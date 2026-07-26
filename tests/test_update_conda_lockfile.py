"""Tests for the Conda lockfile update helper."""

from pathlib import Path
from runpy import run_path

SCRIPT = Path(__file__).parents[1] / "scripts" / "update_conda_lockfile.py"
MODULE = run_path(str(SCRIPT))


def test_lock_command_targets_every_supported_platform() -> None:
    command = MODULE["lock_command"]()

    assert command[:7] == (
        "conda",
        "run",
        "--no-capture-output",
        "--name",
        "gleiswerk-dev",
        "conda-lock",
        "lock",
    )
    assert command[-8:] == (
        "--platform",
        "osx-arm64",
        "--platform",
        "osx-64",
        "--platform",
        "linux-64",
        "--platform",
        "win-64",
    )
