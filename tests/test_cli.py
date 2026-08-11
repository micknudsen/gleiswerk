"""Tests for the public command-line interface."""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import yaml


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


def test_layout_validate_accepts_a_schema_version_3_layout(tmp_path: Path) -> None:
    layout = tmp_path / "layout.yaml"
    layout.write_text(
        """schema-version: 3
track-sections:
  entry:
    ports: [west, east]
    terminal-ports: [west, east]
    movements: [{from: west, to: east}]
""",
        encoding="utf-8",
    )
    supplied_path = f"{tmp_path}/./layout.yaml"

    result = run_module("layout", "validate", supplied_path)

    assert result.returncode == 0
    assert result.stdout == f"Layout is valid: {supplied_path}\n"
    assert result.stderr == ""


def test_layout_validate_rejects_schema_version_2(tmp_path: Path) -> None:
    layout = tmp_path / "legacy.yaml"
    layout.write_text("schema-version: 2\n", encoding="utf-8")

    result = run_module("layout", "validate", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E103 {layout}:schema-version:\n  unsupported schema version 2\n"
    )


def test_layout_validate_reports_topology_diagnostics(tmp_path: Path) -> None:
    layout = tmp_path / "disconnected.yaml"
    layout.write_text(
        """schema-version: 3
track-sections:
  entry:
    ports: [west, east]
    terminal-ports: [west]
    movements: [{from: west, to: east}]
""",
        encoding="utf-8",
    )

    result = run_module("layout", "validate", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E204 {layout}:track-sections.entry.ports[1]:\n"
        "  nonterminal port has no connection\n"
    )


def test_layout_compatibility_reports_a_stable_structured_result() -> None:
    layout = Path("tests/fixtures/schema_v3/valid-direct.yaml")

    result = run_module("layout", "compatibility", str(layout))

    assert result.returncode == 0
    assert result.stderr == ""
    assert yaml.safe_load(result.stdout) == {
        "topology-revision": "sha256:"
        "d3142628cbd9500f0056c08d3eaad8cdb5ffcacaf0be818f277b4533e23e0dba",
        "pairs": [
            {
                "route-pair": ["direct-arrival", "within-platform"],
                "compatible": False,
                "conflicts": [
                    {
                        "kind": "overlapping-exclusive-claim",
                        "resource": "track-section:platform",
                        "provenance": {
                            "direct-arrival": ["track-section:platform"],
                            "within-platform": ["track-section:platform"],
                        },
                    }
                ],
            }
        ],
    }


def test_layout_compatibility_reports_compatible_routes() -> None:
    layout = Path("tests/fixtures/schema_v3/valid-station.yaml")

    result = run_module("layout", "compatibility", str(layout))

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert {
        "route-pair": ["depot-only", "west-to-east-via-platform-1"],
        "compatible": True,
        "conflicts": [],
    } in report["pairs"]


def test_layout_compatibility_reports_topology_diagnostics(tmp_path: Path) -> None:
    layout = tmp_path / "invalid.yaml"
    layout.write_text("schema-version: 2\n", encoding="utf-8")

    result = run_module("layout", "compatibility", str(layout))

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR E103 {layout}:schema-version:\n  unsupported schema version 2\n"
    )
