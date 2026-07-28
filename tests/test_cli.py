"""Tests for the Gleiswerk command-line interface."""

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
    assert "--version" in result.stdout
    assert result.stderr == ""


def test_version_reports_distribution_version() -> None:
    result = run_module("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"Gleiswerk {version('gleiswerk')}"
    assert result.stderr == ""


def test_no_arguments_succeeds() -> None:
    result = run_module()

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_layout_validate_help_documents_the_file_argument() -> None:
    result = run_module("layout", "validate", "--help")

    assert result.returncode == 0
    assert "usage: gleiswerk layout validate" in result.stdout
    assert "FILE" in result.stdout
    assert result.stderr == ""


def test_layout_validate_reports_success_for_a_valid_layout(tmp_path: Path) -> None:
    layout = tmp_path / "layout.toml"
    layout.write_text("schema-version = 1\n", encoding="utf-8")
    supplied_path = f"{tmp_path}/./layout.toml"

    result = run_module("layout", "validate", supplied_path)

    assert result.returncode == 0
    assert result.stdout == f"Layout is valid: {supplied_path}\n"
    assert result.stderr == ""


def test_layout_validate_accepts_the_shipped_reference_layout() -> None:
    example = Path("examples/reference-layout.toml")

    result = run_module("layout", "validate", str(example))

    assert result.returncode == 0
    assert result.stdout == f"Layout is valid: {example}\n"
    assert result.stderr == ""


def test_layout_validate_reports_diagnostics_for_an_invalid_layout(
    tmp_path: Path,
) -> None:
    layout = tmp_path / "invalid.toml"
    layout.write_text("schema-version = 2\n", encoding="utf-8")

    result = run_module("layout", "validate", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E103 {layout}:schema-version:\n  unsupported schema version 2\n"
    )


def test_layout_conflicts_reports_no_conflicts_for_the_reference_layout() -> None:
    example = Path("examples/reference-layout.toml")

    result = run_module("layout", "conflicts", str(example))

    assert result.returncode == 0
    assert result.stdout == f"No route conflicts: {example}\n"
    assert result.stderr == ""


def test_layout_conflicts_reports_every_conflict_from_a_fixture() -> None:
    fixture = Path("tests/fixtures/conflicting-layout.toml")

    result = run_module("layout", "conflicts", str(fixture))

    assert result.returncode == 2
    assert result.stdout == (
        f"Route conflicts: {fixture}\n"
        "arrival-to-platform-1, departure-from-platform-1: "
        "shared block platform-1\n"
        "arrival-to-platform-1, departure-from-platform-1: "
        "incompatible turnout west-throat (normal, reverse)\n"
    )
    assert result.stderr == ""


def test_layout_conflicts_preserves_validation_diagnostics(tmp_path: Path) -> None:
    layout = tmp_path / "invalid.toml"
    layout.write_text("schema-version = 2\n", encoding="utf-8")

    result = run_module("layout", "conflicts", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E103 {layout}:schema-version:\n  unsupported schema version 2\n"
    )
