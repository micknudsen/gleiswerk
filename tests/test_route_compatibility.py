"""Tests for conservative, controller-independent route compatibility."""

import unittest

from gleiswerk.layout import BlockId, PositionId, Route, RouteId, TurnoutId
from gleiswerk.route_compatibility import (
    RouteConflictKind,
    compare_routes,
)


class RouteCompatibilityTest(unittest.TestCase):
    def test_routes_without_shared_resources_are_compatible(self) -> None:
        first = Route(RouteId("arrival"), (BlockId("west-entry"),))
        second = Route(RouteId("departure"), (BlockId("east-exit"),))

        compatibility = compare_routes(first, second)

        self.assertTrue(compatibility.is_compatible)
        self.assertEqual(compatibility.conflicts, ())
        self.assertEqual(
            compatibility.routes, (RouteId("arrival"), RouteId("departure"))
        )

    def test_shared_block_is_a_conflict(self) -> None:
        first = Route(RouteId("arrival"), (BlockId("platform"), BlockId("west-entry")))
        second = Route(
            RouteId("departure"), (BlockId("east-exit"), BlockId("platform"))
        )

        compatibility = compare_routes(first, second)

        self.assertFalse(compatibility.is_compatible)
        self.assertEqual(len(compatibility.conflicts), 1)
        conflict = compatibility.conflicts[0]
        self.assertEqual(conflict.kind, RouteConflictKind.SHARED_BLOCK)
        self.assertEqual(conflict.routes, (RouteId("arrival"), RouteId("departure")))
        self.assertEqual(conflict.block, BlockId("platform"))

    def test_incompatible_turnout_positions_are_a_conflict(self) -> None:
        first = Route(
            RouteId("arrival"),
            (BlockId("west-entry"),),
            {TurnoutId("west-throat"): PositionId("normal")},
        )
        second = Route(
            RouteId("departure"),
            (BlockId("east-exit"),),
            {TurnoutId("west-throat"): PositionId("reverse")},
        )

        compatibility = compare_routes(first, second)

        self.assertFalse(compatibility.is_compatible)
        self.assertEqual(len(compatibility.conflicts), 1)
        conflict = compatibility.conflicts[0]
        self.assertEqual(conflict.kind, RouteConflictKind.INCOMPATIBLE_TURNOUT)
        self.assertEqual(conflict.turnout, TurnoutId("west-throat"))
        self.assertEqual(
            conflict.required_positions,
            (PositionId("normal"), PositionId("reverse")),
        )

    def test_explanations_are_deterministic_across_input_order(self) -> None:
        first = Route(
            RouteId("zebra"),
            (BlockId("zebra-block"), BlockId("alpha-block")),
            {
                TurnoutId("zebra-turnout"): PositionId("normal"),
                TurnoutId("alpha-turnout"): PositionId("reverse"),
            },
        )
        second = Route(
            RouteId("alpha"),
            (BlockId("alpha-block"), BlockId("zebra-block")),
            {
                TurnoutId("zebra-turnout"): PositionId("reverse"),
                TurnoutId("alpha-turnout"): PositionId("normal"),
            },
        )

        forward = compare_routes(first, second)
        reverse = compare_routes(second, first)

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [
                (conflict.kind, conflict.block, conflict.turnout)
                for conflict in forward.conflicts
            ],
            [
                (RouteConflictKind.SHARED_BLOCK, BlockId("alpha-block"), None),
                (RouteConflictKind.SHARED_BLOCK, BlockId("zebra-block"), None),
                (
                    RouteConflictKind.INCOMPATIBLE_TURNOUT,
                    None,
                    TurnoutId("alpha-turnout"),
                ),
                (
                    RouteConflictKind.INCOMPATIBLE_TURNOUT,
                    None,
                    TurnoutId("zebra-turnout"),
                ),
            ],
        )
        self.assertEqual(
            forward.conflicts[2].required_positions,
            (PositionId("normal"), PositionId("reverse")),
        )
        self.assertEqual(
            forward.conflicts[3].required_positions,
            (PositionId("reverse"), PositionId("normal")),
        )
