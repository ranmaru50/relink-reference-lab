# gateway/server.py
"""Resolver、Capability API、Pico outbound session を提供する開発用 Gateway。"""

from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

# ラボで使用する固定 Anchor。公開運用では Resolver 登録値と一致させる。
ANCHOR_UUID = "550e8400-e29b-41d4-a716-446655440000"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "web"
ARXML_PATH = PROJECT_ROOT / "arxml" / "pico2w.arxml"


class DeviceCommandError(Exception):
    """デバイスがコマンドを実行できなかった場合のエラー。"""


class DeviceCommandTimeout(DeviceCommandError):
    """デバイスから規定時間内に結果が返らなかった場合のエラー。"""


@dataclass(frozen=True)
class DeviceResult:
    """デバイスが返した成功値。"""

    values: dict[str, Any]


@dataclass
class _PendingCommand:
    """送信済み command と待機中の HTTP リクエストを相関させる状態。"""

    event: threading.Event
    result: DeviceResult | None = None
    error: str | None = None


class DeviceSession:
    """Pico ごとの小さな command queue と result correlation を管理する。"""

    def __init__(self, device_id: str) -> None:
        """指定デバイスだけを受け付けるセッションを作成する。"""
        self.device_id = device_id
        self._commands: queue.Queue[dict[str, Any]] = queue.Queue()
        self._pending: dict[str, _PendingCommand] = {}
        self._lock = threading.Lock()

    def submit(self, action: str, inputs: dict[str, Any], timeout: float) -> DeviceResult:
        """コマンドをキューへ追加し、相関した結果を bounded wait する。"""
        command_id = str(uuid.uuid4())
        pending = _PendingCommand(event=threading.Event())
        with self._lock:
            self._pending[command_id] = pending
        self._commands.put({"id": command_id, "action": action, "inputs": inputs})

        if not pending.event.wait(timeout):
            with self._lock:
                self._pending.pop(command_id, None)
            raise DeviceCommandTimeout(f"device command timed out: {action}")

        if pending.error:
            raise DeviceCommandError(pending.error)
        if pending.result is None:
            raise DeviceCommandError("device returned no result")
        return pending.result

    def next_command(self) -> dict[str, Any] | None:
        """Pico の polling に対して待機中の command を一件返す。"""
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    def complete(self, command_id: str, payload: dict[str, Any]) -> bool:
        """Pico の結果を command ID に結び付け、待機中の API を起こす。"""
        if not isinstance(payload.get("ok"), bool):
            return False
        with self._lock:
            pending = self._pending.get(command_id)
            if pending is None:
                return False
            if payload["ok"]:
                values = payload.get("values", {})
                if not isinstance(values, dict):
                    pending.error = "device values must be an object"
                else:
                    pending.result = DeviceResult(values=values)
            else:
                pending.error = str(payload.get("error", "device command failed"))
            self._pending.pop(command_id, None)
            pending.event.set()
        return True


@dataclass(frozen=True)
class GatewayConfig:
    """Gateway の公開 URL と bounded wait を保持する設定。"""

    public_base_url: str = "http://127.0.0.1:8000"
    device_id: str = "pico2w-01"
    device_command_timeout: float = 8.0

    @classmethod
    def from_environment(cls) -> GatewayConfig:
        """環境変数から設定を読み込む。"""
        timeout = float(os.environ.get("DEVICE_COMMAND_TIMEOUT", "8"))
        return cls(
            public_base_url=os.environ.get("PUBLIC_BASE_URL", cls.public_base_url).rstrip("/"),
            device_id=os.environ.get("DEVICE_ID", cls.device_id),
            device_command_timeout=timeout,
        )

    @property
    def description_url(self) -> str:
        """公開 Base URL を基準にした AR-XML の絶対 URL を返す。"""
        return urljoin(f"{self.public_base_url}/", "arxml/pico2w.arxml")


class LabGatewayServer(ThreadingHTTPServer):
    """HTTP handler から参照するラボ設定とセッションを保持するサーバー。"""

    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        config: GatewayConfig | None = None,
        session: DeviceSession | None = None,
    ) -> None:
        """指定アドレスで Gateway を初期化する。"""
        self.config = config or GatewayConfig.from_environment()
        self.session = session or DeviceSession(self.config.device_id)
        super().__init__(server_address, GatewayRequestHandler)


