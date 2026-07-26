# 0002: Distribution and release trigger

- Status: Accepted
- Date: 2026-07-26

## Context

Gleiswerk needs a small, reproducible release process that proves a package can
be built, tested, published, and installed in a clean environment. The project
is developed publicly and uses Conda for distribution.

## Decision

- The source repository is public from the beginning.
- Gleiswerk is released under the MIT License.
- Packages are published only to the `micknudsen` Conda channel.
- Package dependencies come from `conda-forge` with strict channel priority.
- Gleiswerk is not published to PyPI.
- Pushing a tag matching `v*` triggers the release workflow.
- A release tag must contain the same semantic version as the project metadata.
- Third-party GitHub Actions are pinned to immutable commit SHAs.

## Consequences

- The release workflow must reject malformed or mismatched tags before upload.
- Conda packages must be built and smoke-tested before publication.
- A successful tagged release creates both a GitHub Release and a Conda
  package.
- Python packaging metadata may be used for local and Conda builds, but no
  workflow or documentation may publish or direct users to PyPI.
