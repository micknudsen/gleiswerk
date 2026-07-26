# 0005: Documentation and release automation

- Status: Accepted
- Date: 2026-07-26

## Context

Gleiswerk is developed in public. Contributors and future users need a small,
maintained documentation site, and releases must deliver the tested Conda
package without a manual chain of local publishing steps.

## Decision

- Write project documentation in Markdown and build it with Material for
  MkDocs.
- Validate documentation with `mkdocs build --strict` in CI.
- Deploy the generated site to GitHub Pages using the GitHub Actions artifact
  deployment flow after changes reach `master`.
- Trigger releases only when a `v*` tag is pushed. Verify that the tag equals
  `v` plus the single package version in `pyproject.toml`.
- Build and test the Conda package before uploading it to the `micknudsen`
  channel and creating a GitHub release.
- Protect the publishing credential with a GitHub Actions `conda` environment.

## Consequences

- Documentation remains reviewable with its code and cannot be deployed from a
  separate `gh-pages` branch.
- A tagged release has a repeatable, test-gated delivery path.
- GitHub Pages and the protected `conda` environment require one-time
  repository configuration by a maintainer.
