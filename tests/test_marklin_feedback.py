"""Protocol-emulator tests for the fail-closed Märklin S88 adapter."""

from datetime import UTC, datetime, timedelta

from gleiswerk.evidence import EvidenceSourceId, EvidenceSourceStatus, OccupancyState
from gleiswerk.marklin_feedback import (
    MarklinCs3S88Adapter,
    MarklinFeedbackBinding,
    S88Contact,
    S88OccupancySource,
)
from gleiswerk.topology import OccupancyZoneId

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
