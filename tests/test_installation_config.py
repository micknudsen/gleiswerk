# pyright: reportMissingImports=false, reportUnknownMemberType=false
"""Tests for revision-matched Installation Binding validation."""

from pathlib import Path

import pytest

from gleiswerk.installation_config import (
    load_installation_binding,
    validate_installation_binding_data,
)
from gleiswerk.topology import ControlDeviceId, OccupancyZoneId
from gleiswerk.topology_config import TopologyConfigurationError, load_topology

LAYOUT = """schema-version: 3
control-devices:
  turnout: {positions: [normal, reverse]}
occupancy-zones:
  detector:
    coverage: [{resource: track-section:section, extent: complete}]
track-sections:
  section:
    ports: [west, east]
    terminal-ports: [west, east]
    movements: [{from: west, to: east}]
"""


def test_loads_complete_revision_matched_installation_binding(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.yaml"
    layout_path.write_text(LAYOUT, encoding="utf-8")
    topology = load_topology(layout_path)
    binding_path = tmp_path / "binding.yaml"
    binding_path.write_text(
        f"""topology-revision: {topology.revision}
control-devices:
  turnout:
    command-channel: dcc-12
    feedback-channel: input-7
occupancy-zones:
  detector: input-21
""",
        encoding="utf-8",
    )

    binding = load_installation_binding(binding_path, topology)

    assert (
        binding.control_devices[ControlDeviceId("turnout")].command_channel == "dcc-12"
    )
    assert binding.occupancy_feedback[OccupancyZoneId("detector")] == "input-21"


def test_binding_allows_a_command_only_turnout_mechanism(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.yaml"
    layout_path.write_text(LAYOUT, encoding="utf-8")
    topology = load_topology(layout_path)
    binding_path = tmp_path / "binding.yaml"
    binding_path.write_text(
        f"""topology-revision: {topology.revision}
control-devices:
  turnout: {{command-channel: dcc-12}}
occupancy-zones:
  detector: input-21
""",
        encoding="utf-8",
    )

    binding = load_installation_binding(binding_path, topology)

    assert binding.control_devices[ControlDeviceId("turnout")].feedback_channel is None


def test_binding_rejects_stale_missing_unknown_and_conflicting_channels(
    tmp_path: Path,
) -> None:
    layout_path = tmp_path / "layout.yaml"
    layout_path.write_text(LAYOUT, encoding="utf-8")
    topology = load_topology(layout_path)
    data: object = {
        "topology-revision": "sha256:stale",
        "control-devices": {
            "turnout": {"command-channel": "shared", "feedback-channel": "shared"},
            "unknown": {"command-channel": "other", "feedback-channel": "third"},
        },
        "occupancy-zones": {"unknown": "shared"},
    }

    diagnostics = validate_installation_binding_data(data, topology)

    assert [(item.code, item.path) for item in diagnostics] == [
        ("E209", "topology-revision"),
        ("E210", "control-devices.turnout.feedback-channel"),
        ("E200", "control-devices.unknown"),
        ("E200", "occupancy-zones.unknown"),
        ("E111", "occupancy-zones.detector"),
        ("E211", "control-devices.turnout.feedback-channel"),
        ("E211", "occupancy-zones.unknown"),
    ]
    with pytest.raises(TopologyConfigurationError):
        binding_path = tmp_path / "invalid.yaml"
        binding_path.write_text("topology-revision: sha256:stale\n", encoding="utf-8")
        load_installation_binding(binding_path, topology)
