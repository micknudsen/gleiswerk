"""Deterministic validation of logical evidence for one compiled RoutePlan."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from gleiswerk.evidence import (
    DevicePositionEvidence,
    DevicePositionEvidenceOutcome,
    DevicePositionEvidenceResult,
    EvidenceFreshness,
    EvidenceFreshnessBasis,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyEvidenceOutcome,
    OccupancyEvidenceResult,
    OccupancyState,
)
from gleiswerk.topology import (
    ControlDeviceId,
    DeviceRequirement,
    JunctionResource,
    OccupancyExtent,
    OccupancyZoneId,
    PhysicalResource,
    RoutePlan,
    Topology,
    TrackSectionResource,
)


class EvidenceRejectionKind(StrEnum):
    """A stable reason that evidence cannot support a movement prerequisite."""

    REVISION_MISMATCH = "revision-mismatch"
    UNKNOWN_OCCUPANCY_ZONE = "unknown-occupancy-zone"
    UNKNOWN_CONTROL_DEVICE = "unknown-control-device"
    DUPLICATE_OCCUPANCY_EVIDENCE = "duplicate-occupancy-evidence"
    DUPLICATE_DEVICE_EVIDENCE = "duplicate-device-evidence"
    MISSING_OCCUPANCY_COVERAGE = "missing-occupancy-coverage"
    AMBIGUOUS_OCCUPANCY_COVERAGE = "ambiguous-occupancy-coverage"
    MISSING_OCCUPANCY_EVIDENCE = "missing-occupancy-evidence"
    MISSING_DEVICE_EVIDENCE = "missing-device-evidence"
    OCCUPIED = "occupied"
    UNALIGNED = "unaligned"
    UNKNOWN = "unknown"
    STALE = "stale"
    FAULTED = "faulted"


@dataclass(frozen=True, slots=True)
class EvidenceRejection:
    """One failed prerequisite, retaining logical target and source provenance."""

    kind: EvidenceRejectionKind
    target: str
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", tuple(sorted(self.source_ids)))


@dataclass(frozen=True, slots=True)
class EvidenceValidationResult:
    """Immutable, explainable outcome of validating evidence for a RoutePlan."""

    topology_revision: str
    plan_route_id: str
    plan_topology_revision: str
    occupancy_results: tuple[OccupancyEvidenceResult, ...]
    device_position_results: tuple[DevicePositionEvidenceResult, ...]
    rejections: tuple[EvidenceRejection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "occupancy_results",
            tuple(sorted(self.occupancy_results, key=lambda result: result.zone_id)),
        )
        object.__setattr__(
            self,
            "device_position_results",
            tuple(
                sorted(
                    self.device_position_results,
                    key=lambda result: (result.device_id, result.required_position_id),
                )
            ),
        )
        object.__setattr__(
            self,
            "rejections",
            tuple(
                sorted(
                    self.rejections,
                    key=lambda rejection: (
                        rejection.kind,
                        rejection.target,
                        rejection.source_ids,
                    ),
                )
            ),
        )

    @property
    def is_usable(self) -> bool:
        """Whether every prerequisite is complete, fresh, known, and safe."""

        return not self.rejections


def validate_evidence(
    topology: Topology,
    plan: RoutePlan,
    freshness: EvidenceFreshnessBasis,
    occupancy_evidence: Iterable[OccupancyEvidence] = (),
    device_position_evidence: Iterable[DevicePositionEvidence] = (),
) -> EvidenceValidationResult:
    """Fail closed unless evidence completely supports this exact RoutePlan.

    Evaluation is entirely logical: occupancy is selected through declared
    Occupancy Zones and device observations are compared with RoutePlan
    requirements.  Input order cannot change the resulting value.
    """

    occupancies = tuple(occupancy_evidence)
    devices = tuple(device_position_evidence)
    rejections: list[EvidenceRejection] = []
    occupancy_results: list[OccupancyEvidenceResult] = []
    device_results: list[DevicePositionEvidenceResult] = []

    if plan.topology_revision != topology.revision:
        rejections.append(
            EvidenceRejection(
                EvidenceRejectionKind.REVISION_MISMATCH,
                f"route-plan:{plan.route_id}",
                (plan.topology_revision,),
            )
        )

    occupancy_by_zone = _index_occupancies(topology, occupancies, rejections)
    device_by_id = _index_devices(topology, devices, rejections)
    evaluated_zones: set[OccupancyZoneId] = set()

    for resource in _physical_claims(plan):
        zones = _complete_zones_for(topology, resource)
        target = _resource_target(resource)
        if not zones:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.MISSING_OCCUPANCY_COVERAGE, target
                )
            )
            continue
        if len(zones) > 1:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.AMBIGUOUS_OCCUPANCY_COVERAGE,
                    target,
                    tuple(str(zone) for zone in zones),
                )
            )
            continue
        zone = zones[0]
        if zone in evaluated_zones:
            continue
        evaluated_zones.add(zone)
        observation = occupancy_by_zone.get(zone)
        if observation is None:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.MISSING_OCCUPANCY_EVIDENCE, str(zone)
                )
            )
            continue
        outcome = _occupancy_outcome(observation, freshness)
        occupancy_results.append(
            OccupancyEvidenceResult(zone, observation.source_id, outcome)
        )
        _reject_outcome(rejections, outcome, str(zone), str(observation.source_id))

    for requirement in sorted(plan.requirements, key=lambda item: item.device_id):
        observation = device_by_id.get(requirement.device_id)
        if observation is None:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.MISSING_DEVICE_EVIDENCE,
                    str(requirement.device_id),
                )
            )
            continue
        outcome = _device_outcome(observation, requirement, freshness)
        device_results.append(
            DevicePositionEvidenceResult(
                requirement.device_id,
                requirement.position_id,
                observation.source_id,
                outcome,
            )
        )
        _reject_outcome(
            rejections, outcome, str(requirement.device_id), str(observation.source_id)
        )

    return EvidenceValidationResult(
        topology.revision,
        str(plan.route_id),
        plan.topology_revision,
        tuple(occupancy_results),
        tuple(device_results),
        tuple(rejections),
    )


def _index_occupancies(
    topology: Topology,
    evidence: tuple[OccupancyEvidence, ...],
    rejections: list[EvidenceRejection],
) -> dict[OccupancyZoneId, OccupancyEvidence]:
    grouped: defaultdict[OccupancyZoneId, list[OccupancyEvidence]] = defaultdict(list)
    for observation in evidence:
        if observation.topology_revision != topology.revision:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.REVISION_MISMATCH,
                    str(observation.zone_id),
                    (str(observation.source_id),),
                )
            )
        if observation.zone_id not in topology.occupancy_zones:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.UNKNOWN_OCCUPANCY_ZONE,
                    str(observation.zone_id),
                    (str(observation.source_id),),
                )
            )
            continue
        grouped[observation.zone_id].append(observation)
    indexed: dict[OccupancyZoneId, OccupancyEvidence] = {}
    for zone, observations in grouped.items():
        if len(observations) != 1:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.DUPLICATE_OCCUPANCY_EVIDENCE,
                    str(zone),
                    tuple(str(item.source_id) for item in observations),
                )
            )
            continue
        indexed[zone] = observations[0]
    return indexed


def _index_devices(
    topology: Topology,
    evidence: tuple[DevicePositionEvidence, ...],
    rejections: list[EvidenceRejection],
) -> dict[ControlDeviceId, DevicePositionEvidence]:
    grouped: defaultdict[ControlDeviceId, list[DevicePositionEvidence]] = defaultdict(
        list
    )
    for observation in evidence:
        if observation.topology_revision != topology.revision:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.REVISION_MISMATCH,
                    str(observation.device_id),
                    (str(observation.source_id),),
                )
            )
        if observation.device_id not in topology.control_devices:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.UNKNOWN_CONTROL_DEVICE,
                    str(observation.device_id),
                    (str(observation.source_id),),
                )
            )
            continue
        grouped[observation.device_id].append(observation)
    indexed: dict[ControlDeviceId, DevicePositionEvidence] = {}
    for device_id, observations in grouped.items():
        if len(observations) != 1:
            rejections.append(
                EvidenceRejection(
                    EvidenceRejectionKind.DUPLICATE_DEVICE_EVIDENCE,
                    str(device_id),
                    tuple(str(item.source_id) for item in observations),
                )
            )
            continue
        indexed[device_id] = observations[0]
    return indexed


def _physical_claims(plan: RoutePlan) -> tuple[PhysicalResource, ...]:
    return tuple(
        claim
        for claim in plan.claims
        if isinstance(claim, (TrackSectionResource, JunctionResource))
    )


def _complete_zones_for(
    topology: Topology, resource: PhysicalResource
) -> list[OccupancyZoneId]:
    zones: list[OccupancyZoneId] = []
    for zone_id, zone in topology.occupancy_zones.items():
        if any(
            coverage.resource == resource
            and coverage.extent is OccupancyExtent.COMPLETE
            for coverage in zone.coverage
        ):
            zones.append(zone_id)
    return sorted(zones)


def _resource_target(resource: PhysicalResource) -> str:
    kind = "track-section" if isinstance(resource, TrackSectionResource) else "junction"
    return f"{kind}:{resource.id}"


def _occupancy_outcome(
    observation: OccupancyEvidence, freshness: EvidenceFreshnessBasis
) -> OccupancyEvidenceOutcome:
    if observation.source_status is EvidenceSourceStatus.FAULTED:
        return OccupancyEvidenceOutcome.FAULTED
    if observation.source_status is EvidenceSourceStatus.UNKNOWN:
        return OccupancyEvidenceOutcome.UNKNOWN
    if freshness.qualify(observation.observed_at) is EvidenceFreshness.STALE:
        return OccupancyEvidenceOutcome.STALE
    return (
        OccupancyEvidenceOutcome.CLEAR
        if observation.state is OccupancyState.CLEAR
        else OccupancyEvidenceOutcome.OCCUPIED
    )


def _device_outcome(
    observation: DevicePositionEvidence,
    requirement: DeviceRequirement,
    freshness: EvidenceFreshnessBasis,
) -> DevicePositionEvidenceOutcome:
    if observation.source_status is EvidenceSourceStatus.FAULTED:
        return DevicePositionEvidenceOutcome.FAULTED
    if observation.source_status is EvidenceSourceStatus.UNKNOWN:
        return DevicePositionEvidenceOutcome.UNKNOWN
    if freshness.qualify(observation.observed_at) is EvidenceFreshness.STALE:
        return DevicePositionEvidenceOutcome.STALE
    return (
        DevicePositionEvidenceOutcome.ALIGNED
        if observation.position_id == requirement.position_id
        else DevicePositionEvidenceOutcome.UNALIGNED
    )


def _reject_outcome(
    rejections: list[EvidenceRejection],
    outcome: OccupancyEvidenceOutcome | DevicePositionEvidenceOutcome,
    target: str,
    source_id: str,
) -> None:
    kinds = {
        OccupancyEvidenceOutcome.OCCUPIED: EvidenceRejectionKind.OCCUPIED,
        DevicePositionEvidenceOutcome.UNALIGNED: EvidenceRejectionKind.UNALIGNED,
        OccupancyEvidenceOutcome.UNKNOWN: EvidenceRejectionKind.UNKNOWN,
        DevicePositionEvidenceOutcome.UNKNOWN: EvidenceRejectionKind.UNKNOWN,
        OccupancyEvidenceOutcome.STALE: EvidenceRejectionKind.STALE,
        DevicePositionEvidenceOutcome.STALE: EvidenceRejectionKind.STALE,
        OccupancyEvidenceOutcome.FAULTED: EvidenceRejectionKind.FAULTED,
        DevicePositionEvidenceOutcome.FAULTED: EvidenceRejectionKind.FAULTED,
    }
    kind = kinds.get(outcome)
    if kind is not None:
        rejections.append(EvidenceRejection(kind, target, (source_id,)))
