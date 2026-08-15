# 0016: Command-acknowledged turnout-position assumptions

- Status: Accepted
- Date: 2026-08-15

## Context

The selected Märklin CS3+ and S88 integration supplies physical occupancy
feedback, but it cannot report the physical position of a conventional turnout.
The CS3+ can report its configured accessory mapping and acknowledge a turnout
command. Neither response proves that a turnout moved, remained mechanically
locked, or was not moved manually afterward.

The schema already permits an Installation Binding to declare
`assumed-after-delay` for a Control Device. ADR 0013, however, described every
movement-authority prerequisite as observed position evidence. This record
resolves that conflict and makes the operational assumption explicit.

## Decision

For a Control Device whose revision-matched Installation Binding declares
`position-evidence.kind: assumed-after-delay`, a successful response from the
firmware-pinned CS3+ integration may establish a bounded **assumed position
assertion** after the binding's configured `delay-ms` has elapsed. It may
satisfy the device-position prerequisite for Gleiswerk's logical
movement-authority model.

The assertion is not sensor evidence and must retain distinct provenance. Its
source identifies the command acknowledgement and the bound Control Device,
not a feedback channel. A report must label it `assumed-after-delay`, state
the configured delay, command acknowledgement time, assumed position, and the
exact topology and Installation Binding revision.

Before such an assertion is usable, commissioning must verify all of the
following against the same validated binding:

1. The topology revision matches the binding exactly.
2. The firmware-pinned integration reads and matches the CS3+ configuration
   to the declared command channel for every assumed-position Control Device.
3. The integration receives its characterized command-acceptance response for
   the declared channel and requested logical position.
4. The configured settling delay has elapsed without a command-station or
   transport fault.

An unavailable controller, unreadable or mismatched configuration, rejected
or timed-out command, transport loss, a new command, stale assertion, or
restart produces unavailable position evidence and fails closed. A later
successful command can establish only its own bounded assertion after its
delay; it cannot restore an older assertion. A sensor binding remains stronger
evidence and continues to require an independent feedback channel.

The assumption is deliberately limited to Gleiswerk's logical authority model.
It does not establish physical turnout position, clear a signal, dispatch a
train, or authorize real-world movement. Physical occupancy still requires
fresh, complete S88 evidence.

## Alternatives considered

### Require physical turnout-position sensors

This is the stronger physical guarantee, but it is unavailable on the selected
reference installation. It remains the preferred option where independent
turnout-position sensors are installed.

### Treat CS3+ configuration alone as position evidence

Configuration describes intended wiring and addressing, not current state.
It is necessary commissioning evidence but cannot establish a position without
a command acknowledgement and its explicit delay.

### Treat an accepted command as a physical observation

This would erase the difference between an instruction and a measurement. The
system instead labels the result as an assumption and invalidates it on any
relevant fault or replacement command.

## Consequences

- ADR 0013's device-position prerequisite includes this explicitly configured
  assumed assertion in addition to sensor-observed position evidence.
- The commissioning workflow must use a firmware-pinned integration to read
  and compare CS3+ configuration before it permits command-acknowledged
  assumptions; Märklin does not currently document a stable machine API for
  this operation.
- Command and commissioning adapters must expose acknowledgement, timing,
  configuration-match, and fault provenance without putting CS3+ protocol
  details into the safety core.
- Routes using assumed positions retain the residual risk that a turnout can
  fail mechanically or be moved outside the controller. Operators must treat
  this as an operational assumption, not physical proof.
