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


def test_commissioning_requires_explicit_live_hardware_acknowledgement() -> None:
    result = run_module(
        "commissioning",
        "verify",
        "layout.yaml",
        "binding.yaml",
        "capture.yaml",
        "expectations.yaml",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        result.stderr
        == "ERROR --live-hardware is required for commissioning verification\n"
    )


def test_commissioning_capture_requires_explicit_live_hardware_acknowledgement() -> (
    None
):
    result = run_module(
        "commissioning",
        "capture",
        "layout.yaml",
        "binding.yaml",
        "http://192.0.2.17",
        "2.6.1 (Build 3)",
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert (
        result.stderr == "ERROR --live-hardware is required for commissioning capture\n"
    )


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


def test_documented_conflicting_reference_layout_reports_a_stable_result() -> None:
    layout = Path("tests/fixtures/schema_v3/valid-direct.yaml")

    result = run_module("layout", "compatibility", str(layout))

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "topology-revision: sha256:"
        "9f8a1e165ba31073b9a5e887c8c854e90cfe1cda302cde76fbaa4dcf60df16cb\n"
        "pairs:\n"
        "- route-pair: [direct-arrival, within-platform]\n"
        "  compatible: false\n"
        "  conflicts:\n"
        "  - kind: overlapping-exclusive-claim\n"
        "    resource: track-section:platform\n"
        "    provenance:\n"
        "      direct-arrival: [track-section:platform]\n"
        "      within-platform: [track-section:platform]\n"
    )
    assert yaml.safe_load(result.stdout) == {
        "topology-revision": "sha256:"
        "9f8a1e165ba31073b9a5e887c8c854e90cfe1cda302cde76fbaa4dcf60df16cb",
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


def test_documented_compatible_reference_layout_reports_compatible_routes() -> None:
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


def test_layout_reservations_evaluates_compatible_acquisition_and_release() -> None:
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-station.yaml",
        "tests/fixtures/reservation_operations/compatible.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert [operation["outcome"] for operation in report["operations"]] == [
        "acquired",
        "acquired",
        "released",
        "released",
    ]
    assert all(operation["success"] for operation in report["operations"])
    assert report["held-reservations"] == []


def test_layout_reservations_reports_structured_incompatible_denial() -> None:
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-direct.yaml",
        "tests/fixtures/reservation_operations/denied.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "topology-revision: sha256:"
        "9f8a1e165ba31073b9a5e887c8c854e90cfe1cda302cde76fbaa4dcf60df16cb\n"
        "operations:\n"
        "- operation: acquire\n"
        "  owner: dispatcher-a\n"
        "  route: direct-arrival\n"
        "  success: true\n"
        "  outcome: acquired\n"
        "  reservation: reservation-1\n"
        "- operation: acquire\n"
        "  owner: dispatcher-b\n"
        "  route: within-platform\n"
        "  success: false\n"
        "  outcome: incompatible\n"
        "  denial:\n"
        "    kind: incompatible\n"
        "    claim-conflicts:\n"
        "    - resource: track-section:platform\n"
        "      requested-provenance: [track-section:platform]\n"
        "      held-reservation: reservation-1\n"
        "      held-provenance: [track-section:platform]\n"
        "    device-constraint-conflicts: []\n"
        "- operation: release\n"
        "  owner: dispatcher-a\n"
        "  reservation: reservation-1\n"
        "  success: true\n"
        "  outcome: released\n"
        "held-reservations: []\n"
    )
    report = yaml.safe_load(result.stdout)
    denied = report["operations"][1]
    assert denied == {
        "operation": "acquire",
        "owner": "dispatcher-b",
        "route": "within-platform",
        "success": False,
        "outcome": "incompatible",
        "denial": {
            "kind": "incompatible",
            "claim-conflicts": [
                {
                    "resource": "track-section:platform",
                    "requested-provenance": ["track-section:platform"],
                    "held-reservation": "reservation-1",
                    "held-provenance": ["track-section:platform"],
                }
            ],
            "device-constraint-conflicts": [],
        },
    }
    assert report["held-reservations"] == []


