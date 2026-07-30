"""Controller-independent domain models for a schema-version 2 layout."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import NewType

BlockId = NewType("BlockId", str)
"""A stable identifier for a block."""

EndpointId = NewType("EndpointId", str)
"""A stable identifier for an endpoint local to one block."""

PositionId = NewType("PositionId", str)
"""A turnout position identifier, local to one turnout."""

RouteId = NewType("RouteId", str)
"""A stable identifier for a route."""

TraversalId = NewType("TraversalId", str)
"""A stable identifier for a directed topology traversal."""

TurnoutId = NewType("TurnoutId", str)
"""A stable identifier for a turnout."""


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _require_identifier(value: str, description: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{description} must be a lowercase kebab-case identifier")


def _require_display_name(value: str | None) -> None:
    if value is not None and not value:
        raise ValueError("display name must not be empty")


def _empty_turnout_positions() -> Mapping[TurnoutId, PositionId]:
    return {}


@dataclass(frozen=True, slots=True)
class EndpointReference:
    """A logical reference to one declared block endpoint."""

    block_id: BlockId
    endpoint_id: EndpointId

    def __post_init__(self) -> None:
        _require_identifier(self.block_id, "endpoint block ID")
        _require_identifier(self.endpoint_id, "endpoint ID")

    @classmethod
    def from_string(cls, value: str) -> EndpointReference:
        """Build a reference from its ``block-id.endpoint-id`` representation."""
        block_id, separator, endpoint_id = value.partition(".")
        if not separator or "." in endpoint_id:
            raise ValueError("endpoint reference must be block-id.endpoint-id")
        return cls(BlockId(block_id), EndpointId(endpoint_id))

    def __str__(self) -> str:
        return f"{self.block_id}.{self.endpoint_id}"


@dataclass(frozen=True, slots=True)
class Block:
    """A named track section with exactly two logical endpoints."""

    id: BlockId
    endpoints: tuple[EndpointId, EndpointId]
    display_name: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "block ID")
        _require_display_name(self.display_name)
        if len(self.endpoints) != 2:
            raise ValueError("a block must declare exactly two endpoints")
        if len(set(self.endpoints)) != len(self.endpoints):
            raise ValueError("block endpoints must be distinct")
        for endpoint in self.endpoints:
            _require_identifier(endpoint, "endpoint ID")

    @property
    def effective_display_name(self) -> str:
        """Return the operator-facing name, falling back to the stable ID."""
        return self.display_name or self.id


@dataclass(frozen=True, slots=True)
class Turnout:
    """A named turnout with the selectable positions it supports."""

    id: TurnoutId
    positions: tuple[PositionId, ...]
    display_name: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "turnout ID")
        _require_display_name(self.display_name)
        if len(self.positions) < 2:
            raise ValueError("a turnout must declare at least two positions")
        if len(set(self.positions)) != len(self.positions):
            raise ValueError("turnout positions must be distinct")
        for position in self.positions:
            _require_identifier(position, "turnout position ID")

    @property
    def effective_display_name(self) -> str:
        """Return the operator-facing name, falling back to the stable ID."""
        return self.display_name or self.id


@dataclass(frozen=True, slots=True)
class Traversal:
    """A directed logical passage, optionally constrained by turnout positions."""

    id: TraversalId
    from_endpoint: EndpointReference
    to_endpoint: EndpointReference
    turnout_positions: Mapping[TurnoutId, PositionId] = field(
        default_factory=_empty_turnout_positions
    )

    def __post_init__(self) -> None:
        _require_identifier(self.id, "traversal ID")
        if self.from_endpoint == self.to_endpoint:
            raise ValueError("traversal endpoints must differ")
        for turnout_id, position_id in self.turnout_positions.items():
            _require_identifier(turnout_id, "traversal turnout ID")
            _require_identifier(position_id, "traversal turnout position ID")
        object.__setattr__(
            self, "turnout_positions", MappingProxyType(dict(self.turnout_positions))
        )


@dataclass(frozen=True, slots=True)
class Route:
    """An ordered declaration of the traversals a route requires."""

    id: RouteId
    traversals: tuple[TraversalId, ...]
    display_name: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "route ID")
        _require_display_name(self.display_name)
        if not self.traversals:
            raise ValueError("a route must declare at least one traversal")
        for traversal_id in self.traversals:
            _require_identifier(traversal_id, "route traversal ID")

    @property
    def effective_display_name(self) -> str:
        """Return the operator-facing name, falling back to the stable ID."""
        return self.display_name or self.id


@dataclass(frozen=True, slots=True)
class Layout:
    """The complete declared topology, independent of controller or simulator."""

    blocks: tuple[Block, ...] = ()
    turnouts: tuple[Turnout, ...] = ()
    traversals: tuple[Traversal, ...] = ()
    routes: tuple[Route, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_ids(self.blocks, "block")
        _require_unique_ids(self.turnouts, "turnout")
        _require_unique_ids(self.traversals, "traversal")
        _require_unique_ids(self.routes, "route")

        endpoints = {
            (block.id, endpoint_id)
            for block in self.blocks
            for endpoint_id in block.endpoints
        }
        turnouts = {turnout.id: turnout for turnout in self.turnouts}
        traversal_ids = {traversal.id for traversal in self.traversals}
        for traversal in self.traversals:
            for endpoint in (traversal.from_endpoint, traversal.to_endpoint):
                if (endpoint.block_id, endpoint.endpoint_id) not in endpoints:
                    raise ValueError(
                        f"traversal {traversal.id!r} references an undeclared endpoint"
                    )
            for turnout_id, position_id in traversal.turnout_positions.items():
                turnout = turnouts.get(turnout_id)
                if turnout is None:
                    raise ValueError(
                        f"traversal {traversal.id!r} references an undeclared turnout"
                    )
                if position_id not in turnout.positions:
                    raise ValueError(
                        f"traversal {traversal.id!r} requires an undeclared turnout position"
                    )
        for route in self.routes:
            if set(route.traversals) - traversal_ids:
                raise ValueError(
                    f"route {route.id!r} references an undeclared traversal"
                )


def _require_unique_ids(
    objects: tuple[Block | Turnout | Traversal | Route, ...], kind: str
) -> None:
    if len({object_.id for object_ in objects}) != len(objects):
        raise ValueError(f"{kind} IDs must be unique")
