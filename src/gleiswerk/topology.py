"""Immutable, controller-independent schema-version 3 topology values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

ConnectionId = NewType("ConnectionId", str)
ControlDeviceId = NewType("ControlDeviceId", str)
DevicePositionId = NewType("DevicePositionId", str)
JunctionId = NewType("JunctionId", str)
JunctionPassageId = NewType("JunctionPassageId", str)
OccupancyZoneId = NewType("OccupancyZoneId", str)
PortId = NewType("PortId", str)
ProtectionZoneId = NewType("ProtectionZoneId", str)
RouteDefinitionId = NewType("RouteDefinitionId", str)
TrackSectionId = NewType("TrackSectionId", str)


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _require_identifier(value: str, description: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{description} must be a lowercase kebab-case identifier")


def _require_unique(values: tuple[object, ...], description: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{description} must be distinct")


@dataclass(frozen=True, slots=True)
class TrackSectionPort:
    """A port owned by a claimable linear track section."""

    owner_id: TrackSectionId
    id: PortId

    def __post_init__(self) -> None:
        _require_identifier(self.owner_id, "track section ID")
        _require_identifier(self.id, "port ID")


@dataclass(frozen=True, slots=True)
class JunctionPort:
    """A port owned by a claimable junction footprint."""

    owner_id: JunctionId
    id: PortId

    def __post_init__(self) -> None:
        _require_identifier(self.owner_id, "junction ID")
        _require_identifier(self.id, "port ID")


PortReference = TrackSectionPort | JunctionPort
"""A connection boundary with an explicit physical owner kind."""


@dataclass(frozen=True, slots=True)
class TrackSectionResource:
    """The direction-independent physical resource of one track section."""

    id: TrackSectionId

    def __post_init__(self) -> None:
        _require_identifier(self.id, "track section ID")


@dataclass(frozen=True, slots=True)
class JunctionResource:
    """The direction-independent physical resource of one junction."""

    id: JunctionId

    def __post_init__(self) -> None:
        _require_identifier(self.id, "junction ID")


PhysicalResource = TrackSectionResource | JunctionResource
"""A claimable resource traversed by a path, never a directed path element."""


@dataclass(frozen=True, slots=True)
class ProtectionZoneResource:
    """A claimable protection resource that need not occur in a wheel path."""

    id: ProtectionZoneId

    def __post_init__(self) -> None:
        _require_identifier(self.id, "protection zone ID")


ClaimResource = PhysicalResource | ProtectionZoneResource
"""A physical or declared protection resource held by a route plan."""


class OccupancyExtent(StrEnum):
    """How an occupancy observation overlaps a physical resource."""

    COMPLETE = "complete"
    PARTIAL = "partial"


class ControlDevicePositionEvidence(StrEnum):
    """How an Installation Binding establishes a Control Device position."""

    SENSOR = "sensor"
    ASSUMED_AFTER_DELAY = "assumed-after-delay"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TrackSectionMovement:
    """An explicitly permitted directed movement through one track section."""

    from_port: PortId
    to_port: PortId

    def __post_init__(self) -> None:
        _require_identifier(self.from_port, "track section movement from-port ID")
        _require_identifier(self.to_port, "track section movement to-port ID")
        if self.from_port == self.to_port:
            raise ValueError("track section movement ports must be distinct")


@dataclass(frozen=True, slots=True)
class TrackSection:
    """A claimable linear rail span with two local ports."""

    id: TrackSectionId
    ports: tuple[PortId, PortId]
    movements: tuple[TrackSectionMovement, ...]
    terminal_ports: tuple[PortId, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "track section ID")
        if len(self.ports) != 2:
            raise ValueError("a track section must declare exactly two ports")
        _require_unique(self.ports, "track section ports")
        for port in self.ports:
            _require_identifier(port, "track section port ID")
        if not self.movements:
            raise ValueError("a track section must declare at least one movement")
        _require_unique(self.movements, "track section movements")
        for movement in self.movements:
            if (
                movement.from_port not in self.ports
                or movement.to_port not in self.ports
            ):
                raise ValueError("track section movements must use declared ports")
        _require_unique(self.terminal_ports, "track section terminal ports")
        for port in self.terminal_ports:
            _require_identifier(port, "track section terminal port ID")
            if port not in self.ports:
                raise ValueError("track section terminal ports must be declared ports")


@dataclass(frozen=True, slots=True)
class Junction:
    """An atomic, exclusively claimable junction resource."""

    id: JunctionId
    ports: tuple[PortId, ...]
    terminal_ports: tuple[PortId, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "junction ID")
        if len(self.ports) < 2:
            raise ValueError("a junction must declare at least two ports")
        _require_unique(self.ports, "junction ports")
        for port in self.ports:
            _require_identifier(port, "junction port ID")
        _require_unique(self.terminal_ports, "junction terminal ports")
        for port in self.terminal_ports:
            _require_identifier(port, "junction terminal port ID")
            if port not in self.ports:
                raise ValueError("junction terminal ports must be declared ports")


@dataclass(frozen=True, slots=True)
class ConnectionMovement:
    """An explicitly permitted directed movement across one fixed connection."""

    from_port: PortReference
    to_port: PortReference

    def __post_init__(self) -> None:
        if self.from_port == self.to_port:
            raise ValueError("connection movement ports must be distinct")


@dataclass(frozen=True, slots=True)
class Connection:
    """A non-claimable fixed adjacency between exactly two ports."""

    id: ConnectionId
    ports: tuple[PortReference, PortReference]
    movements: tuple[ConnectionMovement, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.id, "connection ID")
        if len(self.ports) != 2 or self.ports[0] == self.ports[1]:
            raise ValueError("a connection must declare two distinct ports")
        if not self.movements:
            raise ValueError("a connection must declare at least one movement")
        _require_unique(self.movements, "connection movements")
        for movement in self.movements:
            if {movement.from_port, movement.to_port} != set(self.ports):
                raise ValueError("connection movements must use the connection ports")


@dataclass(frozen=True, slots=True)
class ControlDevice:
    """A logical state-bearing device with explicitly declared positions."""

    id: ControlDeviceId
    positions: tuple[DevicePositionId, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.id, "control device ID")
        if len(self.positions) < 2:
            raise ValueError("a control device must declare at least two positions")
        _require_unique(self.positions, "control device positions")
        for position in self.positions:
            _require_identifier(position, "control device position ID")


@dataclass(frozen=True, slots=True)
class DeviceRequirement:
    """One required logical position, without a command or observed state."""

    device_id: ControlDeviceId
    position_id: DevicePositionId

    def __post_init__(self) -> None:
        _require_identifier(self.device_id, "device requirement control device ID")
        _require_identifier(self.position_id, "device requirement position ID")


@dataclass(frozen=True, slots=True)
class JunctionPassage:
    """An explicitly permitted directed movement that claims its junction."""

    id: JunctionPassageId
    junction_id: JunctionId
    from_port: PortId
    to_port: PortId
    requirements: tuple[DeviceRequirement, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "junction passage ID")
        _require_identifier(self.junction_id, "junction passage junction ID")
        _require_identifier(self.from_port, "junction passage from-port ID")
        _require_identifier(self.to_port, "junction passage to-port ID")
        if self.from_port == self.to_port:
            raise ValueError("junction passage ports must be distinct")
        if len({requirement.device_id for requirement in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("junction passage device requirements must be unique")


@dataclass(frozen=True, slots=True)
class OccupancyCoverage:
    """The declared complete or partial observation of one physical resource."""

    resource: PhysicalResource
    extent: OccupancyExtent


@dataclass(frozen=True, slots=True)
class OccupancyZone:
    """One logical observation source, separate from physical resource identity."""

    id: OccupancyZoneId
    coverage: tuple[OccupancyCoverage, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.id, "occupancy zone ID")
        if not self.coverage:
            raise ValueError("occupancy zone coverage must be nonempty")
        if len({item.resource for item in self.coverage}) != len(self.coverage):
            raise ValueError("an occupancy zone may cover each resource only once")


@dataclass(frozen=True, slots=True)
class ProtectionZone:
    """A claimable safety resource outside or in addition to a wheel path."""

    id: ProtectionZoneId

    def __post_init__(self) -> None:
        _require_identifier(self.id, "protection zone ID")


@dataclass(frozen=True, slots=True)
class ProtectionRule:
    """Static non-path claims and device requirements for one path trigger."""

    id: str
    trigger: Mapping[str, str]
    claims: tuple[ProtectionZoneId, ...] = ()
    requirements: tuple[DeviceRequirement, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "protection rule ID")
        if not self.claims and not self.requirements:
            raise ValueError("a protection rule must make a contribution")
        _require_unique(self.claims, "protection rule claims")
        if len({item.device_id for item in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("protection rule device requirements must be unique")


@dataclass(frozen=True, slots=True)
class RouteDefinition:
    """Declared route boundaries and ordered constraints before compilation."""

    id: RouteDefinitionId
    entry: PortReference
    exit: PortReference
    via: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrackSectionPathElement:
    """One directed traversal of a Track Section in a compiled route."""

    id: TrackSectionId
    from_port: PortId
    to_port: PortId


@dataclass(frozen=True, slots=True)
class ConnectionPathElement:
    """One directed traversal of a non-claimable fixed connection."""

    id: ConnectionId
    from_port: PortReference
    to_port: PortReference


@dataclass(frozen=True, slots=True)
class JunctionPassagePathElement:
    """One declared directed Junction Passage in a compiled route."""

    id: JunctionPassageId


PathElement = (
    TrackSectionPathElement | ConnectionPathElement | JunctionPassagePathElement
)
"""A directed element in the complete ordered path of a Route Plan."""


@dataclass(frozen=True, slots=True)
class ClaimContribution:
    """The path element or rule that made a claim necessary."""

    source: str


@dataclass(frozen=True, slots=True)
class RequirementContribution:
    """The path element or rule that made a device position necessary."""

    source: str


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """An immutable, resource-complete compilation of one Route Definition."""

    route_id: RouteDefinitionId
    topology_revision: str
    path: tuple[PathElement, ...]
    claims: tuple[ClaimResource, ...]
    requirements: tuple[DeviceRequirement, ...]
    claim_provenance: Mapping[ClaimResource, tuple[ClaimContribution, ...]]
    requirement_provenance: Mapping[
        ControlDeviceId, tuple[RequirementContribution, ...]
    ]


@dataclass(frozen=True, slots=True)
class ControlDeviceBinding:
    """One command channel and declared position evidence for a Control Device."""

    command_channel: str
    position_evidence: ControlDevicePositionEvidence
    feedback_channel: str | None = None
    settle_delay_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.command_channel:
            raise ValueError("installation binding command channel must be nonempty")
        if self.feedback_channel is not None and not self.feedback_channel:
            raise ValueError("installation binding feedback channel must be nonempty")
        if self.feedback_channel == self.command_channel:
            raise ValueError("command and feedback channels must be independent")
        if self.position_evidence is ControlDevicePositionEvidence.SENSOR:
            if self.feedback_channel is None or self.settle_delay_ms is not None:
                raise ValueError("sensor evidence requires feedback only")
        elif (
            self.position_evidence is ControlDevicePositionEvidence.ASSUMED_AFTER_DELAY
        ):
            if (
                self.feedback_channel is not None
                or not isinstance(self.settle_delay_ms, int)
                or self.settle_delay_ms < 1
            ):
                raise ValueError(
                    "assumed-after-delay evidence requires a positive delay only"
                )
        elif self.feedback_channel is not None or self.settle_delay_ms is not None:
            raise ValueError("unknown evidence cannot declare feedback or a delay")


@dataclass(frozen=True, slots=True)
class InstallationBinding:
    """Complete controller-channel mapping for one topology revision."""

    topology_revision: str
    control_devices: Mapping[ControlDeviceId, ControlDeviceBinding]
    occupancy_feedback: Mapping[OccupancyZoneId, str]


@dataclass(frozen=True, slots=True)
class Topology:
    """The immutable, validated core rail graph from one schema-v3 layout."""

    track_sections: Mapping[TrackSectionId, TrackSection]
    junctions: Mapping[JunctionId, Junction]
    control_devices: Mapping[ControlDeviceId, ControlDevice]
    connections: Mapping[ConnectionId, Connection]
    junction_passages: Mapping[JunctionPassageId, JunctionPassage]
    occupancy_zones: Mapping[OccupancyZoneId, OccupancyZone]
    protection_zones: Mapping[ProtectionZoneId, ProtectionZone]
    protection_rules: Mapping[str, ProtectionRule]
    route_definitions: Mapping[RouteDefinitionId, RouteDefinition]
    revision: str
