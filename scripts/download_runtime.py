# scripts/download_runtime.py
"""固定した RELink Web Runtime リリースを取得して検証するスクリプト。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Runtime 0.1.0 の公開 standalone ESM アセットと SHA-256 ダイジェスト。
RUNTIME_URL = (
    "https://github.com/ranmaru50/relink-web-runtime/releases/download/"
    "v0.1.0/relink-web-runtime.js"
)
RUNTIME_SHA256 = "f18d739edabc23285abd5fb64fcc056f17aaf480ddd1e0b6bed1702f8aab9e46"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "web" / "vendor" / "relink-web-runtime.js"


def download_runtime() -> Path:
    """Runtime を一時バイト列として取得し、検証後に保存する。"""
    request = Request(RUNTIME_URL, headers={"User-Agent": "relink-reference-lab/0.1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URL は上記定数に固定
        content = response.read()

    digest = hashlib.sha256(content).hexdigest()
    if digest != RUNTIME_SHA256:
        raise RuntimeError(f"Runtime の SHA-256 が一致しません: {digest}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(content)
    return OUTPUT_PATH


def main() -> int:
    """取得処理を実行し、シェル向け終了コードを返す。"""
    try:
        output_path = download_runtime()
    except Exception as error:  # noqa: BLE001 - CLI では原因を表示して失敗させる
        print(f"Runtime の取得に失敗しました: {error}", file=sys.stderr)
        return 1

    print(f"Runtime 0.1.0 を取得しました: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
