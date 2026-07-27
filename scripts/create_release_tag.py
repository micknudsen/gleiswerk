#!/usr/bin/env python3
"""Create a verified release tag from Gleiswerk's package metadata."""

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPOSITORY_ROOT / "pyproject.toml"
RELEASE_NOTES_DIRECTORY = REPOSITORY_ROOT / "docs" / "releases"
TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+$")


def run_git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git from the repository root and capture its text output."""
    return subprocess.run(
        ("git", *arguments),
        cwd=REPOSITORY_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def release_tag() -> str:
    """Read and validate the version-derived release tag."""
    with VERSION_FILE.open("rb") as version_file:
        version = tomllib.load(version_file)["project"]["version"]

    if not isinstance(version, str):
        raise ValueError("project.version in pyproject.toml must be a string")

    tag = f"v{version}"
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(
            "project.version must use major.minor.patch form to create a release tag"
        )
    return tag


def require_release_ready(tag: str, push: bool) -> bool:
    """Verify readiness and report whether a safe local tag already exists."""
    branch = run_git("branch", "--show-current").stdout.strip()
    if branch != "master":
        raise ValueError(
            f"release tags must be created from master, not {branch or 'HEAD'}"
        )

    if run_git("status", "--porcelain").stdout:
        raise ValueError("working tree must be clean before creating a release tag")

    head = run_git("rev-parse", "HEAD").stdout.strip()
    remote_master = run_git("rev-parse", "origin/master").stdout.strip()
    if head != remote_master:
        raise ValueError(
            "local master must match origin/master before creating a release tag"
        )

    release_notes = RELEASE_NOTES_DIRECTORY / f"{tag}.md"
    if not release_notes.is_file():
        relative_notes = release_notes.relative_to(REPOSITORY_ROOT)
        raise ValueError(f"required release notes are missing: {relative_notes}")

    local_tag = run_git(
        "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", check=False
    )
    tag_exists_locally = local_tag.returncode == 0
    if tag_exists_locally:
        tag_type = run_git("cat-file", "--type", f"refs/tags/{tag}").stdout.strip()
        if tag_type != "tag":
            raise ValueError(f"local tag must be annotated: {tag}")

        tagged_commit = run_git("rev-list", "--max-count=1", tag).stdout.strip()
        if tagged_commit != head:
            raise ValueError(f"local tag does not point to current master: {tag}")

        if not push:
            raise ValueError(f"tag already exists locally: {tag}")

    remote_tag = run_git(
        "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}", check=False
    )
    if remote_tag.returncode == 0:
        raise ValueError(f"tag already exists on origin: {tag}")

    return tag_exists_locally


def create_tag(tag: str, push: bool, tag_exists_locally: bool) -> None:
    """Create or reuse the local annotated tag and optionally push it."""
    if tag_exists_locally:
        print(f"Reusing local annotated tag {tag}.")
    else:
        run_git("tag", "--annotate", tag, "--message", f"Release {tag}")
        print(f"Created local annotated tag {tag}.")

    if push:
        run_git("push", "origin", tag)
        print(f"Pushed {tag}; the release workflow can now start.")
    else:
        print("Review it, then run: python scripts/create_release_tag.py --push")


def parse_arguments() -> argparse.Namespace:
    """Parse the explicit publication opt-in."""
    parser = argparse.ArgumentParser(
        description="Create a release tag derived from pyproject.toml."
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="push the new tag to origin and trigger the release workflow",
    )
    return parser.parse_args()


def main() -> int:
    """Create a verified local release tag, optionally pushing it."""
    try:
        arguments = parse_arguments()
        tag = release_tag()
        tag_exists_locally = require_release_ready(tag, arguments.push)
        create_tag(tag, arguments.push, tag_exists_locally)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Release tag not created: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
