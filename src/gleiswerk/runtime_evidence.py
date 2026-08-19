"""Supervised, controller-independent runtime occupancy evidence service."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from gleiswerk.evidence import (
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
)
from gleiswerk.topology import OccupancyZoneId


class RuntimeEvidenceFault(StrEnum):
    """Stable reasons a supervised evidence session fails closed."""

    TRANSPORT_LOST = "transport-lost"
    MALFORMED_INPUT = "malformed-input"
    INCOMPLETE_BASELINE = "incomplete-baseline"
    DUPLICATE_TARGET = "duplicate-target"
    UNORDERED_UPDATE = "unordered-update"


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceTarget:
    """One logical occupancy target expected from a runtime source."""

    zone_id: OccupancyZoneId
    source_id: EvidenceSourceId


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceDiagnostics:
    """Controller-independent health and provenance for the current session."""

    topology_revision: str
    session_id: int
    source_status: EvidenceSourceStatus
    source_ids: tuple[EvidenceSourceId, ...]
    received_at: datetime
    fault: RuntimeEvidenceFault | None = None
    detail: str | None = None


Clock = Callable[[], datetime]


@dataclass(slots=True)
class RuntimeEvidenceService:
    """Publish only complete, ordered logical evidence within one session.

    Adapters translate their controller protocol before calling this service.
    The service therefore has no knowledge of frames, addresses, or sockets.
    """

    topology_revision: str
    targets: Iterable[RuntimeEvidenceTarget]
    clock: Clock = lambda: datetime.now(UTC)
    _targets: Mapping[OccupancyZoneId, RuntimeEvidenceTarget] = field(init=False)
    _session_id: int = field(init=False, default=1)
    _status: EvidenceSourceStatus = field(
        init=False, default=EvidenceSourceStatus.UNKNOWN
    )
    _evidence: dict[OccupancyZoneId, OccupancyEvidence] = field(
        init=False,
        default_factory=lambda: dict[OccupancyZoneId, OccupancyEvidence](),
    )
    _last_order: int | None = field(init=False, default=None)
    _last_update: tuple[OccupancyEvidence, ...] | None = field(init=False, default=None)
    _diagnostics: RuntimeEvidenceDiagnostics = field(init=False)

    def __post_init__(self) -> None:
        if not self.topology_revision:
            raise ValueError("topology revision must be nonempty")
        targets = tuple(self.targets)
        indexed = {target.zone_id: target for target in targets}
        if not targets or len(indexed) != len(targets):
            raise ValueError("runtime evidence targets must be nonempty and unique")
        if len({target.source_id for target in targets}) != len(targets):
            raise ValueError("runtime evidence source IDs must be unique")
        self._targets = MappingProxyType(indexed)
        self._diagnostics = self._make_diagnostics(self._now())

    @property
    def diagnostics(self) -> RuntimeEvidenceDiagnostics:
        return self._diagnostics

    def snapshot(self) -> tuple[OccupancyEvidence, ...]:
        """Return every expected target, unavailable unless this session is healthy."""
        now = self._now()
        return tuple(
            self._evidence.get(zone) or self._unavailable(target, now)
            for zone, target in sorted(self._targets.items())
        )

    def accept_baseline(
        self,
        observations: Iterable[OccupancyEvidence],
        received_at: datetime | None = None,
    ) -> tuple[OccupancyEvidence, ...]:
        """Start a fresh available session from one complete logical baseline."""
        now = self._at(received_at)
        values = tuple(observations)
        fault = self._baseline_fault(values)
        if fault is not None:
            self._fault(fault, now)
            return self.snapshot()
        if self._status is EvidenceSourceStatus.FAULTED:
            self._session_id += 1
        self._status = EvidenceSourceStatus.AVAILABLE
        self._evidence = {item.zone_id: item for item in values}
        self._last_order = None
        self._last_update = None
        self._diagnostics = self._make_diagnostics(now)
        return self.snapshot()

    def accept_update(
        self,
        observations: Iterable[OccupancyEvidence],
        order: int,
        received_at: datetime | None = None,
        *,
        redelivered: bool = False,
    ) -> tuple[OccupancyEvidence, ...]:
        """Apply a proven ordered update, otherwise immediately fail closed."""
        now = self._at(received_at)
        values = tuple(observations)
        if self._status is not EvidenceSourceStatus.AVAILABLE:
            return self.snapshot()
        fault = self._update_fault(values)
        if fault is not None:
            self._fault(fault, now)
        elif order == self._last_order and redelivered and values == self._last_update:
            self._diagnostics = self._make_diagnostics(now)
        elif (
            type(order) is not int
            or self._last_order is not None
            and order <= self._last_order
        ):
            self._fault(RuntimeEvidenceFault.UNORDERED_UPDATE, now)
        else:
            self._evidence.update({item.zone_id: item for item in values})
            self._last_order = order
            self._last_update = values
            self._diagnostics = self._make_diagnostics(now)
        return self.snapshot()

    def transport_lost(
        self,
        detail: str = "evidence transport unavailable",
        received_at: datetime | None = None,
    ) -> tuple[OccupancyEvidence, ...]:
        self._fault(RuntimeEvidenceFault.TRANSPORT_LOST, self._at(received_at), detail)
        return self.snapshot()

    def malformed_input(
        self,
        detail: str = "adapter rejected malformed input",
        received_at: datetime | None = None,
    ) -> tuple[OccupancyEvidence, ...]:
        self._fault(RuntimeEvidenceFault.MALFORMED_INPUT, self._at(received_at), detail)
        return self.snapshot()

    def _baseline_fault(
        self, values: tuple[OccupancyEvidence, ...]
    ) -> RuntimeEvidenceFault | None:
        fault = self._update_fault(values)
        if fault is not None:
            return fault
        if len(values) != len(self._targets) or {
            item.zone_id for item in values
        } != set(self._targets):
            return RuntimeEvidenceFault.INCOMPLETE_BASELINE
        return None

    def _update_fault(
        self, values: tuple[OccupancyEvidence, ...]
    ) -> RuntimeEvidenceFault | None:
        zones = [item.zone_id for item in values]
        if len(zones) != len(set(zones)):
            return RuntimeEvidenceFault.DUPLICATE_TARGET
        if not values or not all(
            item.topology_revision == self.topology_revision
            and item.source_status is EvidenceSourceStatus.AVAILABLE
            and self._targets.get(item.zone_id) is not None
            and self._targets[item.zone_id].source_id == item.source_id
            for item in values
        ):
            return RuntimeEvidenceFault.MALFORMED_INPUT
        return None

    def _fault(
        self, fault: RuntimeEvidenceFault, now: datetime, detail: str | None = None
    ) -> None:
        self._status = EvidenceSourceStatus.FAULTED
        self._evidence.clear()
        self._last_order = None
        self._last_update = None
        self._diagnostics = self._make_diagnostics(now, fault, detail)

    def _unavailable(
        self, target: RuntimeEvidenceTarget, observed_at: datetime
    ) -> OccupancyEvidence:
        return OccupancyEvidence(
            target.zone_id,
            self.topology_revision,
            target.source_id,
            self._status,
            observed_at,
        )

    def _make_diagnostics(
        self,
        received_at: datetime,
        fault: RuntimeEvidenceFault | None = None,
        detail: str | None = None,
    ) -> RuntimeEvidenceDiagnostics:
        return RuntimeEvidenceDiagnostics(
            self.topology_revision,
            self._session_id,
            self._status,
            tuple(sorted(target.source_id for target in self._targets.values())),
            received_at,
            fault,
            detail,
        )

    def _now(self) -> datetime:
        return self._at(self.clock())

    @staticmethod
    def _at(value: datetime | None) -> datetime:
        now = datetime.now(UTC) if value is None else value
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("runtime evidence time must be timezone-aware")
        return now
