"""Protocol-emulator tests for the fail-closed Märklin S88 adapter."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from gleiswerk.evidence import (
    DevicePositionEvidence,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyState,
)
from gleiswerk.evidence_validation import validate_evidence
from gleiswerk.marklin_feedback import (
    MarklinCs3S88Adapter,
    MarklinCs3S88RuntimeBridge,
    MarklinFeedbackBinding,
    S88Contact,
    S88OccupancySource,
)
from gleiswerk.movement_authority import (
    MovementAuthorityEvaluator,
    MovementAuthorityRequest,
)
from gleiswerk.route_compiler import compile_routes
from gleiswerk.route_reservations import (
    AcquireReservationRequest,
    ReservationManager,
    ReservationOwner,
)
from gleiswerk.runtime_evidence import RuntimeEvidenceService, RuntimeEvidenceTarget
from gleiswerk.topology import (
    ControlDeviceId,
    DevicePositionId,
    OccupancyZoneId,
    RouteDefinitionId,
)
from gleiswerk.topology_config import load_topology

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
ONE = S88Contact(1, 1, 1)
TWO = S88Contact(1, 1, 2)


def adapter() -> MarklinCs3S88Adapter:
    binding = MarklinFeedbackBinding(
        "sha256:topology",
        {
            ONE: S88OccupancySource(
                EvidenceSourceId("platform-one"), OccupancyZoneId("platform-one"), ONE
            ),
            TWO: S88OccupancySource(
                EvidenceSourceId("platform-two"), OccupancyZoneId("platform-two"), TWO
            ),
        },
    )
    return MarklinCs3S88Adapter(binding, clock=lambda: NOW)


def event(contact: S88Contact, old: int, new: int) -> bytes:
    can_id = (0x11 << 17) | (1 << 16)
    global_contact = (contact.module - 1) * 16 + contact.contact
    return (
        can_id.to_bytes(4, "big")
        + bytes([8])
        + contact.bus.to_bytes(2, "big")
        + global_contact.to_bytes(2, "big")
        + bytes([old, new, 0, 0])
    )


def states(
    sut: MarklinCs3S88Adapter,
) -> list[tuple[EvidenceSourceStatus, OccupancyState | None]]:
    return [(item.source_status, item.state) for item in sut.snapshot()]


def test_startup_and_events_before_a_complete_poll_remain_unknown() -> None:
    sut = adapter()

    assert states(sut) == [(EvidenceSourceStatus.UNKNOWN, None)] * 2
    sut.receive_event(ONE, True, NOW)

    assert states(sut) == [(EvidenceSourceStatus.UNKNOWN, None)] * 2


def test_complete_poll_translates_every_contact_to_logical_evidence() -> None:
    sut = adapter()

    evidence = sut.receive_poll({ONE: True, TWO: False}, NOW)

    assert [(item.source_status, item.state) for item in evidence] == [
        (EvidenceSourceStatus.AVAILABLE, OccupancyState.OCCUPIED),
        (EvidenceSourceStatus.AVAILABLE, OccupancyState.CLEAR),
    ]
    assert all(item.observed_at == NOW for item in evidence)


def test_event_updates_only_its_mapped_source_and_duplicate_refreshes_receipt_time() -> (
    None
):
    sut = adapter()
    sut.receive_poll({ONE: False, TWO: False}, NOW)

    later = NOW + timedelta(seconds=1)
    sut.receive_event(ONE, False, later)
    evidence = sut.snapshot()

    assert evidence[0].observed_at == later
    assert evidence[1].observed_at == NOW


def test_protocol_emulator_decodes_a_cs3_udp_event() -> None:
    sut = adapter()
    sut.receive_poll({ONE: False, TWO: False}, NOW)

    evidence = sut.receive_datagram(event(ONE, 0, 1), NOW + timedelta(seconds=1))

    assert evidence[0].state is OccupancyState.OCCUPIED
    assert evidence[0].observed_at == NOW + timedelta(seconds=1)


def test_invalid_direct_event_value_faults_every_source() -> None:
    sut = adapter()
    sut.receive_poll({ONE: True, TWO: False}, NOW)

    sut.receive_event(ONE, 1, NOW)

    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2


def test_partial_poll_malformed_input_and_disconnect_fault_every_source() -> None:
    sut = adapter()
    sut.receive_poll({ONE: True}, NOW)
    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2

    sut.receive_poll({ONE: True, TWO: False}, NOW)
    sut.malformed_datagram()
    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2

    sut.receive_poll({ONE: True, TWO: False}, NOW)
    sut.receive_datagram(b"malformed", NOW)
    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2

    sut.receive_poll({ONE: True, TWO: False}, NOW)
    sut.connection_lost()
    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2


def test_only_a_complete_poll_can_recover_a_fault_and_unmapped_input_is_ignored() -> (
    None
):
    sut = adapter()
    sut.connection_lost()
    sut.receive_event(ONE, True, NOW)
    sut.receive_event(S88Contact(1, 2, 1), True, NOW)

    assert states(sut) == [(EvidenceSourceStatus.FAULTED, None)] * 2
    assert "ignored unmapped" in sut.diagnostics[-1]

    sut.receive_poll({ONE: True, TWO: False}, NOW)
    assert states(sut)[0] == (EvidenceSourceStatus.AVAILABLE, OccupancyState.OCCUPIED)


def test_adapter_evidence_drives_read_only_authority_evaluation() -> None:
    topology = load_topology(Path("tests/fixtures/schema_v3/valid-occupancy.yaml"))
    plan = compile_routes(topology)[RouteDefinitionId("west-to-main")]
    binding = MarklinFeedbackBinding(
        topology.revision,
        {
            ONE: S88OccupancySource(
                EvidenceSourceId("throat-s88"),
                OccupancyZoneId("throat-detector"),
                ONE,
            ),
            TWO: S88OccupancySource(
                EvidenceSourceId("main-s88"), OccupancyZoneId("main-detector"), TWO
            ),
        },
    )
    adapter = MarklinCs3S88Adapter(binding, clock=lambda: NOW)
    reservations = ReservationManager(topology)
    reservation = reservations.acquire(
        AcquireReservationRequest(ReservationOwner("dispatcher"), plan)
    ).reservation
    assert reservation is not None
    evaluator = MovementAuthorityEvaluator(
        topology.revision, timedelta(seconds=30), lambda: 0
    )
    position = DevicePositionEvidence(
        ControlDeviceId("throat-turnout"),
        topology.revision,
        EvidenceSourceId("turnout-sensor"),
        EvidenceSourceStatus.AVAILABLE,
        NOW,
        DevicePositionId("normal"),
    )

    adapter.receive_poll({ONE: False, TWO: False}, NOW)
    evidence = validate_evidence(
        topology,
        plan,
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)),
        adapter.snapshot(),
        (position,),
    )
    granted = evaluator.evaluate(
        MovementAuthorityRequest(
            ReservationOwner("dispatcher"),
            reservation.id,
            evidence,
            timedelta(seconds=20),
        ),
        reservations.inspect(),
    )

    assert granted.outcome == "granted"
    assert granted.authority is not None
    adapter.receive_event(ONE, True, NOW)
    rejected = validate_evidence(
        topology,
        plan,
        EvidenceFreshnessBasis(NOW, timedelta(seconds=30)),
        adapter.snapshot(),
        (position,),
    )
    revoked = evaluator.reevaluate(
        granted.authority.id, reservations.inspect(), rejected
    )

    assert [(item.kind.value, item.source_ids) for item in rejected.rejections] == [
        ("occupied", ("throat-s88",))
    ]
    assert revoked.outcome == "revoked"
    assert revoked.authority is not None
    assert revoked.authority.revocation is not None
    assert revoked.authority.revocation.evidence_rejection is not None
    assert revoked.authority.revocation.evidence_rejection.source_ids == ("throat-s88",)


def test_runtime_bridge_keeps_cs3_ordering_at_the_adapter_edge() -> None:
    translator = adapter()
    service = RuntimeEvidenceService(
        translator.binding.topology_revision,
        tuple(
            RuntimeEvidenceTarget(source.zone_id, source.source_id)
            for source in translator.binding.sources.values()
        ),
        clock=lambda: NOW,
    )
    bridge = MarklinCs3S88RuntimeBridge(translator, service)

    bridge.receive_poll({ONE: False, TWO: False}, NOW)
    bridge.receive_event(ONE, True, 1, NOW + timedelta(seconds=1))

    assert service.snapshot()[0].state is OccupancyState.OCCUPIED
    bridge.connection_lost(received_at=NOW + timedelta(seconds=2))
    assert states(translator) == [(EvidenceSourceStatus.FAULTED, None)] * 2
    assert [item.source_status for item in service.snapshot()] == [
        EvidenceSourceStatus.FAULTED,
        EvidenceSourceStatus.FAULTED,
    ]
