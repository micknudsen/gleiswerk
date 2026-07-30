"""Tests for the public command-line interface."""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path


def run_module(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the installed Gleiswerk module in a separate process."""
    return subprocess.run(
        [sys.executable, "-m", "gleiswerk", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_help_succeeds() -> None:
    result = run_module("--help")

    assert result.returncode == 0
    assert "usage: gleiswerk" in result.stdout
    assert result.stderr == ""


def test_version_reports_distribution_version() -> None:
    result = run_module("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"Gleiswerk {version('gleiswerk')}"
    assert result.stderr == ""


def test_layout_validate_accepts_a_schema_version_2_layout(tmp_path: Path) -> None:
    layout = tmp_path / "layout.toml"
    layout.write_text(
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
    supplied_path = f"{tmp_path}/./layout.toml"

    result = run_module("layout", "validate", supplied_path)

    assert result.returncode == 0
    assert result.stdout == f"Layout is valid: {supplied_path}\n"
    assert result.stderr == ""


def test_layout_validate_rejects_schema_version_1(tmp_path: Path) -> None:
    layout = tmp_path / "legacy.toml"
    layout.write_text("schema-version = 1\n", encoding="utf-8")

    result = run_module("layout", "validate", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E103 {layout}:schema-version:\n  unsupported schema version 1\n"
    )


def test_layout_validate_reports_route_continuity_diagnostics(tmp_path: Path) -> None:
    layout = tmp_path / "disconnected.toml"
    layout.write_text(
        """schema-version = 2

[blocks.west-entry]
endpoints = ["west", "east"]

[blocks.platform-1]
endpoints = ["west", "east"]

[blocks.depot]
endpoints = ["west", "east"]

[traversals.west-to-platform]
from = "west-entry.east"
to = "platform-1.west"

[traversals.platform-to-depot]
from = "platform-1.east"
to = "depot.west"

[routes.arrival]
traversals = ["west-to-platform", "platform-to-depot"]
""",
        encoding="utf-8",
    )

    result = run_module("layout", "validate", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E205 {layout}:routes.arrival.traversals[1]:\n"
        "  traversal 'west-to-platform' does not connect to "
        "'platform-to-depot'\n"
    )
