# scripts/download_runtime.py
"""固定した RELink Web Runtime リリースを取得して検証するスクリプト。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# Runtime 0.2.0 standalone ESM アセットと SHA-256 ダイジェスト。
# Release 作成前の ver.0.2.0 ブランチを完全な commit SHA で固定する。
RUNTIME_REVISION = "402e378c3cd6aa92355f93a3781c7ddc49c141d5"
RUNTIME_URL = (
    "https://raw.githubusercontent.com/ranmaru50/relink-web-runtime/"
    f"{RUNTIME_REVISION}/dist/relink-web-runtime.js"
)
RUNTIME_SHA256 = "1d8605db4529929d2ee63dde9da407c0a3350abb559751352fd5083ed6f5245a"
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

    print(f"Downloaded Runtime 0.2.0 ({RUNTIME_REVISION}): {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
