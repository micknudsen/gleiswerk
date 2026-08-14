# Movement-authority contract

`gleiswerk.movement_authority` provides a controller-independent, in-memory
decision over an existing reservation and a validated logical-evidence result.
It does not command a Control Device, set a signal, dispatch a train, or grant
permission to move a real train.

## Evaluation

Construct `MovementAuthorityEvaluator` with one immutable topology revision, a
positive maximum validity, and an injected monotonic clock. Call `evaluate()`
with a `MovementAuthorityRequest` and current `ReservationInspection`.

The evaluator grants an opaque `MovementAuthority` only when the named
reservation is live and owned by the caller, the validated evidence refers to
the reservation's route and exact topology revision, every evidence
prerequisite is usable, and the requested positive duration does not exceed the
configured bound. Its scope is exactly the reservation's complete claims and
its expiration is an explicit value on the same monotonic-clock scale.

Denials are immutable `MovementAuthorityFailure` values. Categories are checked
in this order: reservation, scope, topology revision, occupancy evidence,
device-position evidence, then expiration. Evidence failures retain the
validator's logical target and source provenance without exposing mutable
reservation-manager state.

## Continuous validity

Call `reevaluate()` with current reservation and evidence snapshots to check a
live authority. A missing or released reservation, ownership change, scope or
revision mismatch, unusable evidence, or elapsed expiration transitions the
record once to `revoked`. The first failure is retained permanently; a revoked
authority cannot be reactivated, transferred, or renewed.

Revocation never releases the reservation. Reservations remain the separate
owner-authorized, whole-reservation concern of `gleiswerk.route_reservations`.
`inspect()` exposes both live and revoked records in stable opaque-ID order.
