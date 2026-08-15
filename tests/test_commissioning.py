# pyright: reportMissingImports=false, reportUnknownMemberType=false
"""Tests for supervised, fail-closed hardware commissioning verification."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gleiswerk.commissioning import (
    CommissioningConfigurationError,
    CommissioningExpectations,
    CommissioningSnapshot,
    load_commissioning_snapshot,
    verify_commissioning,
)
from gleiswerk.evidence import OccupancyState
from gleiswerk.installation_config import load_installation_binding
from gleiswerk.topology import OccupancyZoneId
from gleiswerk.topology_config import load_topology

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


def _topology_and_binding(tmp_path: Path):
    layout = tmp_path / "layout.yaml"
    layout.write_text(LAYOUT, encoding="utf-8")
    topology = load_topology(layout)
    binding = tmp_path / "binding.yaml"
    binding.write_text(
        f"""topology-revision: {topology.revision}
control-devices:
  turnout:
    command-channel: dcc-12
    position-evidence: {{kind: assumed-after-delay, delay-ms: 500}}
occupancy-zones:
  detector: input-21
""",
        encoding="utf-8",
    )
    return topology, load_installation_binding(binding, topology)


def _snapshot(topology_revision: str, now: datetime) -> CommissioningSnapshot:
    return CommissioningSnapshot(
        topology_revision,
        now,
        "2.5.0",
        {"turnout": "dcc-12"},
        {"detector": "input-21"},
        {"input-21": OccupancyState.CLEAR},
    )


def test_commissioning_accepts_fresh_matching_capture(tmp_path: Path) -> None:
    topology, binding = _topology_and_binding(tmp_path)
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)

    result = verify_commissioning(
        topology,
        binding,
        _snapshot(topology.revision, now),
        CommissioningExpectations({OccupancyZoneId("detector"): OccupancyState.CLEAR}),
        evaluated_at=now,
        maximum_age=timedelta(seconds=30),
    )

    assert result.is_usable
    assert result.failures == ()


def test_commissioning_fails_closed_for_stale_mismatched_or_missing_capture(
    tmp_path: Path,
) -> None:
    topology, binding = _topology_and_binding(tmp_path)
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)
    snapshot = CommissioningSnapshot(
        "sha256:other",
        now - timedelta(seconds=31),
        "2.5.0",
        {"turnout": "dcc-99"},
        {"detector": "input-21"},
        {},
    )

    result = verify_commissioning(
        topology,
        binding,
        snapshot,
        CommissioningExpectations({OccupancyZoneId("detector"): OccupancyState.CLEAR}),
        evaluated_at=now,
        maximum_age=timedelta(seconds=30),
    )

    assert [(item.kind, item.target) for item in result.failures] == [
        ("command-channel-mismatch", "turnout"),
        ("missing-occupancy-state", "detector"),
        ("revision-mismatch", "hardware-capture"),
        ("stale-capture", "hardware-capture"),
    ]


def test_capture_loader_rejects_unsafe_shape(tmp_path: Path) -> None:
    capture = tmp_path / "capture.yaml"
    capture.write_text("topology-revision: sha256:one\n", encoding="utf-8")

    with pytest.raises(CommissioningConfigurationError, match="must contain exactly"):
        load_commissioning_snapshot(capture)
