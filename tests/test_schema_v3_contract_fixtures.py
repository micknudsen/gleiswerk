"""Syntax and inventory checks for the schema-v3 contract fixtures."""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # pyright: ignore[reportMissingModuleSource]

from gleiswerk.topology_config import TopologyConfigurationError, load_topology

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


def test_compatibility_expected_results_follow_the_stable_contract() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    compatibility_cases = [
        case for case in manifest["cases"] if case["phase"] == "compatibility"
    ]

    assert compatibility_cases
    for case in compatibility_cases:
        result = case["expected-result"]
        route_pair = result["route-pair"]
        assert route_pair == sorted(route_pair)
        assert result["compatible"] is (not result["conflicts"])

        conflict_keys: list[tuple[str, str, str]] = []
        for conflict in result["conflicts"]:
            provenance = conflict["provenance"]
            assert list(provenance) == route_pair
            assert all(
                sources == sorted(sources) and sources
                for sources in provenance.values()
            )
            if conflict["kind"] == "overlapping-exclusive-claim":
                assert set(conflict) == {"kind", "resource", "provenance"}
                resource_kind, resource_id = conflict["resource"].split(":", 1)
                conflict_keys.append(
                    (
                        str(conflict["kind"]),
                        resource_kind,
                        resource_id,
                    )
                )
            else:
                assert conflict["kind"] == "incompatible-control-device-requirement"
                assert set(conflict) == {
                    "kind",
                    "control-device",
                    "required-positions",
                    "provenance",
                }
                assert list(conflict["required-positions"]) == route_pair
                conflict_keys.append(
                    (
                        str(conflict["kind"]),
                        str(conflict["control-device"]),
                        "",
                    )
                )
        assert conflict_keys == sorted(conflict_keys)


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


def test_documented_reference_layouts_load() -> None:
    """Keep the layouts named in the authoring guide executable."""
    for fixture in ("valid-direct.yaml", "valid-station.yaml"):
        topology = load_topology(FIXTURE_DIRECTORY / fixture)

        assert topology.revision.startswith("sha256:")


def test_documented_invalid_layout_reports_the_stated_diagnostic() -> None:
    """Keep the authoring guide's invalid example and diagnostic aligned."""
    try:
        load_topology(FIXTURE_DIRECTORY / "invalid-dangling-port.yaml")
    except TopologyConfigurationError as error:
        diagnostics = error.diagnostics
    else:
        raise AssertionError("the documented invalid layout unexpectedly loaded")

    assert [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics] == [
        ("E204", "track-sections.approach.ports[1]")
    ]
