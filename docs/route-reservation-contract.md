# Route reservation contract

Status: implementation contract. This document defines the immutable values
used by the controller-independent route-reservation API. They are available
from `gleiswerk.route_reservations`. It specifies the inputs, records,
outcomes, and explanations; it does not implement a manager, persistence, or
device control.

## Boundary

An acquire request contains an opaque owner identity and one validated,
immutable `RoutePlan`. A release request contains the same owner identity and
an opaque reservation ID previously returned by the manager. The manager—not
the caller—creates reservation IDs. They must never be inferred from a route
ID, a plan, or an external request ID.

`Reservation` is the immutable runtime record returned on successful acquire
and exposed by inspection. It contains its ID, owner, Route Definition ID,
exact topology revision, claims, Control Device requirements, and complete
claim and requirement provenance. `ReservationInspection` returns the active
topology revision (or `null`) plus a deterministic read-only tuple of held
records.

Neither the requests nor results command devices, establish observations,
detect train presence, clear signals, or authorize movement.

## Acquire result

`AcquireReservationResult` has `outcome`, `reservation`, and
`denial_reason`.

- `acquired` has a `Reservation` and no denial reason.
- `no-active-topology` has `NoActiveTopology` and no reservation.
- `invalid-plan` has `InvalidReservationPlan` and no reservation.
- `revision-mismatch` has `TopologyRevisionMismatch`, which includes both the
  active and plan topology revisions.
- `incompatible` has `IncompatibleReservation` and no reservation.

An incompatible denial preserves all discovered blockers. Every
`OverlappingReservationClaim` names the exclusive resource, the requested
provenance, the already-held reservation ID, and that reservation's
provenance. Every `IncompatibleReservationDeviceConstraint` similarly names
the Control Device, the requested and held position, both provenance lists,
and the held reservation ID. This makes conflicts explainable without making
an ownership decision for the embedding application.

## Release result

`ReleaseReservationResult` has `outcome`, `reservation_id`, and
`denial_reason`.

- `released` returns the released opaque ID and no denial reason.
- `not-found` has `ReservationNotFound` and does not change state.
- `not-owner` has `ReservationNotOwner` and does not expose the held record.

Release is always whole-reservation: the contract has no partial release
result.

## Determinism and immutability

All public collection fields are copied into tuples or read-only mappings.
Reservations are ordered by opaque reservation ID. Claims and claim conflicts
are ordered lexicographically by resource-kind label and ID. Device requirements and device conflicts are
ordered by Control Device ID; a held reservation ID breaks a remaining tie.
Provenance maps use those same keys, and their source lists retain the
compiler's order.

The contract makes result ordering stable. `ReservationManager` performs the
atomic in-memory state transition. Its `acquire`, `release`, and `inspect`
methods take and return the values above. `activate_topology` changes the
active revision only while inspection is empty; otherwise it returns `false`
and preserves the complete live state. The manager is in-memory only and does
not command devices, interpret observations, or authorize movement.
