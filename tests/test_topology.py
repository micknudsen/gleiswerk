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
