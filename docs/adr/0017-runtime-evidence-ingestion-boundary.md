# 0017: Runtime evidence-ingestion boundary

- Status: Accepted
- Date: 2026-08-16

## Context

Gleiswerk already represents logical occupancy and Control Device evidence as
immutable, revision-matched values. The existing Märklin CS3+ S88 adapter can
translate a complete poll and individual feedback events without exposing its
wire format to the evidence validator. It deliberately does not own a socket,
poll schedule, reconnect policy, or long-running application lifecycle.

A runtime integration must add those responsibilities without allowing a
healthy transport, an old observation, or a partial resynchronization to be
mistaken for current clear evidence. It must also preserve the same safety
meaning for the simulator, protocol emulator, and a physical controller.

## Decision

Introduce a controller-independent **Runtime Evidence Source** port between a
supervised infrastructure adapter and the logical evidence validator. The port
publishes immutable logical evidence snapshots and health diagnostics; it does
not expose controller addresses, protocol frames, sockets, poll requests, or
transport ordering tokens to the core.

Every published observation retains its logical source ID, exact topology
revision, source status, timezone-aware observation time, and logical target.
The runtime service also retains an Evidence Session identity and stable fault
diagnostics. Session identity and diagnostics are operational provenance: they
are reported by the service, while the existing immutable evidence values
remain the validator's controller-independent input.

The lifecycle is explicit:

1. A source begins **unknown** on startup, reconnect, binding change, or
   topology-revision change. It has no usable last-known state.
2. A source becomes **available** only after a complete, revision-matched
   baseline snapshot has been accepted for every bound logical target.
3. While available, an adapter may publish an update only when its ordering is
   established within the current session. A duplicate logical target in one
   snapshot, a missing required target, malformed input, or input whose order
   cannot be established faults the affected source set. A redelivered
   transport event is acceptable only when the adapter can prove it is the
   same already-applied event; otherwise it is unordered input.
4. Transport loss, timeout, malformed input, an ambiguous duplicate, or an
   out-of-order update faults the affected source set immediately. Faulted
   sources publish no occupancy or position value.
5. Recovery requires a new complete, revision-matched baseline. Later events
   alone cannot restore availability or revive a previous session.

Freshness remains a pure, explicit assessment by `EvidenceFreshnessBasis` at
the authority-evaluation instant. A runtime service records receipt and
observation times but never silently extends freshness because a connection is
open or an event was received. Evidence from another topology revision is
rejected by the existing validator.

The simulator and protocol emulator implement the same port contract with a
deterministic clock and explicitly supplied baseline, updates, loss, and fault
events. Controller adapters translate their transport semantics at the edge;
the core sees only logical evidence and the stable diagnostic projection.

## Alternatives considered

### Let each controller adapter feed the evidence validator directly

This couples the core to connection, polling, and protocol ordering behavior.
It also makes simulator behavior diverge from hardware paths and obscures
which layer owns recovery.

### Retain the last known clear state across a fault or reconnect

This could mistake an old physical observation for current evidence. Clearing
or faulting the affected logical sources fails closed and requires an explicit
complete resynchronization.

### Treat every repeated transport event as harmless

Some transports can identify an idempotent redelivery, but others cannot.
Accepting an unidentifiable duplicate or out-of-order event would make the
latest state ambiguous. The adapter must prove idempotence or fault the source.

## Consequences

- The next implementation adds the service and adapter-facing port without
  changing the validator's controller-independent contract.
- Runtime diagnostics must name logical sources, session, freshness, and
  stable fault details without leaking CS3 protocol shapes into the core.
- Tests must cover startup, complete baseline, update, loss, malformed input,
  duplicate or unordered input, stale evidence, and recovery in both simulator
  and protocol-emulator paths.
- This decision does not authorize turnout or signal commands, train control,
  automatic live movement-authority issuance, persistence, or a UI.
