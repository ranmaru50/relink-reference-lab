# tests/test_gateway.py
"""Gateway の L1、session correlation、入力境界を検証するテスト。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest

from gateway.server import DeviceSession, GatewayConfig, LabGatewayServer


@pytest.fixture()
def gateway() -> Iterator[tuple[LabGatewayServer, str]]:
    """テスト用の ephemeral Gateway を起動・停止する。"""
    config = GatewayConfig(
        public_base_url="https://lab.example",
        device_id="test-device",
        device_command_timeout=0.5,
    )
    server = LabGatewayServer(
        ("127.0.0.1", 0),
        config=config,
        session=DeviceSession(config.device_id),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield server, base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    """テスト用に redirect 自動追従を無効にした HTTP リクエストを送る。"""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_object = urllib.request.Request(
        base_url + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        """Resolver の 303 Location をテスト側で直接検査する。"""

        def redirect_request(self, req, fp, code, msg, headers, new):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(request_object, timeout=2)
    except urllib.error.HTTPError as error:
        return error
    return response


def response_json(response) -> dict:
    """テスト response の JSON を辞書へ変換する。"""
    return json.loads(response.read().decode("utf-8"))


def test_l1_resolver_returns_absolute_303(gateway):
    """ACTIVE UUID が AR-XML の絶対 HTTPS URL へ 303 される。"""
    _, base_url = gateway
    response = request(base_url, "/relink/" + "550e8400-e29b-41d4-a716-446655440000")

    assert response.status == 303
    assert response.headers["Location"] == "https://lab.example/arxml/pico2w.arxml"
    assert response.headers["Cache-Control"] == "public, max-age=60"
    assert response.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("/relink/not-a-uuid", 400),
        ("/relink/550e8400-e29b-41d4-a716-446655440000?l=2", 501),
        ("/relink/550e8400-e29b-41d4-a716-446655440000?p=demo", 400),
        ("/relink/" + str(uuid.uuid4()), 404),
    ],
)
def test_l1_fail_closed(gateway, path, status):
    """不正 UUID、未対応 level、予約 parameter は fail closed する。"""
    _, base_url = gateway
    response = request(base_url, path)
    assert response.status == status


def test_resolver_is_read_only(gateway):
    """Resolver の POST は 405 で、Capability 実行へ流れない。"""
    _, base_url = gateway
    response = request(base_url, "/relink/550e8400-e29b-41d4-a716-446655440000", "POST", {})
    assert response.status == 405


def test_light_command_is_correlated_to_device_result(gateway):
    """API の待機が Pico の command ID 付き result で完了する。"""
    _, base_url = gateway
    outcome = {}

    def call_api():
        response = request(base_url, "/api/light/state", "POST", {"on": True})
        outcome["status"] = response.status
        outcome["body"] = response_json(response)

    api_thread = threading.Thread(target=call_api)
    api_thread.start()
    server_response = request(base_url, "/device/commands?device_id=test-device")
    command = response_json(server_response)
    assert command["action"] == "light.setState"
    assert command["inputs"] == {"on": True}
    result = request(
        base_url,
        "/device/results/" + command["id"],
        "POST",
        {"ok": True, "values": {"state": True}},
    )
    api_thread.join(timeout=1)

    assert result.status == 200
    assert outcome == {"status": 200, "body": {"state": True}}


def test_device_timeout_is_reported(gateway):
    """Pico が応答しない場合に API が 504 を返す。"""
    _, base_url = gateway
    response = request(base_url, "/api/temperature")
    assert response.status == 504
    assert "timed out" in response_json(response)["error"]


def test_light_requires_boolean_input(gateway):
    """light API は任意値をデバイスへ転送せず boolean だけを受け付ける。"""
    _, base_url = gateway
    response = request(base_url, "/api/light/state", "POST", {"on": "true"})
    assert response.status == 400


def test_arxml_fixture_contains_two_capabilities():
    """Draft 4 fixture の Entity、contract、HTTP binding を確認する。"""
    fixture_path = Path(__file__).parents[1] / "arxml" / "pico2w.arxml"
    root = ET.parse(fixture_path).getroot()
    namespace = {"ar": "https://relink.dev/ns/arxml/core/0.1"}
    capabilities = root.findall("ar:capabilities/ar:capability", namespace)

    assert root.tag == "{https://relink.dev/ns/arxml/core/0.1}ar-entity"
    assert [item.attrib["id"] for item in capabilities] == ["light", "temperature"]
    assert capabilities[0].find("ar:inputs/ar:input", namespace).attrib == {
        "name": "on",
        "type": "boolean",
        "required": "true",
    }
    assert (
        capabilities[0].find("ar:interfaces/ar:interface", namespace).attrib["method"]
        == "POST"
    )
    assert (
        capabilities[1].find("ar:result/ar:outputs/ar:output", namespace).attrib["type"]
        == "number"
    )