def test_layout_reservations_grants_authority_for_fresh_clear_evidence() -> None:
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-grant.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert report["operations"][-1] == {
        "operation": "evaluate-authority",
        "owner": "dispatcher-a",
        "reservation": "reservation-1",
        "route": "west-to-main",
        "valid-for-seconds": 20,
        "success": True,
        "outcome": "granted",
        "authority": "authority-1",
        "evidence": {
            "topology-revision": report["topology-revision"],
            "route": "west-to-main",
            "occupancy": [
                {"zone": "main-detector", "source": "main-source", "outcome": "clear"},
                {
                    "zone": "throat-detector",
                    "source": "throat-source",
                    "outcome": "clear",
                },
            ],
            "device-positions": [
                {
                    "device": "throat-turnout",
                    "required-position": "normal",
                    "source": "turnout-source",
                    "outcome": "aligned",
                }
            ],
            "rejections": [],
        },
    }
    assert report["authorities"] == [
        {
            "id": "authority-1",
            "reservation": "reservation-1",
            "owner": "dispatcher-a",
            "route": "west-to-main",
            "topology-revision": report["topology-revision"],
            "scope": [
                "junction:throat",
                "track-section:main",
                "track-section:west",
            ],
            "issued-at-seconds": 0.0,
            "expires-at-seconds": 20.0,
            "status": "live",
        }
    ]
    assert [item["id"] for item in report["held-reservations"]] == ["reservation-1"]

    repeated = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-grant.yaml",
    )
    assert repeated.stdout == result.stdout


def test_layout_reservations_requires_explicit_authority_settings(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text(
        """operations:
  - operation: advance-time
    seconds: 1
""",
        encoding="utf-8",
    )

    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        str(workflow),
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"ERROR {workflow}: authority workflows require explicit top-level settings\n"
    )


def test_layout_reservations_denies_stale_evidence_without_releasing_reservation() -> (
    None
):
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-stale.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert report["operations"][-1]["outcome"] == "denied"
    assert report["operations"][-1]["denial"] == {
        "kind": "occupancy-evidence",
        "target": "main-detector",
        "evidence-rejection": {
            "kind": "stale",
            "target": "main-detector",
            "sources": ["main-source"],
        },
    }
    assert report["operations"][-1]["evidence"]["occupancy"] == [
        {"zone": "main-detector", "source": "main-source", "outcome": "stale"},
        {
            "zone": "throat-detector",
            "source": "throat-source",
            "outcome": "stale",
        },
    ]
    assert report["authorities"] == []
    assert [item["id"] for item in report["held-reservations"]] == ["reservation-1"]


def test_layout_reservations_revokes_for_device_mismatch_and_retains_reservation() -> (
    None
):
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-device-revocation.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert report["operations"][-1] == {
        "operation": "reevaluate-authority",
        "authority": "authority-1",
        "route": "west-to-main",
        "success": False,
        "outcome": "revoked",
        "revocation": {
            "kind": "device-position-evidence",
            "target": "throat-turnout",
            "evidence-rejection": {
                "kind": "unaligned",
                "target": "throat-turnout",
                "sources": ["turnout-source"],
            },
        },
        "evidence": {
            "topology-revision": report["topology-revision"],
            "route": "west-to-main",
            "occupancy": [
                {"zone": "main-detector", "source": "main-source", "outcome": "clear"},
                {
                    "zone": "throat-detector",
                    "source": "throat-source",
                    "outcome": "clear",
                },
            ],
            "device-positions": [
                {
                    "device": "throat-turnout",
                    "required-position": "normal",
                    "source": "turnout-source",
                    "outcome": "unaligned",
                }
            ],
            "rejections": [
                {
                    "kind": "unaligned",
                    "target": "throat-turnout",
                    "sources": ["turnout-source"],
                }
            ],
        },
    }
    assert report["authorities"][0]["status"] == "revoked"
    assert report["authorities"][0]["revocation"]["kind"] == (
        "device-position-evidence"
    )
    assert [item["id"] for item in report["held-reservations"]] == ["reservation-1"]


def test_layout_reservations_reports_occupied_and_unknown_evidence_denials() -> None:
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-evidence-denials.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    evaluations = [
        operation
        for operation in report["operations"]
        if operation["operation"] == "evaluate-authority"
    ]
    assert [operation["outcome"] for operation in evaluations] == [
        "denied",
        "denied",
    ]
    assert [
        operation["denial"]["evidence-rejection"]["kind"] for operation in evaluations
    ] == ["occupied", "unknown"]
    assert report["authorities"] == []


def test_layout_reservations_expires_authority_without_releasing_reservation() -> None:
    result = run_module(
        "layout",
        "reservations",
        "tests/fixtures/schema_v3/valid-occupancy.yaml",
        "tests/fixtures/reservation_operations/authority-expiry.yaml",
    )

    assert result.returncode == 0
    assert result.stderr == ""
    report = yaml.safe_load(result.stdout)
    assert report["operations"][-1]["outcome"] == "revoked"
    assert report["operations"][-1]["revocation"] == {
        "kind": "expiration",
        "target": "reservation-1",
    }
    assert report["authorities"][0]["status"] == "revoked"
    assert report["authorities"][0]["revocation"]["kind"] == "expiration"
    assert [item["id"] for item in report["held-reservations"]] == ["reservation-1"]
