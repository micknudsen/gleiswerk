#!/usr/bin/env python3
"""Regenerate Gleiswerk's multi-platform Conda lockfile."""

import shutil
import subprocess
import sys
from pathlib import Path

ENVIRONMENT_NAME = "gleiswerk-dev"
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT_FILE = REPOSITORY_ROOT / "environment.yml"
LOCKFILE = REPOSITORY_ROOT / "gleiswerk.conda-lock.yml"
PLATFORMS = ("osx-arm64", "osx-64", "linux-64", "win-64")


def lock_command() -> tuple[str, ...]:
    """Build the command that refreshes every supported platform lock."""
    return (
        "conda",
        "run",
        "--no-capture-output",
        "--name",
        ENVIRONMENT_NAME,
        "conda-lock",
        "lock",
        "--micromamba",
        "--file",
        str(ENVIRONMENT_FILE),
        "--lockfile",
        str(LOCKFILE),
        *(argument for platform in PLATFORMS for argument in ("--platform", platform)),
    )


def main() -> int:
    """Regenerate the committed lockfile using the development environment."""
    if shutil.which("conda") is None:
        print("Conda must be available on PATH.", file=sys.stderr)
        return 1

    command = lock_command()
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
