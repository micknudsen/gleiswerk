"""Tests for bounded movement-authority evaluation."""
# pyright: reportMissingImports=false, reportUnknownMemberType=false

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gleiswerk.evidence import (
    DevicePositionEvidence,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyState,
)
from gleiswerk.evidence_validation import validate_evidence
from gleiswerk.movement_authority import (
    MovementAuthorityEvaluator,
    MovementAuthorityFailureKind,
    MovementAuthorityRequest,
)
from gleiswerk.route_compiler import compile_route
from gleiswerk.route_reservations import (
    AcquireReservationRequest,
    ReleaseReservationRequest,
    ReservationManager,
    ReservationOwner,
)
from gleiswerk.topology import (
    ControlDeviceId,
    DevicePositionId,
    OccupancyZoneId,
    RouteDefinitionId,
)
from gleiswerk.topology_config import load_topology

NOW = datetime(2026, 8, 13, 12, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "schema_v3"


class Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def __call__(self) -> float:
        return self.now


def _context():
    topology = load_topology(FIXTURES / "valid-occupancy.yaml")
    plan = compile_route(topology, RouteDefinitionId("west-to-main"))
    manager = ReservationManager(topology)
    acquired = manager.acquire(
        AcquireReservationRequest(ReservationOwner("dispatcher"), plan)
    )
    assert acquired.reservation is not None
    return topology, plan, manager, acquired.reservation


def _evidence(
    topology_revision: str,
    *,
    occupied: bool = False,
    position: str = "normal",
    stale: bool = False,
):
    observed_at = NOW - timedelta(seconds=31) if stale else NOW
    return validate_evidence(
        load_topology(FIXTURES / "valid-occupancy.yaml"),
        compile_route(
            load_topology(FIXTURES / "valid-occupancy.yaml"),
            RouteDefinitionId("west-to-main"),
        ),
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)),
        (
            OccupancyEvidence(
                OccupancyZoneId("main-detector"),
                topology_revision,
                EvidenceSourceId("main-source"),
                EvidenceSourceStatus.AVAILABLE,
                observed_at,
                OccupancyState.OCCUPIED if occupied else OccupancyState.CLEAR,
            ),
            OccupancyEvidence(
                OccupancyZoneId("throat-detector"),
                topology_revision,
                EvidenceSourceId("throat-source"),
                EvidenceSourceStatus.AVAILABLE,
                NOW,
                OccupancyState.CLEAR,
            ),
        ),
        (
            DevicePositionEvidence(
                ControlDeviceId("throat-turnout"),
                topology_revision,
                EvidenceSourceId("turnout-source"),
                EvidenceSourceStatus.AVAILABLE,
                NOW,
                DevicePositionId(position),
            ),
        ),
    )


def _evaluator(revision: str, clock: Clock) -> MovementAuthorityEvaluator:
    return MovementAuthorityEvaluator(revision, timedelta(seconds=60), clock)


def test_grants_a_bounded_authority_for_live_clear_reservation() -> None:
    topology, _, manager, reservation = _context()
    clock = Clock()
    evaluator = _evaluator(topology.revision, clock)

    result = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )

    assert result.outcome == "granted"
    assert result.authority is not None
    assert result.authority.scope.claims == reservation.claims
    assert result.authority.expires_at == 40.0
    assert evaluator.inspect().authorities == (result.authority,)


def test_denies_occupied_evidence_without_creating_authority_or_releasing_reservation() -> (
    None
):
    topology, _, manager, reservation = _context()
    evaluator = _evaluator(topology.revision, Clock())

    result = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision, occupied=True),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )

    assert result.outcome == "denied"
    assert result.denial_reason is not None
    assert result.denial_reason.kind is MovementAuthorityFailureKind.OCCUPANCY_EVIDENCE
    assert result.denial_reason.evidence_rejection is not None
    assert result.denial_reason.evidence_rejection.kind == "occupied"
    assert evaluator.inspect().authorities == ()
    assert manager.inspect().reservations == (reservation,)


