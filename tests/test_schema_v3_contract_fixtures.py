"""Syntax and inventory checks for the schema-v3 contract fixtures."""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # pyright: ignore[reportMissingModuleSource]

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "schema_v3"
MANIFEST = FIXTURE_DIRECTORY / "manifest.yaml"


def test_every_schema_v3_layout_fixture_is_valid_yaml() -> None:
    fixtures = sorted(FIXTURE_DIRECTORY.glob("*.yaml"))

    assert fixtures
    for fixture in fixtures:
        if fixture == MANIFEST:
            continue
        data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        assert data["schema-version"] == 3


def test_manifest_covers_every_fixture_and_adr_0010_scenario() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    cases = manifest["cases"]

    covered_scenarios = {
        scenario for case in cases for scenario in case["adr-0010-scenarios"]
    }
    assert covered_scenarios == set(range(1, 14))

    fixture_names = {
        path.name for path in FIXTURE_DIRECTORY.glob("*.yaml") if path != MANIFEST
    }
    manifested_names = {case["fixture"] for case in cases}
    assert manifested_names == fixture_names

    allowed_phases = {"validation", "compilation", "compatibility", "runtime-rule"}
    allowed_outcomes = {"valid", "diagnostic", "compatible", "conflict", "denied"}
    for case in cases:
        assert (FIXTURE_DIRECTORY / case["fixture"]).is_file()
        assert case["phase"] in allowed_phases
        assert case["outcome"] in allowed_outcomes
        assert case["expectation"]
        if case["outcome"] == "diagnostic":
            assert re.fullmatch(r"E[0-9]{3}", case["diagnostic"])


def test_track_sections_and_connections_name_each_allowed_movement() -> None:
    for fixture in sorted(FIXTURE_DIRECTORY.glob("*.yaml")):
        if fixture == MANIFEST:
            continue
        data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        for collection_name in ("track-sections", "connections"):
            for declaration in data.get(collection_name, {}).values():
                assert "directions" not in declaration
                movements = declaration["movements"]
                assert movements
                for movement in movements:
                    assert set(movement) == {"from", "to"}
                    assert movement["from"] != movement["to"]


def test_schema_v3_fixtures_do_not_use_display_names() -> None:
    for fixture in sorted(FIXTURE_DIRECTORY.glob("*.yaml")):
        if fixture == MANIFEST:
            continue
        assert "display-name" not in fixture.read_text(encoding="utf-8")
