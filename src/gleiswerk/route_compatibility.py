"""Conservative, controller-independent compatibility checks for routes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gleiswerk.layout import BlockId, PositionId, Route, RouteId, TurnoutId


class RouteConflictKind(StrEnum):
    """The declared resource that makes two routes incompatible."""

    SHARED_BLOCK = "shared-block"
    INCOMPATIBLE_TURNOUT = "incompatible-turnout"


@dataclass(frozen=True, slots=True)
class RouteConflict:
    """One deterministic explanation of why two routes cannot coexist."""

    kind: RouteConflictKind
    routes: tuple[RouteId, RouteId]
    block: BlockId | None = None
    turnout: TurnoutId | None = None
    required_positions: tuple[PositionId, PositionId] | None = None


@dataclass(frozen=True, slots=True)
class RouteCompatibility:
    """The conservative compatibility result for two declared routes."""

    routes: tuple[RouteId, RouteId]
    conflicts: tuple[RouteConflict, ...]

    @property
    def is_compatible(self) -> bool:
        """Return whether the declarations identify no incompatibility."""
        return not self.conflicts


def compare_routes(first: Route, second: Route) -> RouteCompatibility:
    """Compare route declarations without authorizing movement or commands.

    A shared block or different required positions for the same turnout makes
    the pair incompatible. Results are canonicalized by route and resource ID
    so callers receive the same explanation regardless of argument order.
    """
    first, second = (first, second) if first.id <= second.id else (second, first)
    routes = (first.id, second.id)
    conflicts = tuple(
        _shared_block_conflicts(first, second)
        + _incompatible_turnout_conflicts(first, second)
    )
    return RouteCompatibility(routes, conflicts)


def _shared_block_conflicts(first: Route, second: Route) -> list[RouteConflict]:
    routes = (first.id, second.id)
    return [
        RouteConflict(RouteConflictKind.SHARED_BLOCK, routes, block=block)
        for block in sorted(set(first.blocks) & set(second.blocks))
    ]


def _incompatible_turnout_conflicts(first: Route, second: Route) -> list[RouteConflict]:
    routes = (first.id, second.id)
    conflicts: list[RouteConflict] = []
    for turnout in sorted(set(first.turnout_positions) & set(second.turnout_positions)):
        first_position = first.turnout_positions[turnout]
        second_position = second.turnout_positions[turnout]
        if first_position != second_position:
            positions = (first_position, second_position)
            conflicts.append(
                RouteConflict(
                    RouteConflictKind.INCOMPATIBLE_TURNOUT,
                    routes,
                    turnout=turnout,
                    required_positions=positions,
                )
            )
    return conflicts
