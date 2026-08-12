"""Tests for deterministic topology evidence validation."""

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gleiswerk.evidence import (
    DevicePositionEvidence,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyState,
)
from gleiswerk.evidence_validation import EvidenceRejectionKind, validate_evidence
from gleiswerk.route_compiler import compile_route
from gleiswerk.topology import (
    ControlDeviceId,
    DevicePositionId,
    OccupancyZoneId,
    RouteDefinitionId,
    TrackSectionId,
    TrackSectionResource,
)
from gleiswerk.topology_config import load_topology

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "schema_v3"


def _context():
    topology = load_topology(FIXTURES / "valid-occupancy.yaml")
    return topology, compile_route(topology, RouteDefinitionId("west-to-main"))


def _occupancy(
    topology_revision: str,
    zone: str,
    state: OccupancyState = OccupancyState.CLEAR,
    observed_at: datetime = NOW,
):
    return OccupancyEvidence(
        OccupancyZoneId(zone),
        topology_revision,
        EvidenceSourceId(f"{zone}-source"),
        EvidenceSourceStatus.AVAILABLE,
        observed_at,
        state,
    )


def _device(topology_revision: str, position: str = "normal"):
    return DevicePositionEvidence(
        ControlDeviceId("throat-turnout"),
        topology_revision,
        EvidenceSourceId("turnout-source"),
        EvidenceSourceStatus.AVAILABLE,
        NOW,
        DevicePositionId(position),
    )


OccupancyFactory = Callable[[str], OccupancyEvidence]
DeviceFactory = Callable[[str], DevicePositionEvidence]


def _validate(
    occupancy_factories: Iterable[OccupancyFactory] = (),
    device_factories: Iterable[DeviceFactory] = (),
):
    topology, plan = _context()
    return validate_evidence(
        topology,
        plan,
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)),
        tuple(factory(topology.revision) for factory in occupancy_factories),
        tuple(factory(topology.revision) for factory in device_factories),
    )


def test_complete_clear_evidence_is_usable() -> None:
    result = _validate(
        (
            lambda revision: _occupancy(revision, "main-detector"),
            lambda revision: _occupancy(revision, "throat-detector"),
        ),
        (lambda revision: _device(revision),),
    )

    assert result.is_usable
    assert [item.outcome for item in result.occupancy_results] == ["clear", "clear"]
    assert result.device_position_results[0].outcome == "aligned"


def test_occupied_evidence_is_not_usable() -> None:
    result = _validate(
        (
            lambda revision: _occupancy(revision, "main-detector"),
            lambda revision: _occupancy(
                revision, "throat-detector", OccupancyState.OCCUPIED
            ),
        ),
        (lambda revision: _device(revision),),
    )

    assert not result.is_usable
    assert result.rejections[0].kind is EvidenceRejectionKind.OCCUPIED
    assert result.rejections[0].source_ids == ("throat-detector-source",)


def test_stale_evidence_is_not_usable() -> None:
    result = _validate(
        (
            lambda revision: _occupancy(
                revision, "main-detector", observed_at=NOW - timedelta(seconds=31)
            ),
            lambda revision: _occupancy(revision, "throat-detector"),
        ),
        (lambda revision: _device(revision),),
    )

    assert EvidenceRejectionKind.STALE in {item.kind for item in result.rejections}


def test_missing_or_partial_coverage_is_not_usable() -> None:
    result = _validate(
        (lambda revision: _occupancy(revision, "main-detector"),),
        (lambda revision: _device(revision),),
    )

    assert EvidenceRejectionKind.MISSING_OCCUPANCY_EVIDENCE in {
        item.kind for item in result.rejections
    }


def test_partial_occupancy_coverage_cannot_satisfy_a_claim() -> None:
    topology, plan = _context()
    plan_with_partially_covered_claim = replace(
        plan, claims=plan.claims + (TrackSectionResource(TrackSectionId("siding")),)
    )
    result = validate_evidence(
        topology,
        plan_with_partially_covered_claim,
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)),
        (_occupancy(topology.revision, "main-detector"),),
        (_device(topology.revision),),
    )

    assert EvidenceRejectionKind.MISSING_OCCUPANCY_COVERAGE in {
        item.kind for item in result.rejections
    }


def test_device_mismatch_is_not_usable() -> None:
    result = _validate(
        (
            lambda revision: _occupancy(revision, "main-detector"),
            lambda revision: _occupancy(revision, "throat-detector"),
        ),
        (lambda revision: _device(revision, "reverse"),),
    )

    assert result.device_position_results[0].outcome == "unaligned"
    assert result.rejections[0].kind is EvidenceRejectionKind.UNALIGNED


def test_duplicate_evidence_is_not_usable_regardless_of_input_order() -> None:
    def duplicate(revision: str):
        return OccupancyEvidence(
            OccupancyZoneId("main-detector"),
            revision,
            EvidenceSourceId("backup-source"),
            EvidenceSourceStatus.AVAILABLE,
            NOW,
            OccupancyState.CLEAR,
        )

    result = _validate(
        (
            duplicate,
            lambda revision: _occupancy(revision, "main-detector"),
            lambda revision: _occupancy(revision, "throat-detector"),
        ),
        (lambda revision: _device(revision),),
    )

    duplicate_rejection = next(
        item
        for item in result.rejections
        if item.kind is EvidenceRejectionKind.DUPLICATE_OCCUPANCY_EVIDENCE
    )
    assert duplicate_rejection.source_ids == ("backup-source", "main-detector-source")


def test_revision_mismatch_is_not_usable() -> None:
    result = _validate(
        (
            lambda _: OccupancyEvidence(
                OccupancyZoneId("main-detector"),
                "old-revision",
                EvidenceSourceId("main-source"),
                EvidenceSourceStatus.AVAILABLE,
                NOW,
                OccupancyState.CLEAR,
            ),
            lambda revision: _occupancy(revision, "throat-detector"),
        ),
        (lambda revision: _device(revision),),
    )

    assert EvidenceRejectionKind.REVISION_MISMATCH in {
        item.kind for item in result.rejections
    }
