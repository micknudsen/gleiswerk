#!/usr/bin/env python3
"""Create or refresh the local Gleiswerk development environment."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ENVIRONMENT_NAME = "gleiswerk-dev"
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT_FILE = REPOSITORY_ROOT / "environment.yml"
LOCKFILE = REPOSITORY_ROOT / "gleiswerk.conda-lock.yml"


def run(*command: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def environment_prefix() -> Path | None:
    result = subprocess.run(
        ("conda", "env", "list", "--json"),
        check=True,
        capture_output=True,
        text=True,
    )
    prefixes = (Path(prefix) for prefix in json.loads(result.stdout)["envs"])
    return next(
        (prefix for prefix in prefixes if prefix.name == ENVIRONMENT_NAME), None
    )


def conda_lock_command(prefix: Path) -> str:
    if sys.platform == "win32":
        candidates = (
            prefix / "Scripts" / "conda-lock.exe",
            prefix / "Scripts" / "conda-lock.bat",
        )
    else:
        candidates = (prefix / "bin" / "conda-lock",)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(f"conda-lock is not installed in {ENVIRONMENT_NAME}.")


def main() -> int:
    if shutil.which("conda") is None:
        print("Conda must be available on PATH.", file=sys.stderr)
        return 1

    prefix = environment_prefix()
    if prefix is None:
        run(
            "conda",
            "env",
            "create",
            "--name",
            ENVIRONMENT_NAME,
            "--file",
            str(ENVIRONMENT_FILE),
        )
        prefix = environment_prefix()

    if prefix is None:
        raise RuntimeError(f"Failed to create {ENVIRONMENT_NAME}.")

    run(
        conda_lock_command(prefix),
        "install",
        "--name",
        ENVIRONMENT_NAME,
        str(LOCKFILE),
    )
    run(
        "conda",
        "run",
        "--no-capture-output",
        "--name",
        ENVIRONMENT_NAME,
        "python",
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        "--editable",
        str(REPOSITORY_ROOT),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
