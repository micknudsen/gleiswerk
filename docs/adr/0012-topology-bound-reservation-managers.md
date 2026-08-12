# 0012: Topology-bound reservation managers

- Status: Accepted
- Date: 2026-08-12

## Context

ADR 0011 originally described a reservation manager that could activate a new
topology revision after its reservations were drained. That makes the manager
have two separate lifecycle concerns: holding reservations and selecting its
topology. It also permits the binding that defines every reservation's meaning
to change during the manager's lifetime.

## Decision

`ReservationManager` is constructed with one validated immutable `Topology`
and retains that topology's revision for its entire lifetime. It accepts only
plans compiled for that exact revision. It has no activation or deactivation
operation and therefore cannot be unbound from a topology.

This decision supersedes ADR 0011's mutable topology-activation mechanism.

An application that adopts a new topology drains and discards the existing
manager, then constructs a fresh manager for the new topology. The new manager
starts with no reservations.

## Alternatives considered

### Mutable topology activation on one manager

This can enforce a drained state, but expands the manager's mutable state and
obscures the stable topology context of its reservations.

### Bind only a revision string

This is sufficient for a narrow comparison, but accepting the validated
topology makes the construction boundary explicit and prevents callers from
creating a manager without a topology.

## Consequences

- A manager is a smaller, topology-specific synchronization boundary.
- Topology replacement is explicit in the embedding application.
- The `no-active-topology` acquisition outcome is unnecessary and removed.
