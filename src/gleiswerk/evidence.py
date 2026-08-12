"""Immutable, controller-independent logical evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import NewType

from gleiswerk.topology import ControlDeviceId, DevicePositionId, OccupancyZoneId

EvidenceSourceId = NewType("EvidenceSourceId", str)
"""A stable logical identity for the source of one observation."""


class EvidenceSourceStatus(StrEnum):
    """Whether a source can currently make a trustworthy observation."""

    AVAILABLE = "available"
    UNKNOWN = "unknown"
    FAULTED = "faulted"


class OccupancyState(StrEnum):
    """A known logical occupancy observation."""

    CLEAR = "clear"
    OCCUPIED = "occupied"


class EvidenceFreshness(StrEnum):
    """The deterministic freshness qualification of an observation."""

    FRESH = "fresh"
    STALE = "stale"


class OccupancyEvidenceOutcome(StrEnum):
    """The complete safety-relevant outcome for one Occupancy Zone."""

    CLEAR = "clear"
    OCCUPIED = "occupied"
    UNKNOWN = "unknown"
    STALE = "stale"
    FAULTED = "faulted"


class DevicePositionEvidenceOutcome(StrEnum):
    """The complete safety-relevant outcome for one required device position."""

    ALIGNED = "aligned"
    UNALIGNED = "unaligned"
    UNKNOWN = "unknown"
    STALE = "stale"
    FAULTED = "faulted"


def _require_aware(value: datetime, description: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{description} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessBasis:
    """One evaluation instant and maximum accepted observation age."""

    evaluated_at: datetime
    maximum_age: timedelta

    def __post_init__(self) -> None:
        _require_aware(self.evaluated_at, "evidence evaluation time")
        if self.maximum_age < timedelta():
            raise ValueError("evidence maximum age must not be negative")

    def qualify(self, observed_at: datetime) -> EvidenceFreshness:
        """Classify an observation without consulting a wall clock implicitly."""

        _require_aware(observed_at, "evidence observation time")
        return (
            EvidenceFreshness.FRESH
            if observed_at >= self.evaluated_at - self.maximum_age
            else EvidenceFreshness.STALE
        )


@dataclass(frozen=True, slots=True)
class OccupancyEvidence:
    """One timestamped logical occupancy observation for one Occupancy Zone."""

    zone_id: OccupancyZoneId
    topology_revision: str
    source_id: EvidenceSourceId
    source_status: EvidenceSourceStatus
    observed_at: datetime
    state: OccupancyState | None = None

    def __post_init__(self) -> None:
        if not self.topology_revision:
            raise ValueError("evidence topology revision must be nonempty")
        if not self.source_id:
            raise ValueError("evidence source ID must be nonempty")
        _require_aware(self.observed_at, "evidence observation time")
        if (self.source_status is EvidenceSourceStatus.AVAILABLE) != (
            self.state is not None
        ):
            raise ValueError(
                "available occupancy evidence requires a state; unavailable evidence cannot declare one"
            )


@dataclass(frozen=True, slots=True)
class DevicePositionEvidence:
    """One timestamped logical position observation for one Control Device."""

    device_id: ControlDeviceId
    topology_revision: str
    source_id: EvidenceSourceId
    source_status: EvidenceSourceStatus
    observed_at: datetime
    position_id: DevicePositionId | None = None

    def __post_init__(self) -> None:
        if not self.topology_revision:
            raise ValueError("evidence topology revision must be nonempty")
        if not self.source_id:
            raise ValueError("evidence source ID must be nonempty")
        _require_aware(self.observed_at, "evidence observation time")
        if (self.source_status is EvidenceSourceStatus.AVAILABLE) != (
            self.position_id is not None
        ):
            raise ValueError(
                "available device evidence requires a position; unavailable evidence cannot declare one"
            )


@dataclass(frozen=True, slots=True)
class OccupancyEvidenceResult:
    """A qualified occupancy outcome with explicit logical provenance."""

    zone_id: OccupancyZoneId
    source_id: EvidenceSourceId
    outcome: OccupancyEvidenceOutcome


@dataclass(frozen=True, slots=True)
class DevicePositionEvidenceResult:
    """A qualified result for one required logical Control Device position."""

    device_id: ControlDeviceId
    required_position_id: DevicePositionId
    source_id: EvidenceSourceId
    outcome: DevicePositionEvidenceOutcome
