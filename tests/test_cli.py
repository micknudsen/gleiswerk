"""Tests for the Gleiswerk command-line interface."""

import subprocess
import sys
from importlib.metadata import version


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
