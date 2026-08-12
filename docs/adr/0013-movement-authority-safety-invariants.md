# 0013: Movement-authority safety invariants

- Status: Accepted
- Date: 2026-08-12

## Context

A live RoutePlan reservation prevents incompatible concurrent claims. It is
not proof that the route is clear, that the required Control Devices reached
their positions, or that a train may move. Before a movement-authority API is
introduced, Gleiswerk needs a controller-independent decision that keeps those
meanings separate and fails closed when its evidence no longer supports an
authority.

## Decision

A `MovementAuthority` is a distinct, opaque, runtime record issued by the
automation core. The issuer generates its identity; callers must not derive it
from a route, reservation, train, or request identifier. The record binds:

- exactly one live reservation ID and its owner;
- the reservation's exact topology revision and RoutePlan identity;
- a bounded scope derived from that plan's complete claims; and
- an explicit expiration instant.

The bounded scope is the only scope asserted by the authority. It must not be
silently extended by an adjacent reservation, a later topology revision, or a
new observation. Authority duration is finite and is evaluated against a
monotonic time source. An authority is no longer live at its expiration
instant; no grace period or implicit renewal is permitted.

### Issuance prerequisites

Issuance is one atomic, fail-closed decision. It succeeds only when all of the
following are true at that decision point:

1. The named reservation is live, belongs to the supplied owner, and retains a
   valid RoutePlan for the requested authority scope.
2. The issuer's validated topology and all evidence are for exactly the
   reservation's topology revision.
3. Every Occupancy Zone required to establish the scope has complete, fresh,
   non-faulted, non-contradictory evidence that the scope is clear. Unknown,
   missing, stale, partial, faulted, or contradictory evidence is not clear.
4. Every Control Device required by the RoutePlan has complete, fresh,
   non-faulted, non-contradictory position evidence for its required logical
   position. A command request or an accepted command is not position evidence.
5. The requested expiration is in the future and no configured bound on the
   authority duration is exceeded.

A failed issuance returns one deterministic denial outcome and changes no
authority or reservation state. If several prerequisites fail, the outcome
selects the first applicable category in this order: `reservation`, `scope`,
`topology-revision`, `occupancy-evidence`, `device-position-evidence`, then
`expiration`. Within the two evidence categories, it selects the first affected
logical identifier in Unicode code-point order. The public explanation
identifies only the failed category and relevant logical IDs; it does not infer
a safe state from omitted or unavailable data.

### Continuous validity and revocation

Every live authority continuously depends on the reservation, topology
revision, occupancy evidence, and required Control Device position evidence
that supported it. The core revokes the authority immediately when any required
dependency is lost, becomes stale, faults, contradicts the required value, no
longer covers the authority scope completely, changes topology revision, or
when the reservation is released. Expiration also revokes the authority at its
expiration instant.

Revocation is idempotent and deterministic. The first event transitions the
authority to revoked with its documented reason; subsequent equivalent events
do not restore it or produce a different live state. A revoked or expired
authority cannot be renewed, reactivated, or transferred. Issuing a new
authority requires evaluating all issuance prerequisites again.

Revoking, expiring, or otherwise losing an authority never releases its
reservation automatically. Reservation release remains the separate,
owner-authorized whole-reservation operation defined by ADR 0011. This avoids
turning a loss of evidence into a claim release that could permit an
incompatible route while the physical situation remains uncertain.

### Boundary of this decision

Commands request a Control Device action; observations report detected device
position or occupancy. Neither is the other, and neither alone is a
`MovementAuthority`. A reservation is an exclusive runtime claim; an authority
is a time-bounded safety decision that depends on that claim and current
evidence.

Within this bounded domain contract, an authority is not a signal aspect and
does not command a signal. It also does not model a train, control train
motion, or grant real-world permission to move. Those meanings, along with
evidence ingestion, controller adapters, persistence, the simulator, CLI, and
dispatching, require later decisions.

### Representative scenarios

| Scenario | Result |
| --- | --- |
| A live exact-revision reservation has fresh complete clear occupancy and every required device reports its required position. | Issue one authority with the requested bounded scope and finite expiration. |
| The reservation is live, but one required occupancy zone is stale or reports occupied. | Deny issuance; create no authority and retain the reservation. |
| An authority is live and a required device's position evidence becomes unknown, faulted, or reports another position. | Revoke the authority immediately; retain the reservation. |
| An authority reaches its expiration instant. | Expire/revoke it immediately; retain the reservation. |
| A reservation is released while its authority is live. | Revoke the dependent authority immediately. |

## Alternatives considered

### Treat a reservation as movement authority

This would conflate exclusive claims with clear-track and device-position
evidence. It cannot fail closed when observations become stale or
contradictory.

### Release a reservation when authority is revoked

This might improve throughput, but a lost or faulted observation is precisely
when it is unsafe to remove an exclusive claim automatically.

### Permit indefinitely live authorities

An unbounded record could outlive the evidence that justified it. Explicit
expiration makes continued authority require a fresh decision.

## Consequences

- A future authority API must represent identity, bounded scope, expiration,
  and terminal revocation state separately from reservations.
- Evidence providers and adapters must expose freshness, completeness, faults,
  and revision provenance; missing evidence fails closed.
- The authority core remains independent of controller, UI, CLI, and simulator
  implementations.
- A later implementation must specify the concrete public result types and the
  total ordering used for denials and revocation reasons.
