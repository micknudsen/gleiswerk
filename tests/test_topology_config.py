"""Tests for schema-version 2 topology configuration loading."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gleiswerk.layout import EndpointReference
from gleiswerk.layout_config import load_layout, validate_layout_data


class TopologyConfigurationTest(unittest.TestCase):
    def test_loader_constructs_topology_objects(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "layout.toml"
            path.write_text(
                """schema-version = 2

[blocks.west-entry]
endpoints = ["west", "east"]

[blocks.platform-1]
endpoints = ["west", "east"]

[traversals.west-to-platform]
from = "west-entry.east"
to = "platform-1.west"

[routes.arrival]
traversals = ["west-to-platform"]
""",
                encoding="utf-8",
            )

            layout = load_layout(path)

        self.assertEqual(
            layout.traversals[0].from_endpoint,
            EndpointReference.from_string("west-entry.east"),
        )
        self.assertEqual(layout.routes[0].traversals, ("west-to-platform",))

    def test_validator_accepts_a_complete_topology_layout(self) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 2,
                "blocks": {
                    "west-entry": {"endpoints": ["west", "east"]},
                    "platform-1": {"endpoints": ["west", "east"]},
                },
                "turnouts": {"west-throat": {"positions": ["normal", "reverse"]}},
                "traversals": {
                    "west-to-platform": {
                        "from": "west-entry.east",
                        "to": "platform-1.west",
                        "turnouts": {"west-throat": "normal"},
                    }
                },
                "routes": {"arrival": {"traversals": ["west-to-platform"]}},
            }
        )

        self.assertEqual(diagnostics, ())

    def test_validator_accepts_a_continuous_route_with_compatible_turnouts(
        self,
    ) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 2,
                "blocks": {
                    "west-entry": {"endpoints": ["west", "east"]},
                    "platform-1": {"endpoints": ["west", "east"]},
                    "depot": {"endpoints": ["west", "east"]},
                },
                "turnouts": {"west-throat": {"positions": ["normal", "reverse"]}},
                "traversals": {
                    "west-to-platform": {
                        "from": "west-entry.east",
                        "to": "platform-1.west",
                        "turnouts": {"west-throat": "normal"},
                    },
                    "platform-to-depot": {
                        "from": "platform-1.west",
                        "to": "depot.east",
                        "turnouts": {"west-throat": "normal"},
                    },
                },
                "routes": {
                    "arrival": {"traversals": ["west-to-platform", "platform-to-depot"]}
                },
            }
        )

        self.assertEqual(diagnostics, ())

    def test_validator_rejects_schema_version_1(self) -> None:
        diagnostics = validate_layout_data({"schema-version": 1})

        self.assertEqual(
            [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics],
            [("E103", "schema-version")],
        )

    def test_validator_reports_invalid_topology_shapes_with_paths(self) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 2,
                "blocks": {"platform": {"endpoints": ["west", "west"]}},
                "traversals": {"invalid": {"from": "not-a-reference"}},
                "routes": {"arrival": {"traversals": []}},
            }
        )

        self.assertEqual(
            [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics],
            [
                ("E115", "blocks.platform.endpoints[1]"),
                ("E133", "traversals.invalid.from"),
                ("E132", "traversals.invalid.to"),
                ("E144", "routes.arrival.traversals"),
            ],
        )

    def test_validator_reports_unresolved_topology_references_in_order(self) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 2,
                "blocks": {"west-entry": {"endpoints": ["west", "east"]}},
                "turnouts": {"west-throat": {"positions": ["normal", "reverse"]}},
                "traversals": {
                    "invalid": {
                        "from": "west-entry.missing",
                        "to": "missing.west",
                        "turnouts": {"missing": "normal", "west-throat": "straight"},
                    }
                },
                "routes": {"arrival": {"traversals": ["missing"]}},
            }
        )

        self.assertEqual(
            [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics],
            [
                ("E201", "traversals.invalid.from"),
                ("E201", "traversals.invalid.to"),
                ("E202", "traversals.invalid.turnouts.missing"),
                ("E203", "traversals.invalid.turnouts.west-throat"),
                ("E204", "routes.arrival.traversals[0]"),
            ],
        )

    def test_validator_reports_route_continuity_and_turnout_conflicts_in_order(
        self,
    ) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 2,
                "blocks": {
                    "west-entry": {"endpoints": ["west", "east"]},
                    "platform-1": {"endpoints": ["west", "east"]},
                    "depot": {"endpoints": ["west", "east"]},
                },
                "turnouts": {"west-throat": {"positions": ["normal", "reverse"]}},
                "traversals": {
                    "west-to-platform": {
                        "from": "west-entry.east",
                        "to": "platform-1.west",
                        "turnouts": {"west-throat": "normal"},
                    },
                    "platform-to-depot": {
                        "from": "platform-1.east",
                        "to": "depot.west",
                        "turnouts": {"west-throat": "reverse"},
                    },
                },
                "routes": {
                    "zeta": {"traversals": ["west-to-platform", "platform-to-depot"]},
                    "alpha": {"traversals": ["west-to-platform", "platform-to-depot"]},
                },
            }
        )

        self.assertEqual(
            [
                (diagnostic.code, diagnostic.path, diagnostic.message)
                for diagnostic in diagnostics
            ],
            [
                (
                    "E205",
                    "routes.alpha.traversals[1]",
                    "traversal 'west-to-platform' does not connect to "
                    "'platform-to-depot'",
                ),
                (
                    "E206",
                    "routes.alpha.traversals[1]",
                    "traversal 'platform-to-depot' requires turnout 'west-throat' "
                    "to be 'reverse', but the route requires 'normal'",
                ),
                (
                    "E205",
                    "routes.zeta.traversals[1]",
                    "traversal 'west-to-platform' does not connect to "
                    "'platform-to-depot'",
                ),
                (
                    "E206",
                    "routes.zeta.traversals[1]",
                    "traversal 'platform-to-depot' requires turnout 'west-throat' "
                    "to be 'reverse', but the route requires 'normal'",
                ),
            ],
        )

    def test_endpoint_reference_splits_block_and_endpoint_ids(self) -> None:
        reference = EndpointReference.from_string("west-entry.east")

        self.assertEqual(reference.block_id, "west-entry")
        self.assertEqual(reference.endpoint_id, "east")
