# tests/test_php_lab.py
"""Apache + PHP 構成の配線を検証する。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


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
