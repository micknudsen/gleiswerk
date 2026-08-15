"""Fail-closed Märklin CS3 S88 feedback translation.

This infrastructure adapter accepts decoded S88 observations from its UDP
transport and exposes only controller-independent ``OccupancyEvidence``.
Opening a socket and scheduling polls intentionally remain outside this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from gleiswerk.evidence import (
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyState,
)
from gleiswerk.topology import OccupancyZoneId


@dataclass(frozen=True, slots=True, order=True)
class S88Contact:
    """One installation-defined S88 bus, module, and contact address."""

    bus: int
    module: int
    contact: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (self.bus, self.module, self.contact)
        ):
            raise ValueError("S88 bus, module, and contact must be positive integers")
        if self.contact > 16:
            raise ValueError("S88 contact must be in the range 1 through 16")


@dataclass(frozen=True, slots=True)
class S88OccupancySource:
    """The immutable logical target of one commissioned S88 contact."""

    source_id: EvidenceSourceId
    zone_id: OccupancyZoneId
    contact: S88Contact


@dataclass(frozen=True, slots=True)
class MarklinFeedbackBinding:
    """A validated, revision-matched configuration for one feedback adapter."""

    topology_revision: str
    sources: Mapping[S88Contact, S88OccupancySource]

    def __post_init__(self) -> None:
        if not self.topology_revision:
            raise ValueError("topology revision must be nonempty")
        sources = dict(self.sources)
        if not sources:
            raise ValueError("at least one S88 occupancy source is required")
        if any(key != value.contact for key, value in sources.items()):
            raise ValueError("S88 source keys must match their contact")
        source_ids = [source.source_id for source in sources.values()]
        zones = [source.zone_id for source in sources.values()]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("S88 source IDs must be unique")
        if len(set(zones)) != len(zones):
            raise ValueError("S88 occupancy zones must be unique")
        object.__setattr__(self, "sources", MappingProxyType(sources))


Clock = Callable[[], datetime]

_S88_EVENT_COMMAND = 0x11
_CAN_FRAME_LENGTH = 13


@dataclass(slots=True)
class MarklinCs3S88Adapter:
    """Translate S88 observations while enforcing the ADR 0015 trust state."""

    binding: MarklinFeedbackBinding
    clock: Clock = lambda: datetime.now(UTC)
    _status: EvidenceSourceStatus = field(
        init=False, default=EvidenceSourceStatus.UNKNOWN
    )
    _evidence: dict[S88Contact, OccupancyEvidence] = field(
        init=False, default_factory=lambda: dict[S88Contact, OccupancyEvidence]()
    )
    diagnostics: list[str] = field(init=False, default_factory=lambda: list[str]())

    def snapshot(self) -> tuple[OccupancyEvidence, ...]:
        """Return one deterministic logical evidence value for every binding source."""
        now = self._now()
        return tuple(
            self._evidence[contact]
            if contact in self._evidence
            else self._unavailable(source, now)
            for contact, source in sorted(self.binding.sources.items())
        )

    def receive_poll(
        self,
        observations: Mapping[S88Contact, bool],
        received_at: datetime | None = None,
    ) -> tuple[OccupancyEvidence, ...]:
        """Accept a complete poll, or fault every source if it is incomplete/invalid."""
        now = self._at(received_at)
        if set(observations) != set(self.binding.sources) or any(
            type(value) is not bool for value in observations.values()
        ):
            self._fault("incomplete or invalid S88 poll", now)
            return self.snapshot()
        self._status = EvidenceSourceStatus.AVAILABLE
        self._evidence = {
            contact: self._available(self.binding.sources[contact], active, now)
            for contact, active in observations.items()
        }
        return self.snapshot()

    def receive_event(
        self, contact: S88Contact, active: object, received_at: datetime | None = None
    ) -> tuple[OccupancyEvidence, ...]:
        """Apply one event only after a complete poll has established availability."""
        now = self._at(received_at)
        source = self.binding.sources.get(contact)
        if source is None:
            self.diagnostics.append(f"ignored unmapped S88 contact {contact!r}")
            return self.snapshot()
        if type(active) is not bool:
            self._fault("invalid S88 event value", now)
            return self.snapshot()
        if self._status is EvidenceSourceStatus.AVAILABLE:
            self._evidence[contact] = self._available(source, active, now)
        return self.snapshot()

    def receive_datagram(
        self, datagram: bytes, received_at: datetime | None = None
    ) -> tuple[OccupancyEvidence, ...]:
        """Decode one CS3 UDP S88 event frame or fault the entire adapter.

        The CAN-over-Ethernet frame is 13 bytes: a big-endian CAN identifier,
        one data-length byte, and eight payload bytes.  S88 event payloads use
        a 16-bit bus/device identifier, a one-based global contact number,
        then old and new binary states.  Poll aggregation is deliberately kept
        separate because one requested poll can produce several module frames.
        """
        now = self._at(received_at)
        try:
            contact, active = _decode_s88_event(datagram)
        except ValueError as error:
            self._fault(f"malformed S88 datagram: {error}", now)
            return self.snapshot()
        return self.receive_event(contact, active, now)

    def connection_lost(
        self, detail: str = "S88 gateway unavailable"
    ) -> tuple[OccupancyEvidence, ...]:
        """Fail every source; only a later complete poll can recover it."""
        self._fault(detail, self._now())
        return self.snapshot()

    def malformed_datagram(
        self, detail: str = "malformed S88 datagram"
    ) -> tuple[OccupancyEvidence, ...]:
        """Fail every source when the UDP transport rejects a wire frame."""
        self._fault(detail, self._now())
        return self.snapshot()

    def _fault(self, detail: str, now: datetime) -> None:
        self._status = EvidenceSourceStatus.FAULTED
        self._evidence.clear()
        self.diagnostics.append(detail)

    def _available(
        self, source: S88OccupancySource, active: bool, observed_at: datetime
    ) -> OccupancyEvidence:
        return OccupancyEvidence(
            source.zone_id,
            self.binding.topology_revision,
            source.source_id,
            EvidenceSourceStatus.AVAILABLE,
            observed_at,
            OccupancyState.OCCUPIED if active else OccupancyState.CLEAR,
        )

    def _unavailable(
        self, source: S88OccupancySource, observed_at: datetime
    ) -> OccupancyEvidence:
        return OccupancyEvidence(
            source.zone_id,
            self.binding.topology_revision,
            source.source_id,
            self._status,
            observed_at,
        )

    def _now(self) -> datetime:
        return self._at(self.clock())

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        now = datetime.now(UTC) if value is None else value
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("S88 receipt time must be timezone-aware")
        return now


def _decode_s88_event(datagram: bytes) -> tuple[S88Contact, bool]:
    """Decode the event shape selected by ADR 0014's pinned protocol suite."""
    if len(datagram) != _CAN_FRAME_LENGTH:
        raise ValueError("CAN-over-Ethernet frames must be exactly 13 bytes")
    can_id = int.from_bytes(datagram[:4], "big")
    command = (can_id >> 17) & 0xFF
    response = bool(can_id & (1 << 16))
    length = datagram[4]
    if command != _S88_EVENT_COMMAND or not response or length != 8:
        raise ValueError("expected a complete S88 event response")
    payload = datagram[5:]
    bus = int.from_bytes(payload[:2], "big")
    global_contact = int.from_bytes(payload[2:4], "big")
    old_state, new_state = payload[4:6]
    if (
        bus < 1
        or global_contact < 1
        or old_state not in (0, 1)
        or new_state
        not in (
            0,
            1,
        )
    ):
        raise ValueError("S88 event has unsupported contact or state values")
    module, contact_offset = divmod(global_contact - 1, 16)
    return S88Contact(bus, module + 1, contact_offset + 1), bool(new_state)
