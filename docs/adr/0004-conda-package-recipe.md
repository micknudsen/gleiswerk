# 0004: Conda package recipe

- Status: Accepted
- Date: 2026-07-26

## Context

Gleiswerk is distributed only through Conda. The initial release needs to prove
that its package can be built and installed independently of a development
checkout.

## Decision

- Use a Conda Build recipe in `conda-recipe`.
- Read the package version from `pyproject.toml`, which remains the sole version
  source.
- Build Gleiswerk as `noarch: python` while it remains a pure-Python package.
- Build from the checked-out source and use only `conda-forge` for recipe
  dependencies.
- Test the built package by importing Gleiswerk and running `gleiswerk --help`
  and `gleiswerk --version` in Conda Build's fresh test environment.

## Consequences

- A version change in `pyproject.toml` is automatically reflected in the Conda
  package.
- Platform-specific extensions or dependencies would require revisiting the
  `noarch: python` decision.
- CI builds and tests the package before a tagged release may publish it.
