"""Tests for schema-version 2 controller-independent topology models."""

import unittest
from typing import cast

from gleiswerk.layout import (
    Block,
    BlockId,
    EndpointId,
    EndpointReference,
    Layout,
    PositionId,
    Route,
    RouteId,
    Traversal,
    TraversalId,
    Turnout,
    TurnoutId,
)


class TopologyModelTest(unittest.TestCase):
    def test_layout_represents_declared_topology(self) -> None:
        west = Block(BlockId("west-entry"), (EndpointId("west"), EndpointId("east")))
        platform = Block(
            BlockId("platform-1"), (EndpointId("west"), EndpointId("east"))
        )
        turnout = Turnout(
            TurnoutId("west-throat"), (PositionId("normal"), PositionId("reverse"))
        )
        traversal = Traversal(
            TraversalId("west-to-platform"),
            EndpointReference(BlockId("west-entry"), EndpointId("east")),
            EndpointReference(BlockId("platform-1"), EndpointId("west")),
            {TurnoutId("west-throat"): PositionId("normal")},
        )
        route = Route(RouteId("arrival"), (TraversalId("west-to-platform"),))

        layout = Layout((west, platform), (turnout,), (traversal,), (route,))

        self.assertEqual(layout.traversals, (traversal,))
        self.assertEqual(layout.routes, (route,))
        self.assertFalse(hasattr(traversal.turnout_positions, "__setitem__"))

    def test_block_requires_two_distinct_endpoints(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly two"):
            Block(
                BlockId("platform"),
                cast(tuple[EndpointId, EndpointId], (EndpointId("west"),)),
            )

        with self.assertRaisesRegex(ValueError, "distinct"):
            Block(BlockId("platform"), (EndpointId("west"), EndpointId("west")))

    def test_layout_rejects_unresolved_topology_references(self) -> None:
        traversal = Traversal(
            TraversalId("unknown"),
            EndpointReference(BlockId("west-entry"), EndpointId("east")),
            EndpointReference(BlockId("platform"), EndpointId("west")),
        )
        with self.assertRaisesRegex(ValueError, "undeclared endpoint"):
            Layout(traversals=(traversal,))

        block = Block(BlockId("west-entry"), (EndpointId("west"), EndpointId("east")))
        route = Route(RouteId("arrival"), (TraversalId("unknown"),))
        with self.assertRaisesRegex(ValueError, "undeclared traversal"):
            Layout(blocks=(block,), routes=(route,))

    def test_layout_rejects_discontinuous_route_traversals(self) -> None:
        west = Block(BlockId("west-entry"), (EndpointId("west"), EndpointId("east")))
        platform = Block(
            BlockId("platform-1"), (EndpointId("west"), EndpointId("east"))
        )
        depot = Block(BlockId("depot"), (EndpointId("west"), EndpointId("east")))
        to_platform = Traversal(
            TraversalId("west-to-platform"),
            EndpointReference(BlockId("west-entry"), EndpointId("east")),
            EndpointReference(BlockId("platform-1"), EndpointId("west")),
        )
        from_depot = Traversal(
            TraversalId("depot-to-platform"),
            EndpointReference(BlockId("depot"), EndpointId("east")),
            EndpointReference(BlockId("platform-1"), EndpointId("west")),
        )
        route = Route(
            RouteId("arrival"),
            (TraversalId("west-to-platform"), TraversalId("depot-to-platform")),
        )

        with self.assertRaisesRegex(ValueError, "not continuous"):
            Layout(
                (west, platform, depot),
                traversals=(to_platform, from_depot),
                routes=(route,),
            )

    def test_layout_rejects_conflicting_route_turnout_requirements(self) -> None:
        west = Block(BlockId("west-entry"), (EndpointId("west"), EndpointId("east")))
        platform = Block(
            BlockId("platform-1"), (EndpointId("west"), EndpointId("east"))
        )
        depot = Block(BlockId("depot"), (EndpointId("west"), EndpointId("east")))
        turnout = Turnout(
            TurnoutId("west-throat"), (PositionId("normal"), PositionId("reverse"))
        )
        to_platform = Traversal(
            TraversalId("west-to-platform"),
            EndpointReference(BlockId("west-entry"), EndpointId("east")),
            EndpointReference(BlockId("platform-1"), EndpointId("west")),
            {TurnoutId("west-throat"): PositionId("normal")},
        )
        to_depot = Traversal(
            TraversalId("platform-to-depot"),
            EndpointReference(BlockId("platform-1"), EndpointId("west")),
            EndpointReference(BlockId("depot"), EndpointId("east")),
            {TurnoutId("west-throat"): PositionId("reverse")},
        )
        route = Route(
            RouteId("arrival"),
            (TraversalId("west-to-platform"), TraversalId("platform-to-depot")),
        )

        with self.assertRaisesRegex(ValueError, "incompatible turnout requirements"):
            Layout(
                (west, platform, depot),
                (turnout,),
                (to_platform, to_depot),
                (route,),
            )
