# 0003: Quality and dependency reproducibility

- Status: Accepted
- Date: 2026-07-26

## Context

Gleiswerk needs rapid feedback on basic correctness while ensuring developers
and CI use the same resolved dependencies across macOS, Linux, and Windows.

## Decision

- `environment.yml` declares the Conda development toolchain from
  `conda-forge`.
- `gleiswerk.conda-lock.yml` records fully resolved packages for `osx-arm64`,
  `osx-64`, `linux-64`, and `win-64`.
- Ruff checks formatting and lint rules, Pyright runs in strict mode, and
  Pytest runs the test suite.
- GitHub Actions installs the committed lock file directly on macOS, Linux,
  and Windows, then runs the quality suite.
- CI regenerates the lock file and fails if a dependency declaration changed
  without its corresponding lock update.

## Consequences

- Changes to `environment.yml` must include a regenerated lock file.
- Dependabot updates to Conda declarations require a lock-file update before
  they can merge.
- The quality rules begin with a focused baseline and can be tightened as the
  automation core grows.
