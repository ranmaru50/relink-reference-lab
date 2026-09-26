# tests/test_php_lab.py
"""Apache + PHP 構成の配線を検証する。"""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).parents[1]


def test_apache_routes_hide_php_file_names():
    """AR-XML の endpoint と Apache rewrite が public route で一致する。"""
    arxml = (ROOT / "public" / "arxml" / "pico2w.arxml").read_text(encoding="utf-8")
    rewrite = (ROOT / "public" / ".htaccess").read_text(encoding="utf-8")

    assert 'base="../api/"' in arxml
    assert 'path="light/state"' in arxml
    assert 'path="temperature"' in arxml
    assert 'xmlns:http="https://relink.dev/ns/arxml/http/0.1"' in arxml
    assert "<interface-uses>" in arxml
    assert "<interfaces>" in arxml
    assert "^api/light/state" in rewrite
    assert "^api/temperature" in rewrite
    assert "^device/commands" in rewrite
    assert "^device/results" in rewrite


def test_draft5_entity_separates_semantics_from_http_routes():
    """Draft 5 のEntityは共有Interfaceと個別Mappingで外部routeを記述する。"""
    arxml = (ROOT / "public" / "arxml" / "pico2w.arxml").read_text(encoding="utf-8")
    root = ElementTree.fromstring(arxml)
    core = "{https://relink.dev/ns/arxml/core/0.1}"
    http = "{https://relink.dev/ns/arxml/http/0.1}"

    assert root.tag == f"{core}ar-entity"
    assert root.attrib["version"] == "0.1"
    assert root.find(f"{core}profiles/{core}conforms-to").attrib["href"] == (
        "https://relink.dev/profiles/reference-lab/controller-monitor/1"
    )
    assert root.find(f"{core}interfaces/{core}interface/{core}realization/{http}api").attrib[
        "base"
    ] == "../api/"

    capabilities = {
        item.attrib["id"]: item for item in root.findall(f"{core}capabilities/{core}capability")
    }
    temperature = capabilities["controller-temperature"]
    assert temperature.attrib["type"] == "https://relink.dev/capabilities/temperature/read/1"
    assert temperature.attrib["subject-ref"] == "controller-mcu"
    route = temperature.find(
        f"{core}interface-uses/{core}interface-use/{core}mapping/{http}operation"
    )
    assert route.attrib == {
        "method": "GET",
        "path": "temperature",
    }


def test_semantic_fixtures_use_exact_matching_identifiers():
    """JSON fixture identity,Profile要件、Capability typeが完全一致する。"""
    definitions = ROOT / "public" / "definitions"
    temperature = json.loads(
        (definitions / "contracts" / "temperature-read.contract.json").read_text(encoding="utf-8")
    )
    indicator = json.loads(
        (definitions / "contracts" / "indicator-set.contract.json").read_text(encoding="utf-8")
    )
    profile = json.loads(
        (definitions / "profiles" / "controller-monitor.profile.json").read_text(encoding="utf-8")
    )

    assert temperature["identifier"] == "https://relink.dev/capabilities/temperature/read/1"
    assert indicator["identifier"] == "https://relink.dev/capabilities/indicator/set/1"
    assert profile["capabilityRequirements"][0]["contractIdentifier"] == temperature["identifier"]


def test_runtime_download_is_pinned_to_verified_draft5_artifact():
    """取得元commitとRuntime hashがLinux bootstrapにも同じ値で固定される。"""
    downloader = (ROOT / "scripts" / "download_runtime.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts" / "setup-linux.sh").read_text(encoding="utf-8")

    assert "402e378c3cd6aa92355f93a3781c7ddc49c141d5" in downloader
    assert "dist/relink-web-runtime.js" in downloader
    assert "1d8605db4529929d2ee63dde9da407c0a3350abb559751352fd5083ed6f5245a" in downloader
    assert "1d8605db4529929d2ee63dde9da407c0a3350abb559751352fd5083ed6f5245a" in bootstrap
