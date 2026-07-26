"""Controller-independent domain models for a railway layout."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import NewType

BlockId = NewType("BlockId", str)
"""A stable identifier for a block."""

PositionId = NewType("PositionId", str)
"""A turnout position identifier, local to one turnout."""

RouteId = NewType("RouteId", str)
"""A stable identifier for a route."""

TurnoutId = NewType("TurnoutId", str)
"""A stable identifier for a turnout."""


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _require_identifier(value: str, description: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        message = f"{description} must be a lowercase kebab-case identifier"
        raise ValueError(message)


def _require_display_name(value: str | None) -> None:
    if value is not None and not value:
        raise ValueError("display name must not be empty")


def _empty_turnout_positions() -> Mapping[TurnoutId, PositionId]:
    return {}


@dataclass(frozen=True, slots=True)
class Block:
    """A named, controller-independent section of track."""

    id: BlockId
    display_name: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "block ID")
        _require_display_name(self.display_name)

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
class Route:
    """A directional declaration of block traversal and turnout requirements."""

    id: RouteId
    blocks: tuple[BlockId, ...]
    turnout_positions: Mapping[TurnoutId, PositionId] = field(
        default_factory=_empty_turnout_positions
    )
    display_name: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.id, "route ID")
        _require_display_name(self.display_name)
        if not self.blocks:
            raise ValueError("a route must declare at least one block")
        if len(set(self.blocks)) != len(self.blocks):
            raise ValueError("route blocks must be distinct")
        for block_id in self.blocks:
            _require_identifier(block_id, "route block ID")
        for turnout_id, position_id in self.turnout_positions.items():
            _require_identifier(turnout_id, "route turnout ID")
            _require_identifier(position_id, "route turnout position ID")
        object.__setattr__(
            self, "turnout_positions", MappingProxyType(dict(self.turnout_positions))
        )

    @property
    def effective_display_name(self) -> str:
        """Return the operator-facing name, falling back to the stable ID."""
        return self.display_name or self.id


@dataclass(frozen=True, slots=True)
class Layout:
    """The complete declared layout, independent of a controller or simulator."""

    blocks: tuple[Block, ...] = ()
    turnouts: tuple[Turnout, ...] = ()
    routes: tuple[Route, ...] = ()

    def __post_init__(self) -> None:
        _require_unique_ids(self.blocks, "block")
        _require_unique_ids(self.turnouts, "turnout")
        _require_unique_ids(self.routes, "route")

        block_ids = {block.id for block in self.blocks}
        turnouts = {turnout.id: turnout for turnout in self.turnouts}
        for route in self.routes:
            unknown_blocks = set(route.blocks) - block_ids
            if unknown_blocks:
                raise ValueError(f"route {route.id!r} references an undeclared block")
            for turnout_id, position_id in route.turnout_positions.items():
                turnout = turnouts.get(turnout_id)
                if turnout is None:
                    raise ValueError(
                        f"route {route.id!r} references an undeclared turnout"
                    )
                if position_id not in turnout.positions:
                    raise ValueError(
                        f"route {route.id!r} requires an undeclared turnout position"
                    )


def _require_unique_ids(
    objects: tuple[Block | Turnout | Route, ...], kind: str
) -> None:
    if len({object_.id for object_ in objects}) != len(objects):
        raise ValueError(f"{kind} IDs must be unique")
