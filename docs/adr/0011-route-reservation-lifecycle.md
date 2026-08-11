# 0011: Route-reservation lifecycle and safety invariants

- Status: Accepted
- Date: 2026-08-11

## Context

ADR 0010 defines an immutable `RoutePlan` with complete physical and protection claims plus required Control Device positions. Its compatibility analysis is static: it says whether plans can coexist, but it does not hold anything at runtime.

A reservation lifecycle is needed before the core can safely hold a plan's claims. This safety meaning must be independent of controller adapters, the simulator, the CLI, and the UI.

## Decision

The automation core owns a reservation manager for one active topology revision. It accepts validated immutable `RoutePlan` objects and maintains runtime `Reservation` records. A reservation is a runtime claim, not a configuration artifact.

### Identity and ownership

A successful acquire creates an opaque, manager-generated reservation ID. It identifies one live record and is never inferred from a route ID, plan contents, or an external request ID. The record retains its ID, supplied opaque owner identity, plan identity, exact topology revision, and the plan's derived claim and Control Device constraint sets. Release therefore never depends on a caller resupplying a plan.

The caller supplies a stable owner identity on acquire. The manager treats it as opaque and requires the same identity to release the record. Authentication and authorization are the embedding application's responsibility, but an owner mismatch must never release another owner's reservation. A reservation ID is not authorization by itself.

### Acquire lifecycle and claims

Acquire takes an owner and one `RoutePlan`. It succeeds only when all checks pass at one atomic decision point:

1. The plan is validated and its topology revision exactly equals the manager's active topology revision.
2. Its physical and protection claims do not intersect those of any live reservation.
3. Every required Control Device has no live reservation requiring a different value.

On success, the manager installs the entire record and returns its ID. Acquire is not idempotent: every call requests a new reservation. A repeated acquire for a plan that overlaps its still-live exclusive claim deterministically returns `incompatible`; callers must retain a successfully returned ID for retry-safe transport behavior.

Every `TrackSection`, `Junction`, and `ProtectionZone` claim is exclusive. No two live reservations may hold the same physical or protection resource, regardless of owner, route name, or travel direction. Control Device constraints are shared-value claims: several reservations may require one device only when all require exactly the same logical position. The manager retains that value until the final holder releases it. A different value is incompatible even with no shared physical claim.

### Release lifecycle

Release takes an owner and reservation ID. For a live record held by that owner, it atomically removes the entire record, all exclusive claims, and its participation in every shared-value device constraint. A device constraint remains held while at least one record still requires that value.

Release never partially releases a route. Phased release and train-clearance rules are separate future safety decisions. Releasing an unknown or already released ID deterministically returns `not-found` and changes no state. Releasing a live ID with another owner deterministically returns `not-owner` and changes no state; neither outcome reveals reservation details.

### Atomicity, failure, and topology activation

Acquire and release are linearizable: concurrent calls behave as if each took effect at one instant. Validation, compatibility checking, and installation or removal of every associated claim occur as one transaction. A failed acquire—including an invalid plan, revision mismatch, or incompatibility—creates no reservation and changes no claim or device constraint. A failed release likewise changes no state.

The active topology revision cannot change while any reservation is live. An activation request with live reservations is rejected. Once the final release completes, activation establishes a fresh empty reservation state. A reservation therefore never spans revisions, even if all referenced IDs still exist. A manager with no active topology revision rejects acquire.

The manager reports stable outcome categories: `acquired`, `released`, `not-found`, `not-owner`, `invalid-plan`, `revision-mismatch`, `incompatible`, and `no-active-topology`. Exact diagnostic codes and transport representation remain implementation details; the outcome category and state change are deterministic.

### Boundary of this decision

A reservation is not a device command, device or occupancy observation, signal aspect, or `MovementAuthority`. Acquiring it neither moves a Control Device nor proves its position; it neither detects a train nor permits movement. A later movement-authority decision must separately require the relevant reservations, fresh safety evidence, configured device-position evidence, and its own bounded-authority rules.

Reservations do not persist across process restart in this decision. On startup, the manager has no live reservations and downstream safety state is unknown until separately established. It must not reconstruct claims from commands, plans, or stale observations.

## Alternatives considered

### Let each adapter or UI track reservations

That would make safety semantics depend on controller protocol behavior and permit simulator and hardware paths to disagree. A core manager gives every client the same conflict and release semantics.

### Use static compatibility output as a lock

Compatibility is a statement about plans, not current ownership. It cannot reserve resources between analysis and use, identify a releaser, or retain a shared device value.

### Permit partial or automatic release

This could improve throughput, but it requires occupancy and clearance evidence outside this decision. Whole-plan release is conservative and avoids silently coupling reservations to unimplemented train tracking.

### Allow old reservations after topology activation

Matching resource IDs do not prove unchanged physical meaning, protection, or device requirements. Exact revision matching is the safe default.

## Consequences

- A future implementation has a small controller-independent API with explicit ownership, atomicity, and error behavior.
- Static RoutePlan compatibility remains analysis, not runtime locking.
- Topology changes are operationally gated until reservations are drained.
- Device actuation, observations, occupancy-based release, persistence, and movement authority remain separate work.
