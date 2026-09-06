# tests/test_php_lab.py
"""Apache + PHP 構成の配線と、PHP が利用可能な環境での構文を検証する。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PHP_FILES = sorted(ROOT.glob("**/*.php"))


def test_apache_routes_hide_php_file_names():
    """AR-XML の endpoint と Apache rewrite が public route で一致する。"""
    arxml = (ROOT / "public" / "arxml" / "pico2w.arxml").read_text(encoding="utf-8")
    rewrite = (ROOT / "public" / ".htaccess").read_text(encoding="utf-8")

    assert "../api/light/state" in arxml
    assert "../api/temperature" in arxml
    assert "^api/light/state" in rewrite
    assert "^api/temperature" in rewrite
    assert "^device/commands" in rewrite
    assert "^device/results" in rewrite


@pytest.mark.skipif(shutil.which("php") is None, reason="PHP CLI がこの環境にありません")
@pytest.mark.parametrize("php_file", PHP_FILES)
def test_php_syntax(php_file: Path):
    """利用可能な環境では全 PHP ファイルを lint する。"""
    result = subprocess.run(
        ["php", "-l", str(php_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("php") is None, reason="PHP CLI がこの環境にありません")
def test_php_sqlite_store_smoke():
    """PHP/SQLite が利用可能な環境では状態遷移と expiry を実行確認する。"""
    result = subprocess.run(
        ["php", str(ROOT / "tests" / "php_store_smoke.php")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
