# scripts/download_runtime.py
"""固定した RELink Web Runtime リリースを取得して検証するスクリプト。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Runtime v0.2.0 standalone ESM Release asset と SHA-256 ダイジェスト。
RUNTIME_VERSION = "v0.2.0"
RUNTIME_URL = (
    "https://github.com/ranmaru50/relink-web-runtime/releases/download/"
    f"{RUNTIME_VERSION}/relink-web-runtime.js"
)
RUNTIME_SHA256 = "1246cd717cc17d1c4c20583f4b3558703d91d30788ce06d09f4bb9e3b5b008fb"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "public" / "vendor" / "relink-web-runtime.js"


def download_runtime() -> Path:
    """Runtime を一時バイト列として取得し、検証後に保存する。"""
    request = Request(RUNTIME_URL, headers={"User-Agent": "relink-reference-lab/0.2"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URL は上記定数に固定
        content = response.read()

    digest = hashlib.sha256(content).hexdigest()
    if digest != RUNTIME_SHA256:
        raise RuntimeError(f"Runtime SHA-256 mismatch: {digest}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(content)
    return OUTPUT_PATH


def main() -> int:
    """取得処理を実行し、シェル向け終了コードを返す。"""
    try:
        output_path = download_runtime()
    except Exception as error:  # noqa: BLE001 - CLI では原因を表示して失敗させる
        print(f"Failed to download Runtime: {error}", file=sys.stderr)
        return 1

    print(f"Downloaded Runtime {RUNTIME_VERSION}: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