class GatewayRequestHandler(BaseHTTPRequestHandler):
    """Resolver、AR-XML、Capability API、device session の HTTP 境界。"""

    server: LabGatewayServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        """Anchor や入力値を標準ログへ出し過ぎない。"""
        return

    def do_OPTIONS(self) -> None:
        """ブラウザーの Capability API preflight に応答する。"""
        self._send_bytes(HTTPStatus.NO_CONTENT, b"", "text/plain; charset=utf-8")

    def do_GET(self) -> None:
        """GET の公開 read-only resource と temperature を処理する。"""
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/relink/"):
            self._resolve_anchor(parsed.path, parse_qs(parsed.query, keep_blank_values=True))
            return
        if parsed.path == "/arxml/pico2w.arxml":
            self._serve_file(ARXML_PATH, "application/xml; charset=utf-8")
            return
        if parsed.path == "/device/commands":
            self._poll_device(parse_qs(parsed.query, keep_blank_values=True))
            return
        if parsed.path == "/api/temperature":
            self._invoke_device("temperature.read", {})
            return
        self._serve_web(parsed.path)

    def do_POST(self) -> None:
        """Capability API と Pico の result callback を処理する。"""
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/relink/"):
            self._method_not_allowed()
            return
        if parsed.path == "/api/light/state":
            self._set_light_state()
            return
        if parsed.path.startswith("/device/results/"):
            self._complete_device_command(parsed.path)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_HEAD(self) -> None:
        """L1 が定義しない HEAD を 405 として扱う。"""
        self._method_not_allowed()

    def do_PUT(self) -> None:
        """公開 API の更新系メソッドを拒否する。"""
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        """公開 API の更新系メソッドを拒否する。"""
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        """公開 API の削除系メソッドを拒否する。"""
        self._method_not_allowed()

    def _resolve_anchor(self, path: str, query: dict[str, list[str]]) -> None:
        """UUID lookup と L1 の 303 semantics だけを実行する。"""
        if "l" in query and query["l"] != ["1"]:
            self._send_json(HTTPStatus.NOT_IMPLEMENTED, {"error": "requested level is unsupported"})
            return
        if "p" in query:
            status = HTTPStatus.BAD_REQUEST if "l" not in query else HTTPStatus.NOT_IMPLEMENTED
            self._send_json(status, {"error": "parameter p is unsupported"})
            return
        identifier = path.removeprefix("/relink/")
        try:
            uuid.UUID(identifier)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid anchor UUID"})
            return
        if identifier.lower() != ANCHOR_UUID:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "anchor not found"})
            return
        self._send_bytes(
            HTTPStatus.SEE_OTHER,
            b"",
            "text/plain; charset=utf-8",
            extra_headers={"Location": self.server.config.description_url},
        )

    def _poll_device(self, query: dict[str, list[str]]) -> None:
        """許可された device ID にだけ次の lab command を返す。"""
        device_ids = query.get("device_id", [])
        if device_ids != [self.server.config.device_id]:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "device not found"})
            return
        command = self.server.session.next_command()
        if command is None:
            self._send_bytes(HTTPStatus.NO_CONTENT, b"", "application/json")
            return
        self._send_json(HTTPStatus.OK, command)

    def _complete_device_command(self, path: str) -> None:
        """command ID と結果を検証し、Capability API の待機を完了する。"""
        command_id = path.removeprefix("/device/results/")
        if not command_id or len(command_id) > 64:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid command id"})
            return
        try:
            payload = self._read_json()
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if not self.server.session.complete(command_id, payload):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "command not found"})
            return
        self._send_json(HTTPStatus.OK, {"accepted": True})

    def _set_light_state(self) -> None:
        """boolean の light input だけを受け付けて Pico へ送る。"""
        try:
            payload = self._read_json()
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        if set(payload) != {"on"} or not isinstance(payload["on"], bool):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "on must be a boolean"})
            return
        self._invoke_device("light.setState", payload)

    def _invoke_device(self, action: str, inputs: dict[str, Any]) -> None:
        """Pico 結果を待ち、Capability API の JSON representation を返す。"""
        try:
            device_result = self.server.session.submit(
                action, inputs, self.server.config.device_command_timeout
            )
        except DeviceCommandTimeout as error:
            self._send_json(HTTPStatus.GATEWAY_TIMEOUT, {"error": str(error)})
            return
        except DeviceCommandError as error:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return
        self._send_json(HTTPStatus.OK, device_result.values)

    def _read_json(self) -> dict[str, Any]:
        """小さな JSON object を読み、入力エラーを統一する。"""
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4096:
            raise ValueError("JSON body is required and must be at most 4096 bytes")
        body = self.rfile.read(content_length)
        try:
            value = json.loads(body)
        except json.JSONDecodeError as error:
            raise ValueError("invalid JSON body") from error
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _serve_web(self, path: str) -> None:
        """Web UI の限定された静的ファイルだけを配信する。"""
        relative_path = "index.html" if path in {"", "/"} else path.removeprefix("/")
        candidate = (WEB_ROOT / relative_path).resolve()
        if WEB_ROOT.resolve() not in candidate.parents or not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type = (
            "text/html; charset=utf-8" if candidate.suffix == ".html" else "text/javascript"
        )
        self._serve_file(candidate, content_type)

    def _serve_file(self, path: Path, content_type: str) -> None:
        """ファイルを読み、ブラウザー向け CORS と content type を付けて返す。"""
        try:
            content = path.read_bytes()
        except OSError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "resource not found"})
            return
        self._send_bytes(HTTPStatus.OK, content, content_type)

    def _method_not_allowed(self) -> None:
        """Resolver の公開 read-only 契約に従って 405 を返す。"""
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        """JSON representation を共通ヘッダー付きで返す。"""
        content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, content, "application/json; charset=utf-8")

    def _send_bytes(
        self,
        status: HTTPStatus,
        content: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """HTTP response の headers と body を一貫して送信する。"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Referrer-Policy", "no-referrer")
        if status == HTTPStatus.SEE_OTHER:
            self.send_header("Cache-Control", "public, max-age=60")
        elif status in {HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_IMPLEMENTED}:
            self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # クライアントが timeout で先に切断した場合はサーバーを汚染しない。
            return


def run() -> None:
    """環境変数設定でローカル Gateway を起動する。"""
    config = GatewayConfig.from_environment()
    server = LabGatewayServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), config=config)
    print(f"RELink lab Gateway: {config.public_base_url}")
    print(f"Anchor: {config.public_base_url}/relink/{ANCHOR_UUID}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
