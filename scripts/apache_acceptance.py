# scripts/apache_acceptance.py
"""Lab と Resolver の Apache 経由エンドポイントを検証する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class NoRedirectHandler(HTTPRedirectHandler):
    """Resolver の redirect を隠さず検査するための handler。"""

    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


def build_http_opener(ca_file: str | None = None):
    """必要に応じて開発 CA を信頼する redirect 無効の opener を作成する。"""
    context = ssl.create_default_context(cafile=ca_file)
    return build_opener(NoRedirectHandler(), HTTPSHandler(context=context))


def request(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    opener=None,
    headers: dict[str, str] | None = None,
):
    """HTTP request を送り、HTTPError も通常 response として返す。"""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"} if body is not None else {}
    if headers:
        request_headers.update(headers)
    request_object = Request(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
        data=body,
        method=method,
        headers=request_headers,
    )
    http_opener = opener or build_http_opener()
    try:
        return http_opener.open(request_object, timeout=10)
    except HTTPError as error:
        return error


def expect(response, status: int, label: str):
    """HTTP status を検証し、response を返す。"""
    if response.status != status:
        raise RuntimeError(f"{label}: expected {status}, got {response.status}")
    return response


def check_hardening(
    base_url: str,
    path: str,
    opener,
    label: str,
    require_hsts: bool,
    expected_status: int = 200,
) -> None:
    """Apache hardening の実効値（header、TRACE、request bound）を確認する。"""
    normal = expect(
        request(base_url, path, opener=opener),
        expected_status,
        f"{label} security probe",
    )
    server_header = normal.headers.get("Server", "")
    if server_header != "Apache":
        raise RuntimeError(f"{label} Server header is not hardened: {server_header!r}")
    if normal.headers.get("X-Powered-By") is not None:
        raise RuntimeError(f"{label} exposes X-Powered-By")
    if require_hsts and normal.headers.get("Strict-Transport-Security") != "max-age=31536000":
        raise RuntimeError(f"{label} is missing the expected HSTS header")

    expect(
        request(base_url, path, "TRACE", opener=opener),
        405,
        f"{label} TRACE disabled",
    )
    expect(
        request(
            base_url,
            path,
            headers={"X-RELink-Acceptance-Oversized": "x" * 9000},
            opener=opener,
        ),
        400,
        f"{label} request field bound",
    )


def run(
    base_url: str,
    device_id: str,
    resolver_base_url: str | None = None,
    anchor_uuid: str | None = None,
    expected_location: str | None = None,
    ca_file: str | None = None,
    runtime_sha256: str | None = None,
    require_hsts: bool = False,
) -> None:
    """Apache route、Resolver redirect、Runtime asset をまとめて検証する。"""
    resolver_values = (resolver_base_url, anchor_uuid, expected_location)
    if any(value is not None for value in resolver_values) and not all(
        value is not None for value in resolver_values
    ):
        raise ValueError("Resolver verification requires base URL, Anchor UUID, and Location")

    opener = build_http_opener(ca_file)

    web_ui = expect(request(base_url, "/", opener=opener), 200, "Lab Web UI")
    if "RELink Pico 2 W" not in web_ui.read().decode("utf-8"):
        raise RuntimeError("Lab Web UI body is invalid")
    check_hardening(base_url, "/", opener, "Lab", require_hsts)

    arxml = expect(request(base_url, "/arxml/pico2w.arxml", opener=opener), 200, "AR-XML")
    if "ar-entity" not in arxml.read().decode("utf-8"):
        raise RuntimeError("AR-XML body is invalid")

    runtime = expect(
        request(base_url, "/vendor/relink-web-runtime.js", opener=opener),
        200,
        "RELink Web Runtime",
    )
    runtime_digest = hashlib.sha256(runtime.read()).hexdigest()
    if runtime_sha256 is not None and runtime_digest != runtime_sha256:
        raise RuntimeError(
            f"Runtime SHA-256 mismatch: expected {runtime_sha256}, got {runtime_digest}"
        )

    if any(value is not None for value in resolver_values):
        check_hardening(
            resolver_base_url,
            f"/relink/{anchor_uuid}",
            opener,
            "Resolver",
            require_hsts,
            expected_status=303,
        )
        resolver = expect(
            request(resolver_base_url, f"/relink/{anchor_uuid}", opener=opener),
            303,
            "Resolver L1",
        )
        actual_location = resolver.headers.get("Location")
        if actual_location != expected_location:
            raise RuntimeError(
                f"Resolver Location mismatch: expected {expected_location}, got {actual_location}"
            )

    invalid_light = expect(
        request(base_url, "/api/light/state", "POST", {"on": "true"}, opener),
        400,
        "light input validation",
    )
    if invalid_light.headers.get("Access-Control-Allow-Origin") != "*":
        raise RuntimeError("Capability API is missing the CORS header")

    expect(
        request(base_url, "/api/temperature", "OPTIONS", opener=opener),
        204,
        "temperature preflight",
    )
    expect(
        request(base_url, "/device/commands?device_id=" + device_id, opener=opener),
        204,
        "empty device polling",
    )
    expect(
        request(
            base_url,
            "/device/results/" + "0" * 32,
            "POST",
            {"ok": True},
            opener,
        ),
        400,
        "malformed result",
    )


def main() -> int:
    """CLI 引数を解析し、受け入れ検証の終了コードを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Lab URL served by Apache")
    parser.add_argument("--device-id", default="pico2w-01", help="Configured Pico device ID")
    parser.add_argument("--resolver-base-url", help="Resolver URL served by Apache")
    parser.add_argument("--anchor-uuid", help="Registered sample Anchor UUID")
    parser.add_argument("--expected-location", help="Expected Resolver Location header")
    parser.add_argument("--ca-file", help="Development CA certificate used by local HTTPS")
    parser.add_argument("--runtime-sha256", help="Expected Runtime asset SHA-256")
    parser.add_argument(
        "--require-hsts",
        action="store_true",
        help="Require the production HSTS header on both Apache hosts",
    )
    args = parser.parse_args()
    try:
        run(
            args.base_url,
            args.device_id,
            args.resolver_base_url,
            args.anchor_uuid,
            args.expected_location,
            args.ca_file,
            args.runtime_sha256,
            args.require_hsts,
        )
    except Exception as error:  # noqa: BLE001 - acceptance は失敗理由を表示する
        print(f"Apache acceptance failed: {error}", file=sys.stderr)
        return 1
    print("Apache acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
