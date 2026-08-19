"""Simulator tests for supervised runtime evidence ingestion."""

from datetime import UTC, datetime, timedelta

from gleiswerk.evidence import (
    EvidenceFreshness,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyState,
)
from gleiswerk.runtime_evidence import (
    RuntimeEvidenceFault,
    RuntimeEvidenceService,
    RuntimeEvidenceTarget,
)
from gleiswerk.topology import OccupancyZoneId

NOW = datetime(2026, 8, 17, 19, tzinfo=UTC)
ONE = RuntimeEvidenceTarget(OccupancyZoneId("one"), EvidenceSourceId("one-s88"))
TWO = RuntimeEvidenceTarget(OccupancyZoneId("two"), EvidenceSourceId("two-s88"))


def service() -> RuntimeEvidenceService:
    return RuntimeEvidenceService("topology", (ONE, TWO), clock=lambda: NOW)


def evidence(
    target: RuntimeEvidenceTarget, state: OccupancyState, when: datetime = NOW
) -> OccupancyEvidence:
    return OccupancyEvidence(
        target.zone_id,
        "topology",
        target.source_id,
        EvidenceSourceStatus.AVAILABLE,
        when,
        state,
    )


def statuses(sut: RuntimeEvidenceService) -> list[EvidenceSourceStatus]:
    return [item.source_status for item in sut.snapshot()]


def test_startup_is_unknown_until_a_complete_baseline() -> None:
    sut = service()

    assert statuses(sut) == [EvidenceSourceStatus.UNKNOWN] * 2
    sut.accept_update((evidence(ONE, OccupancyState.CLEAR),), 1, NOW)
    assert statuses(sut) == [EvidenceSourceStatus.UNKNOWN] * 2

    sut.accept_baseline(
        (evidence(ONE, OccupancyState.CLEAR), evidence(TWO, OccupancyState.CLEAR)), NOW
    )
    assert statuses(sut) == [EvidenceSourceStatus.AVAILABLE] * 2


def test_incomplete_or_duplicate_baseline_faults_every_target() -> None:
    sut = service()
    sut.accept_baseline((evidence(ONE, OccupancyState.CLEAR),), NOW)

    assert statuses(sut) == [EvidenceSourceStatus.FAULTED] * 2
    assert sut.diagnostics.fault is RuntimeEvidenceFault.INCOMPLETE_BASELINE

    sut.accept_baseline(
        (evidence(ONE, OccupancyState.CLEAR), evidence(TWO, OccupancyState.CLEAR)), NOW
    )
    sut.accept_baseline(
        (evidence(ONE, OccupancyState.CLEAR), evidence(ONE, OccupancyState.OCCUPIED)),
        NOW,
    )
    assert sut.diagnostics.fault is RuntimeEvidenceFault.DUPLICATE_TARGET


def test_updates_need_strict_order_but_proven_redelivery_is_idempotent() -> None:
    sut = service()
    sut.accept_baseline(
        (evidence(ONE, OccupancyState.CLEAR), evidence(TWO, OccupancyState.CLEAR)), NOW
    )
    update = evidence(ONE, OccupancyState.OCCUPIED, NOW + timedelta(seconds=1))
    sut.accept_update((update,), 4, NOW + timedelta(seconds=1))
    sut.accept_update((update,), 4, NOW + timedelta(seconds=2), redelivered=True)
    assert sut.snapshot()[0].state is OccupancyState.OCCUPIED

    sut.accept_update((evidence(TWO, OccupancyState.OCCUPIED),), 4, NOW)
    assert statuses(sut) == [EvidenceSourceStatus.FAULTED] * 2
    assert sut.diagnostics.fault is RuntimeEvidenceFault.UNORDERED_UPDATE


def test_transport_fault_requires_a_new_complete_baseline_and_preserves_age() -> None:
    sut = service()
    old = NOW - timedelta(seconds=31)
    sut.accept_baseline(
        (
            evidence(ONE, OccupancyState.CLEAR, old),
            evidence(TWO, OccupancyState.CLEAR, old),
        ),
        NOW,
    )
    assert (
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)).qualify(
            sut.snapshot()[0].observed_at
        )
        is EvidenceFreshness.STALE
    )
    sut.transport_lost(received_at=NOW)
    faulted_session = sut.diagnostics.session_id
    sut.accept_update((evidence(ONE, OccupancyState.CLEAR),), 5, NOW)
    assert statuses(sut) == [EvidenceSourceStatus.FAULTED] * 2

    sut.accept_baseline(
        (evidence(ONE, OccupancyState.CLEAR), evidence(TWO, OccupancyState.CLEAR)), NOW
    )
    assert statuses(sut) == [EvidenceSourceStatus.AVAILABLE] * 2
    assert sut.diagnostics.session_id == faulted_session + 1
