# 0008: Approval-gated milestone planning

- Status: Accepted
- Date: 2026-07-28

## Context

Gleiswerk needs a repeatable way to turn an agreed product direction into small,
reviewable changes without treating planning artifacts or release actions as
automatic. Milestones and GitHub issues make the intended delivery sequence
visible, but creating them commits the project to a public representation of a
plan. The project also needs a clear boundary between agreeing a plan, doing a
piece of work, and publishing a release.

## Decision

Plan releases through an approval-gated sequence:

1. Draft a local milestone proposal containing its user outcome, non-goals,
   release criteria, ordered issues, and dependencies.
2. Obtain explicit maintainer approval before creating the corresponding
   GitHub milestone or issues. Approval of a milestone proposal authorizes
   only the agreed planning artifacts, not implementation, pushes, tags, or
   publication.
3. Before implementing each issue, agree its problem statement, acceptance
   criteria, proposed interface or configuration changes, tests,
   documentation, dependencies, and non-goals. Record durable technical
   decisions in an ADR before implementation.
4. Keep implementation changes focused: one coherent concern per pull request.
5. Include a final release-preparation issue in every milestone. It verifies
   completed scope, prepares the version and release notes, updates affected
   documentation, and passes the full release gate defined in ADR 0007.
6. After the release-preparation pull request is merged, require separate,
   explicit approval before creating or pushing the matching release tag.
   Publication remains the tag-triggered process defined in ADR 0002.

The milestone proposal and every issue should answer the questions appropriate
to its level. A milestone defines the user-visible result and release boundary;
an issue defines the smallest testable contribution toward that result.

## Alternatives considered

### Create planning artifacts as soon as a direction is discussed

This is quick, but it risks publishing incomplete or unapproved scope and can
make exploratory discussion appear to be a commitment.

### Use only pull requests to organize work

Pull requests show implementation, but do not provide a clear release-level
view of intended outcomes, sequencing, and remaining work.

### Require one approval for an entire milestone

This reduces coordination overhead, but allows technical decisions and scope to
drift after the initial plan without a deliberate review point.

## Consequences

- Project plans are visible and traceable only after maintainer approval.
- Each implementation starts with testable scope and explicit non-goals.
- A release-preparation issue makes release work visible without conflating it
  with irreversible tag and publication approval.
- Planning takes a small deliberate step before GitHub artifacts exist.
