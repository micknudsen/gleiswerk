"""Executable layout examples and invalid validation fixtures."""

import subprocess
import sys
import unittest
from pathlib import Path

from gleiswerk.layout_config import LayoutConfigurationError, load_layout

REPOSITORY_ROOT = Path(__file__).parent.parent
REFERENCE_LAYOUT = REPOSITORY_ROOT / "examples" / "reference-layout.toml"
INVALID_LAYOUTS = REPOSITORY_ROOT / "tests" / "fixtures" / "layout"


class LayoutFixtureTest(unittest.TestCase):
    def test_reference_layout_validates_through_the_public_cli(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "gleiswerk",
                "layout",
                "validate",
                str(REFERENCE_LAYOUT),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"Layout is valid: {REFERENCE_LAYOUT}\n")
        self.assertEqual(result.stderr, "")

    def test_invalid_layout_fixtures_report_their_validation_rules(self) -> None:
        expected_codes_by_fixture = {
            "invalid-syntax.toml": ["E005"],
            "invalid-top-level.toml": ["E104", "E102", "E105"],
            "missing-schema-version.toml": ["E101"],
            "unsupported-schema-version.toml": ["E103"],
            "invalid-blocks.toml": ["E110", "E106", "E107", "E111"],
            "invalid-turnouts.toml": [
                "E120",
                "E106",
                "E125",
                "E126",
                "E107",
                "E122",
                "E121",
                "E123",
                "E124",
            ],
            "invalid-routes.toml": [
                "E130",
                "E106",
                "E132",
                "E107",
                "E133",
                "E134",
                "E135",
                "E136",
                "E138",
                "E139",
                "E132",
                "E131",
                "E137",
            ],
            "invalid-references.toml": ["E201", "E202", "E203"],
        }

        for fixture_name, expected_codes in expected_codes_by_fixture.items():
            with self.subTest(fixture_name=fixture_name):
                with self.assertRaises(LayoutConfigurationError) as raised:
                    load_layout(INVALID_LAYOUTS / fixture_name)

                self.assertEqual(
                    [diagnostic.code for diagnostic in raised.exception.diagnostics],
                    expected_codes,
                )
