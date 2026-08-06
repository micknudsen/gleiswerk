# pyright: reportArgumentType=false, reportIndexIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false
"""Tests for schema-version 3 core topology configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from gleiswerk.topology import TrackSectionId
from gleiswerk.topology_config import (
    TopologyConfigurationError,
    load_topology,
    validate_topology_data,
)

VALID_TOPOLOGY = """schema-version: 3
track-sections:
  approach:
    ports: [west, east]
    terminal-ports: [west]
    movements: [{from: west, to: east}]
  platform:
    ports: [west, east]
    terminal-ports: [east]
    movements: [{from: west, to: east}]
connections:
  approach-to-platform:
    ports: [track-section:approach:east, track-section:platform:west]
    movements:
      - {from: track-section:approach:east, to: track-section:platform:west}
"""


def test_loads_valid_core_topology_into_immutable_domain_values(tmp_path: Path) -> None:
    path = tmp_path / "layout.yaml"
    path.write_text(VALID_TOPOLOGY, encoding="utf-8")

    topology = load_topology(path)

    assert topology.track_sections[TrackSectionId("approach")].ports == (
        "west",
        "east",
    )
    assert topology.connections["approach-to-platform"].id == "approach-to-platform"
    with pytest.raises(TypeError):
        topology.track_sections[TrackSectionId("other")] = topology.track_sections[
            TrackSectionId("approach")
        ]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"schema-version": 2}, ("E103", "schema-version")),
        (
            {
                "schema-version": 3,
                "track-sections": {
                    "approach": {
                        "ports": ["west", "east"],
                        "terminal-ports": ["west"],
                        "movements": [{"from": "west", "to": "east"}],
                    }
                },
            },
            ("E204", "track-sections.approach.ports[1]"),
        ),
    ],
)
def test_validation_rejects_unsupported_versions_and_dangling_ports(
    data: object, expected: tuple[str, str]
) -> None:
    diagnostics = validate_topology_data(data)

    assert [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics] == [
        expected
    ]


def test_validation_rejects_unresolved_references_and_ambiguous_passages() -> None:
    data = {
        "schema-version": 3,
        "junctions": {
            "throat": {
                "ports": ["west", "main", "branch"],
                "terminal-ports": ["west", "main", "branch"],
            }
        },
        "connections": {
            "missing": {
                "ports": ["junction:throat:west", "track-section:nope:west"],
                "movements": [
                    {
                        "from": "junction:throat:west",
                        "to": "track-section:nope:west",
                    }
                ],
            }
        },
        "junction-passages": {
            "to-main": {"junction": "throat", "from": "west", "to": "main"},
            "to-branch": {
                "junction": "throat",
                "from": "west",
                "to": "branch",
            },
        },
    }

    diagnostics = validate_topology_data(data)

    assert [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics] == [
        ("E200", "connections.missing.ports[1]"),
        ("E203", "junctions.throat.ports[0]"),
        ("E300", "junction-passages.to-branch"),
    ]


def test_load_topology_preserves_error_reporting_behavior(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.yaml"
    path.write_text("schema-version: 2\n", encoding="utf-8")

    with pytest.raises(TopologyConfigurationError) as error:
        load_topology(path)

    message = str(cast(Exception, error.value))

    assert message == (
        f"ERROR E103 {path}:schema-version:\n  unsupported schema version 2"
    )


def test_load_topology_rejects_duplicate_yaml_keys_and_anchors(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("schema-version: 3\nschema-version: 3\n", encoding="utf-8")
    anchored = tmp_path / "anchored.yaml"
    anchored.write_text("schema-version: 3\nvalue: &value {}\n", encoding="utf-8")

    for path in (duplicate, anchored):
        with pytest.raises(TopologyConfigurationError) as error:
            load_topology(path)
        assert error.value.diagnostics[0].code == "E005"
