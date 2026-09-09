# scripts/apache_acceptance.py
"""Validate the Lab's live Apache routes and basic HTTP responses."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirectHandler(HTTPRedirectHandler):
    """Resolver の redirect を隠さず検査するための handler。"""

    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


def request(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    """HTTP request を送り、HTTPError も通常 response として返す。"""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    request_object = Request(
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/")),
        data=body,
        method=method,
        headers=headers,
    )
    try:
        return build_opener(NoRedirectHandler()).open(request_object, timeout=10)
    except HTTPError as error:
        return error


def expect(response, status: int, label: str):
    """HTTP status を検証し、response を返す。"""
    if response.status != status:
        raise RuntimeError(f"{label}: expected {status}, got {response.status}")
    return response


def run(base_url: str, device_id: str) -> None:
    """Validate Apache routes, JSON errors, CORS, and empty polling responses."""
    arxml = expect(request(base_url, "/arxml/pico2w.arxml"), 200, "AR-XML")
    if "ar-entity" not in arxml.read().decode("utf-8"):
        raise RuntimeError("AR-XML body is invalid")

    invalid_light = expect(
        request(base_url, "/api/light/state", "POST", {"on": "true"}),
        400,
        "light input validation",
    )
    if invalid_light.headers.get("Access-Control-Allow-Origin") != "*":
        raise RuntimeError("Capability API is missing the CORS header")

    expect(request(base_url, "/api/temperature", "OPTIONS"), 204, "temperature preflight")
    expect(
        request(base_url, "/device/commands?device_id=" + device_id),
        204,
        "empty device polling",
    )
    expect(
        request(base_url, "/device/results/" + "0" * 32, "POST", {"ok": True}),
        400,
        "malformed result",
    )


def main() -> int:
    """Parse CLI arguments and return the acceptance exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Lab URL served by Apache")
    parser.add_argument("--device-id", default="pico2w-01", help="Configured Pico device ID")
    args = parser.parse_args()
    try:
        run(args.base_url, args.device_id)
    except Exception as error:  # noqa: BLE001 - acceptance は失敗理由を表示する
        print(f"Apache acceptance failed: {error}", file=sys.stderr)
        return 1
    print("Apache acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
