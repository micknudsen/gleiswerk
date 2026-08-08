"""Deterministic compilation of schema-v3 route intent into immutable plans."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from gleiswerk.topology import (
    ClaimContribution,
    ClaimResource,
    ConnectionPathElement,
    ControlDeviceId,
    DeviceRequirement,
    JunctionPassagePathElement,
    JunctionPort,
    JunctionResource,
    PathElement,
    PortReference,
    ProtectionZoneResource,
    RequirementContribution,
    RouteDefinition,
    RouteDefinitionId,
    RoutePlan,
    Topology,
    TrackSectionPathElement,
    TrackSectionPort,
    TrackSectionResource,
)


@dataclass(slots=True)
class RouteCompilationError(Exception):
    """A stable route-definition compilation failure."""

    code: str
    route_id: RouteDefinitionId
    message: str
    via_index: int | None = None

    @property
    def path(self) -> str:
        path = f"route-definitions.{self.route_id}"
        return f"{path}.via[{self.via_index}]" if self.via_index is not None else path

    def __str__(self) -> str:
        return f"{self.code} {self.path}: {self.message}"


def compile_route(topology: Topology, route_id: RouteDefinitionId) -> RoutePlan:
    """Compile one validated Route Definition against this exact topology revision."""

    route = topology.route_definitions[route_id]
    paths = _terminal_paths(topology, route)
    matching = [path for path in paths if _constraints_match(path, route.via)]
    if not matching:
        if paths:
            raise RouteCompilationError(
                "E403", route.id, "route constraints are absent from or out of order"
            )
        raise RouteCompilationError(
            "E400", route.id, "no path satisfies route definition"
        )
    nonrepeating = [
        path for path in matching if not _revisits_physical_resource(path, topology)
    ]
    if len(nonrepeating) > 1:
        raise RouteCompilationError(
            "E401", route.id, "more than one path satisfies route definition"
        )
    if not nonrepeating:
        raise RouteCompilationError(
            "E402", route.id, "selected route revisits a physical resource"
        )
    return _build_plan(topology, route, nonrepeating[0])


def compile_routes(topology: Topology) -> Mapping[RouteDefinitionId, RoutePlan]:
    """Compile every Route Definition in stable identifier order."""

    return MappingProxyType(
        {
            route_id: compile_route(topology, route_id)
            for route_id in sorted(topology.route_definitions)
        }
    )


def _terminal_paths(
    topology: Topology, route: RouteDefinition
) -> list[tuple[PathElement, ...]]:
    edges = _edges(topology)
    results: list[tuple[PathElement, ...]] = []

    def visit(
        port: PortReference,
        path: tuple[PathElement, ...],
        used: tuple[tuple[PortReference, PortReference, PathElement], ...],
        needs_local_movement: bool,
    ) -> None:
        if path and not needs_local_movement and port == route.exit:
            results.append(path)
            if _constraints_match(path, route.via):
                return
        for destination, element, is_local_movement in edges[port]:
            if is_local_movement != needs_local_movement:
                continue
            edge = (port, destination, element)
            if used.count(edge) < 2:
                visit(
                    destination,
                    path + (element,),
                    used + (edge,),
                    not needs_local_movement,
                )

    visit(route.entry, (), (), True)
    return results


def _edges(
    topology: Topology,
) -> Mapping[PortReference, tuple[tuple[PortReference, PathElement, bool], ...]]:
    edges: defaultdict[PortReference, list[tuple[PortReference, PathElement, bool]]] = (
        defaultdict(list)
    )
    for section_id, section in topology.track_sections.items():
        for movement in section.movements:
            origin = TrackSectionPort(section_id, movement.from_port)
            destination = TrackSectionPort(section_id, movement.to_port)
            edges[origin].append(
                (
                    destination,
                    TrackSectionPathElement(
                        section_id, movement.from_port, movement.to_port
                    ),
                    True,
                )
            )
    for passage_id, passage in topology.junction_passages.items():
        origin = JunctionPort(passage.junction_id, passage.from_port)
        destination = JunctionPort(passage.junction_id, passage.to_port)
        edges[origin].append(
            (destination, JunctionPassagePathElement(passage_id), True)
        )
    for connection_id, connection in topology.connections.items():
        for movement in connection.movements:
            edges[movement.from_port].append(
                (
                    movement.to_port,
                    ConnectionPathElement(
                        connection_id, movement.from_port, movement.to_port
                    ),
                    False,
                )
            )
    return MappingProxyType(
        {
            port: tuple(sorted(items, key=lambda item: _element_key(item[1])))
            for port, items in edges.items()
        }
    )


def _element_key(element: PathElement) -> tuple[str, str, str, str]:
    if isinstance(element, TrackSectionPathElement):
        return ("track-section", element.id, element.from_port, element.to_port)
    if isinstance(element, ConnectionPathElement):
        return ("connection", element.id, str(element.from_port), str(element.to_port))
    return ("junction-passage", element.id, "", "")


def _constraints_match(
    path: tuple[PathElement, ...], constraints: tuple[str, ...]
) -> bool:
    next_constraint = 0
    for element in path:
        if next_constraint < len(constraints) and _matches_constraint(
            element, constraints[next_constraint]
        ):
            next_constraint += 1
    return next_constraint == len(constraints)


def _matches_constraint(element: PathElement, constraint: str) -> bool:
    kind, identifier = constraint.split(":", 1)
    return _element_key(element)[:2] == (kind, identifier)


def _revisits_physical_resource(
    path: tuple[PathElement, ...], topology: Topology
) -> bool:
    resources = [_physical_claim(element, topology) for element in path]
    physical = [resource for resource in resources if resource is not None]
    return len(physical) != len(set(physical))


def _build_plan(
    topology: Topology, route: RouteDefinition, path: tuple[PathElement, ...]
) -> RoutePlan:
    claim_sources: defaultdict[ClaimResource, list[ClaimContribution]] = defaultdict(
        list
    )
    requirements: dict[ControlDeviceId, DeviceRequirement] = {}
    requirement_sources: defaultdict[ControlDeviceId, list[RequirementContribution]] = (
        defaultdict(list)
    )

    def add_requirement(requirement: DeviceRequirement, source: str) -> None:
        existing = requirements.get(requirement.device_id)
        if existing is not None and existing.position_id != requirement.position_id:
            raise RouteCompilationError(
                "E404", route.id, "effective control device requirements contradict"
            )
        requirements[requirement.device_id] = requirement
        requirement_sources[requirement.device_id].append(
            RequirementContribution(source)
        )

    for element in path:
        source = _path_source(element)
        resource = _physical_claim(element, topology)
        if resource is not None:
            claim_sources[resource].append(ClaimContribution(source))
        if isinstance(element, JunctionPassagePathElement):
            for requirement in topology.junction_passages[element.id].requirements:
                add_requirement(requirement, source)

    for rule_id, rule in topology.protection_rules.items():
        if _rule_applies(rule.trigger, route, path):
            source = f"protection-rule:{rule_id}"
            for claim in rule.claims:
                claim_sources[ProtectionZoneResource(claim)].append(
                    ClaimContribution(source)
                )
            for requirement in rule.requirements:
                add_requirement(requirement, source)

    claims = tuple(sorted(claim_sources, key=_claim_key))
    ordered_requirements = tuple(
        requirements[device] for device in sorted(requirements)
    )
    plan = RoutePlan(
        route.id,
        topology.revision,
        path,
        claims,
        ordered_requirements,
        MappingProxyType(
            {
                claim: tuple(sources)
                for claim, sources in sorted(
                    claim_sources.items(), key=lambda item: _claim_key(item[0])
                )
            }
        ),
        MappingProxyType(
            {
                device: tuple(requirement_sources[device])
                for device in sorted(requirement_sources)
            }
        ),
    )
    _audit(plan, topology, route)
    return plan


def _physical_claim(element: PathElement, topology: Topology) -> ClaimResource | None:
    if isinstance(element, TrackSectionPathElement):
        return TrackSectionResource(element.id)
    if isinstance(element, JunctionPassagePathElement):
        return JunctionResource(topology.junction_passages[element.id].junction_id)
    return None


def _path_source(element: PathElement) -> str:
    kind, identifier, *_ = _element_key(element)
    return f"{kind}:{identifier}"


def _claim_key(claim: ClaimResource) -> tuple[str, str]:
    if isinstance(claim, TrackSectionResource):
        return ("track-section", claim.id)
    if isinstance(claim, JunctionResource):
        return ("junction", claim.id)
    return ("protection-zone", claim.id)


def _rule_applies(
    trigger: Mapping[str, str], route: RouteDefinition, path: tuple[PathElement, ...]
) -> bool:
    kind = trigger["kind"]
    if kind == "route-definition":
        return trigger["id"] == route.id
    if kind == "route-boundary":
        return trigger["route"] == route.id
    if kind == "junction-passage":
        return any(
            isinstance(element, JunctionPassagePathElement)
            and element.id == trigger["id"]
            for element in path
        )
    return any(_movement_matches_trigger(element, trigger) for element in path)


def _movement_matches_trigger(element: PathElement, trigger: Mapping[str, str]) -> bool:
    if trigger["kind"] == "track-section" and isinstance(
        element, TrackSectionPathElement
    ):
        return (
            element.id == trigger["id"]
            and element.from_port == trigger["from"]
            and element.to_port == trigger["to"]
        )
    if trigger["kind"] == "connection" and isinstance(element, ConnectionPathElement):
        return (
            element.id == trigger["id"]
            and _port_reference_string(element.from_port) == trigger["from"]
            and _port_reference_string(element.to_port) == trigger["to"]
        )
    return False


def _port_reference_string(port: PortReference) -> str:
    kind = "track-section" if isinstance(port, TrackSectionPort) else "junction"
    return f"{kind}:{port.owner_id}:{port.id}"


def _audit(plan: RoutePlan, topology: Topology, route: RouteDefinition) -> None:
    expected = {
        resource
        for element in plan.path
        if (resource := _physical_claim(element, topology)) is not None
    }
    if not expected <= set(plan.claims) or any(
        not sources for sources in plan.claim_provenance.values()
    ):
        raise RouteCompilationError(
            "E405", route.id, "compiled plan claim audit failed"
        )
    if any(not sources for sources in plan.requirement_provenance.values()):
        raise RouteCompilationError(
            "E405", route.id, "compiled plan requirement audit failed"
        )
