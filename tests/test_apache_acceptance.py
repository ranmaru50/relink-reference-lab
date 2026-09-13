# tests/test_apache_acceptance.py
"""Apache acceptance の統合判定をローカル HTTP fixture で検証する。"""

from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.apache_acceptance import run

ANCHOR_UUID = "550e8400-e29b-41d4-a716-446655440000"
RUNTIME_BODY = b"export const runtimeVersion = '0.1.0';\n"


class AcceptanceHandler(BaseHTTPRequestHandler):
    """実運用で検証するstatusとheaderだけを返すHTTP fixture。"""

    server_version = "Apache"
    sys_version = ""
    expected_location = ""
    include_hsts = False

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler のAPI名に従う
        """UI、AR-XML、Runtime、Resolver、pollingを返す。"""
        if len(self.headers.get("X-RELink-Acceptance-Oversized", "")) > 8190:
            self._respond(400)
            return
        if self.path == "/":
            self._respond(200, b"<h1>RELink Pico 2 W</h1>")
        elif self.path == "/arxml/pico2w.arxml":
            self._respond(200, b"<ar-entity />")
        elif self.path == "/vendor/relink-web-runtime.js":
            self._respond(200, RUNTIME_BODY)
        elif self.path == f"/relink/{ANCHOR_UUID}":
            self.send_response(303)
            self.send_header("Location", self.expected_location)
            if self.include_hsts:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            self.end_headers()
        elif self.path.startswith("/device/commands?"):
            self._respond(204)
        else:
            self._respond(404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler のAPI名に従う
        """Capability validation と不正resultの応答を返す。"""
        if self.path == "/api/light/state":
            self.send_response(400)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        elif self.path == "/device/results/" + "0" * 32:
            self._respond(400)
        else:
            self._respond(404)

    def do_TRACE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler のAPI名に従う
        """TraceEnable Off と同じ拒否応答を返す。"""
        self._respond(405)

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler のAPI名に従う
        """温度Capabilityのpreflightを返す。"""
        self._respond(204 if self.path == "/api/temperature" else 404)

    def log_message(self, format: str, *args: object) -> None:
        """テスト出力へHTTPアクセスログを混在させない。"""

    def _respond(self, status: int, body: bytes = b"") -> None:
        """最小HTTP responseを返す。"""
        if len(self.headers.get("X-RELink-Acceptance-Oversized", "")) > 8190:
            status = 400
        self.send_response(status)
        if self.include_hsts:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.end_headers()
        if body:
            self.wfile.write(body)


def test_acceptance_checks_resolver_lab_runtime_and_polling() -> None:
    """一括構築後に必要なHTTP経路を1回のacceptanceで確認する。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), AcceptanceHandler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    AcceptanceHandler.expected_location = base_url + "/arxml/pico2w.arxml"
    AcceptanceHandler.include_hsts = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run(
            base_url,
            "pico2w-01",
            base_url,
            ANCHOR_UUID,
            AcceptanceHandler.expected_location,
            runtime_sha256=hashlib.sha256(RUNTIME_BODY).hexdigest(),
            require_hsts=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
