"""Tests for version-1 layout configuration loading and diagnostics."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gleiswerk.layout_config import (
    LayoutConfigurationError,
    load_layout,
    validate_layout_data,
)


class LayoutConfigurationTest(unittest.TestCase):
    def write_layout(
        self, directory: Path, content: str, name: str = "layout.toml"
    ) -> Path:
        path = directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_layout_builds_a_valid_domain_layout(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = self.write_layout(
                Path(temporary_directory),
                """schema-version = 1

[blocks.west-entry]
display-name = "West entry"

[turnouts.west-entry]
positions = ["normal", "reverse"]

[routes.arrival]
blocks = ["west-entry"]

[routes.arrival.turnouts]
west-entry = "normal"
""",
            )

            layout = load_layout(path)

        self.assertEqual(layout.blocks[0].id, "west-entry")
        self.assertEqual(layout.turnouts[0].positions, ("normal", "reverse"))
        self.assertEqual(layout.routes[0].turnout_positions, {"west-entry": "normal"})

    def test_load_layout_requires_exact_lowercase_toml_suffix(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for name in "layout", "layout.TOML", "layout.yaml":
                with self.subTest(name=name):
                    path = self.write_layout(directory, "schema-version = 1", name)
                    with self.assertRaises(LayoutConfigurationError) as raised:
                        load_layout(path)
                    self.assertEqual(raised.exception.diagnostics[0].code, "E001")

    def test_load_layout_reports_file_encoding_and_toml_errors(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            with self.assertRaises(LayoutConfigurationError) as raised:
                load_layout(directory / "missing.toml")
            self.assertEqual(raised.exception.diagnostics[0].code, "E002")

            invalid_encoding = directory / "invalid.toml"
            invalid_encoding.write_bytes(b"\xff")
            with self.assertRaises(LayoutConfigurationError) as raised:
                load_layout(invalid_encoding)
            self.assertEqual(raised.exception.diagnostics[0].code, "E003")

            malformed = self.write_layout(
                directory, "schema-version =", "malformed.toml"
            )
            with self.assertRaises(LayoutConfigurationError) as raised:
                load_layout(malformed)
            self.assertEqual(raised.exception.diagnostics[0].code, "E005")

    def test_validator_rejects_schema_and_local_object_violations(self) -> None:
        diagnostics = validate_layout_data(
            {
                "blocks": {"Bad_block": {"display-name": "", "unexpected": True}},
                "turnouts": {"west": {"positions": ["normal", "normal"]}},
                "routes": {"arrival": {"blocks": []}},
                "unknown": True,
            }
        )

        self.assertEqual(
            [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics],
            [
                ("E104", "unknown"),
                ("E101", "schema-version"),
                ("E110", "blocks.Bad_block"),
                ("E106", "blocks.Bad_block.unexpected"),
                ("E107", "blocks.Bad_block.display-name"),
                ("E125", "turnouts.west.positions[1]"),
                ("E134", "routes.arrival.blocks"),
            ],
        )

    def test_validator_rejects_unknown_references_and_invalid_position(self) -> None:
        diagnostics = validate_layout_data(
            {
                "schema-version": 1,
                "blocks": {"known": {}},
                "turnouts": {"west": {"positions": ["normal", "reverse"]}},
                "routes": {
                    "arrival": {
                        "blocks": ["missing"],
                        "turnouts": {"missing": "normal", "west": "straight"},
                    }
                },
            }
        )

        self.assertEqual(
            [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics],
            [
                ("E201", "routes.arrival.blocks[0]"),
                ("E202", "routes.arrival.turnouts.missing"),
                ("E203", "routes.arrival.turnouts.west"),
            ],
        )

    def test_diagnostic_keeps_source_separate_from_configuration_path(self) -> None:
        path = Path("layout.toml")
        diagnostic = validate_layout_data(
            {"schema-version": 1, "routes": {"arrival": {"blocks": []}}},
            source=path,
        )[-1]

        self.assertEqual(diagnostic.path, "routes.arrival.blocks")
        self.assertEqual(diagnostic.source, path)
        self.assertEqual(
            diagnostic.format(),
            "ERROR E134 layout.toml:routes.arrival.blocks:\n  must not be empty",
        )
