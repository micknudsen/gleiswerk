"""Tests for controller-independent layout domain models."""

import unittest

from gleiswerk.layout import (
    Block,
    BlockId,
    Layout,
    PositionId,
    Route,
    RouteId,
    Turnout,
    TurnoutId,
)


class LayoutTest(unittest.TestCase):
    def test_layout_represents_declared_blocks_turnouts_and_routes(self) -> None:
        block = Block(BlockId("west-entry"), "West entry")
        turnout = Turnout(
            TurnoutId("west-entry"), (PositionId("normal"), PositionId("reverse"))
        )
        route = Route(
            RouteId("arrival-to-platform-1"),
            (BlockId("west-entry"),),
            {TurnoutId("west-entry"): PositionId("normal")},
        )

        layout = Layout((block,), (turnout,), (route,))

        self.assertEqual(layout.blocks, (block,))
        self.assertEqual(layout.turnouts, (turnout,))
        self.assertEqual(layout.routes, (route,))
        self.assertEqual(block.effective_display_name, "West entry")
        self.assertEqual(turnout.effective_display_name, "west-entry")
        self.assertEqual(route.effective_display_name, "arrival-to-platform-1")

    def test_stable_ids_must_be_lowercase_kebab_case(self) -> None:
        for identifier in "", "West-entry", "west_entry", "west--entry":
            with (
                self.subTest(identifier=identifier),
                self.assertRaisesRegex(ValueError, "lowercase kebab-case"),
            ):
                Block(BlockId(identifier))

    def test_turnout_requires_distinct_selectable_positions(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            Turnout(TurnoutId("west-entry"), (PositionId("normal"),))

        with self.assertRaisesRegex(ValueError, "distinct"):
            Turnout(
                TurnoutId("west-entry"),
                (PositionId("normal"), PositionId("normal")),
            )

    def test_route_requires_non_empty_distinct_blocks(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            Route(RouteId("arrival"), ())

        with self.assertRaisesRegex(ValueError, "distinct"):
            Route(RouteId("arrival"), (BlockId("west-entry"), BlockId("west-entry")))

    def test_layout_rejects_unknown_route_references(self) -> None:
        with self.assertRaisesRegex(ValueError, "undeclared block"):
            Layout(routes=(Route(RouteId("arrival"), (BlockId("west-entry"),)),))

        block = Block(BlockId("west-entry"))
        route = Route(
            RouteId("arrival"),
            (BlockId("west-entry"),),
            {TurnoutId("west-entry"): PositionId("normal")},
        )
        with self.assertRaisesRegex(ValueError, "undeclared turnout"):
            Layout(blocks=(block,), routes=(route,))

    def test_layout_rejects_unsupported_turnout_position(self) -> None:
        block = Block(BlockId("west-entry"))
        turnout = Turnout(
            TurnoutId("west-entry"), (PositionId("normal"), PositionId("reverse"))
        )
        route = Route(
            RouteId("arrival"),
            (BlockId("west-entry"),),
            {TurnoutId("west-entry"): PositionId("straight")},
        )

        with self.assertRaisesRegex(ValueError, "undeclared turnout position"):
            Layout(blocks=(block,), turnouts=(turnout,), routes=(route,))

    def test_route_turnout_requirements_are_immutable(self) -> None:
        route = Route(
            RouteId("arrival"),
            (BlockId("west-entry"),),
            {TurnoutId("west-entry"): PositionId("normal")},
        )

        self.assertFalse(hasattr(route.turnout_positions, "__setitem__"))
