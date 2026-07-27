# 0007: Release preparation

- Status: Accepted
- Date: 2026-07-27

## Context

Releases need a reviewable, repeatable preparation step that keeps the package
version, release notes, documentation, and local verification aligned. The
tag-triggered release workflow already protects publication, but it does not
define how a release is assembled and reviewed before a tag is created.

## Decision

- Prepare each release in a dedicated pull request.
- Keep `pyproject.toml` as the single authoritative package-version value.
- Commit release notes at `docs/releases/vX.Y.Z.md` for every release.
- Require release notes to state the new capability, configuration contract,
  and explicit non-goals.
- Use the committed release-notes file as the GitHub Release body.
- Require the full local quality, documentation, and Conda-package verification
  gate before requesting review.
- Do not tag, publish, or create a GitHub release as part of release
  preparation. Those actions require explicit maintainer approval after the
  preparation pull request is merged.
- Create release tags with a repository helper that derives the tag from
  `pyproject.toml`, verifies release readiness, and requires an explicit
  `--push` opt-in before triggering publication.

## Alternatives considered

- Rely only on generated GitHub release notes. This does not require the
  configuration contract or non-goals to be reviewed with the code.
- Keep release instructions only in contributor documentation. This would not
  record the durable project decision or its boundaries.
- Create and publish a release directly from a feature pull request. This
  couples reviewable preparation with irreversible publishing actions.

## Consequences

- Releases have a consistent, committed record that users can read in the
  documentation site and on the corresponding GitHub Release.
- Reviewers can verify versioning, scope, and release readiness before any
  publishing action is authorized.
- Release preparation introduces a small dedicated pull request even for
  otherwise simple version bumps.
