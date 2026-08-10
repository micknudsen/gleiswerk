"""Static, deterministic compatibility analysis for compiled route plans."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeAlias

from gleiswerk.topology import (
    ClaimContribution,
    ClaimResource,
    ControlDeviceId,
    JunctionResource,
    RequirementContribution,
    RouteDefinitionId,
    RoutePlan,
    TrackSectionResource,
)

ConflictKind: TypeAlias = Literal[
    "incompatible-control-device-requirement", "overlapping-exclusive-claim"
]


@dataclass(frozen=True, slots=True)
class OverlappingExclusiveClaim:
    """One shared exclusive claim, with its complete plan provenance."""

    resource: ClaimResource
    provenance: Mapping[RouteDefinitionId, tuple[str, ...]]
    kind: Literal["overlapping-exclusive-claim"] = "overlapping-exclusive-claim"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provenance",
            MappingProxyType(
                {
                    route_id: tuple(sources)
                    for route_id, sources in self.provenance.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class IncompatibleControlDeviceRequirement:
    """One Control Device required in different positions by two plans."""

    control_device: ControlDeviceId
    required_positions: Mapping[RouteDefinitionId, str]
    provenance: Mapping[RouteDefinitionId, tuple[str, ...]]
    kind: Literal["incompatible-control-device-requirement"] = (
        "incompatible-control-device-requirement"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "required_positions", MappingProxyType(dict(self.required_positions))
        )
        object.__setattr__(
            self,
            "provenance",
            MappingProxyType(
                {
                    route_id: tuple(sources)
                    for route_id, sources in self.provenance.items()
                }
            ),
        )


CompatibilityConflict: TypeAlias = (
    OverlappingExclusiveClaim | IncompatibleControlDeviceRequirement
)


@dataclass(frozen=True, slots=True)
class PairCompatibilityResult:
    """The explicit compatibility result for one unordered pair of route plans."""

    route_pair: tuple[RouteDefinitionId, RouteDefinitionId]
    conflicts: tuple[CompatibilityConflict, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_pair", tuple(self.route_pair))
        object.__setattr__(self, "conflicts", tuple(self.conflicts))

    @property
    def compatible(self) -> bool:
        """Whether this pair has no static conflicts."""

        return not self.conflicts


@dataclass(frozen=True, slots=True)
class CompatibilityAnalysisResult:
    """Compatibility results for every unordered pair of input route plans."""

    topology_revision: str
    pairs: tuple[PairCompatibilityResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pairs", tuple(self.pairs))


def analyze_route_plans(plans: Iterable[RoutePlan]) -> CompatibilityAnalysisResult:
    """Compare validated plans from one topology revision in canonical order.

    The input must contain at least two plans with distinct route IDs, all compiled
    from the same topology revision. Violating either precondition is a caller
    error and raises ``ValueError``.
    """

    input_plans = tuple(plans)
    if len(input_plans) < 2:
        raise ValueError("compatibility analysis requires at least two route plans")
    plans_by_route = {plan.route_id: plan for plan in input_plans}
    if len(plans_by_route) != len(input_plans):
        raise ValueError("compatibility analysis requires unique route definition IDs")

    revisions = {plan.topology_revision for plan in input_plans}
    if len(revisions) != 1:
        raise ValueError("compatibility analysis requires one topology revision")

    ordered_plans = tuple(sorted(input_plans, key=lambda plan: plan.route_id))
    pairs = tuple(
        _analyze_pair(left, right)
        for index, left in enumerate(ordered_plans)
        for right in ordered_plans[index + 1 :]
    )
    return CompatibilityAnalysisResult(next(iter(revisions)), pairs)


def analyze_compatibility(plans: Iterable[RoutePlan]) -> CompatibilityAnalysisResult:
    """Alias for :func:`analyze_route_plans`."""

    return analyze_route_plans(plans)


def _analyze_pair(left: RoutePlan, right: RoutePlan) -> PairCompatibilityResult:
    route_pair = (left.route_id, right.route_id)
    left_claims = set(left.claims)
    right_claims = set(right.claims)
    claim_conflicts = tuple(
        OverlappingExclusiveClaim(
            resource,
            _provenance_pair(
                route_pair,
                left.claim_provenance[resource],
                right.claim_provenance[resource],
            ),
        )
        for resource in sorted(left_claims & right_claims, key=_claim_key)
    )

    left_requirements = {item.device_id: item for item in left.requirements}
    right_requirements = {item.device_id: item for item in right.requirements}
    requirement_conflicts = tuple(
        IncompatibleControlDeviceRequirement(
            device,
            MappingProxyType(
                {
                    left.route_id: left_requirements[device].position_id,
                    right.route_id: right_requirements[device].position_id,
                }
            ),
            _provenance_pair(
                route_pair,
                left.requirement_provenance[device],
                right.requirement_provenance[device],
            ),
        )
        for device in sorted(set(left_requirements) & set(right_requirements))
        if left_requirements[device].position_id
        != right_requirements[device].position_id
    )
    conflicts = tuple(
        sorted(
            claim_conflicts + requirement_conflicts,
            key=_conflict_key,
        )
    )
    return PairCompatibilityResult(route_pair, conflicts)


def _provenance_pair(
    route_pair: tuple[RouteDefinitionId, RouteDefinitionId],
    left: Iterable[ClaimContribution | RequirementContribution],
    right: Iterable[ClaimContribution | RequirementContribution],
) -> Mapping[RouteDefinitionId, tuple[str, ...]]:
    return MappingProxyType(
        {
            route_pair[0]: tuple(sorted(item.source for item in left)),
            route_pair[1]: tuple(sorted(item.source for item in right)),
        }
    )


def _claim_key(claim: ClaimResource) -> tuple[str, str]:
    if isinstance(claim, TrackSectionResource):
        return ("track-section", claim.id)
    if isinstance(claim, JunctionResource):
        return ("junction", claim.id)
    return ("protection-zone", claim.id)


def _conflict_key(conflict: CompatibilityConflict) -> tuple[str, str, str]:
    if isinstance(conflict, OverlappingExclusiveClaim):
        return (conflict.kind, *_claim_key(conflict.resource))
    return (conflict.kind, conflict.control_device, "")