def test_reevaluation_revokes_for_device_mismatch_without_releasing_reservation() -> (
    None
):
    topology, _, manager, reservation = _context()
    clock = Clock()
    evaluator = _evaluator(topology.revision, clock)
    granted = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )
    assert granted.authority is not None

    reevaluated = evaluator.reevaluate(
        granted.authority.id,
        manager.inspect(),
        _evidence(topology.revision, position="reverse"),
    )

    assert reevaluated.outcome == "revoked"
    assert reevaluated.authority is not None
    assert reevaluated.authority.revocation is not None
    assert (
        reevaluated.authority.revocation.kind
        is MovementAuthorityFailureKind.DEVICE_POSITION_EVIDENCE
    )
    assert manager.inspect().reservations == (reservation,)


def test_reevaluation_revokes_when_the_reservation_is_released() -> None:
    topology, _, manager, reservation = _context()
    clock = Clock()
    evaluator = _evaluator(topology.revision, clock)
    granted = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )
    assert granted.authority is not None
    manager.release(
        ReleaseReservationRequest(ReservationOwner("dispatcher"), reservation.id)
    )

    result = evaluator.reevaluate(
        granted.authority.id, manager.inspect(), _evidence(topology.revision)
    )

    assert result.outcome == "revoked"
    assert result.authority is not None
    assert result.authority.revocation is not None
    assert result.authority.revocation.kind is MovementAuthorityFailureKind.RESERVATION
    assert manager.inspect().reservations == ()


def test_reevaluation_selects_evidence_before_expiration_and_is_idempotent() -> None:
    topology, _, manager, reservation = _context()
    clock = Clock()
    evaluator = _evaluator(topology.revision, clock)
    granted = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(seconds=10),
        ),
        manager.inspect(),
    )
    assert granted.authority is not None
    clock.now = 20.0

    first = evaluator.reevaluate(
        granted.authority.id,
        manager.inspect(),
        _evidence(topology.revision, occupied=True),
    )
    second = evaluator.reevaluate(
        granted.authority.id, manager.inspect(), _evidence(topology.revision)
    )

    assert first.authority is not None
    assert first.authority.revocation is not None
    assert (
        first.authority.revocation.kind
        is MovementAuthorityFailureKind.OCCUPANCY_EVIDENCE
    )
    assert second.authority == first.authority


def test_denies_stale_evidence_and_revision_mismatch_in_their_categories() -> None:
    topology, _, manager, reservation = _context()
    evaluator = _evaluator(topology.revision, Clock())
    stale = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision, stale=True),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )
    revision_mismatch = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            replace(_evidence(topology.revision), topology_revision="sha256:old"),
            timedelta(seconds=30),
        ),
        manager.inspect(),
    )

    assert stale.denial_reason is not None
    assert stale.denial_reason.kind is MovementAuthorityFailureKind.OCCUPANCY_EVIDENCE
    assert stale.denial_reason.evidence_rejection is not None
    assert stale.denial_reason.evidence_rejection.kind == "stale"
    assert revision_mismatch.denial_reason is not None
    assert (
        revision_mismatch.denial_reason.kind
        is MovementAuthorityFailureKind.TOPOLOGY_REVISION
    )


def test_reevaluation_revokes_an_expired_authority() -> None:
    topology, _, manager, reservation = _context()
    clock = Clock()
    evaluator = _evaluator(topology.revision, clock)
    granted = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(seconds=10),
        ),
        manager.inspect(),
    )
    assert granted.authority is not None
    clock.now = 20.0

    result = evaluator.reevaluate(
        granted.authority.id, manager.inspect(), _evidence(topology.revision)
    )

    assert result.authority is not None
    assert result.authority.revocation is not None
    assert result.authority.revocation.kind is MovementAuthorityFailureKind.EXPIRATION


def test_denials_use_the_documented_prerequisite_order() -> None:
    topology, _, manager, reservation = _context()
    evaluator = _evaluator(topology.revision, Clock())
    wrong_scope = replace(_evidence(topology.revision), plan_route_id="other-route")

    result = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("other"),
            reservation.id,
            wrong_scope,
            timedelta(seconds=90),
        ),
        manager.inspect(),
    )

    assert result.denial_reason is not None
    assert result.denial_reason.kind is MovementAuthorityFailureKind.RESERVATION


def test_request_rejects_nonpositive_validity() -> None:
    topology, _, _, reservation = _context()

    with pytest.raises(ValueError, match="must be positive"):
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            _evidence(topology.revision),
            timedelta(),
        )
