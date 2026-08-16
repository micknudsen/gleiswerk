# Hardware commissioning verification

`gleiswerk commissioning capture` collects one supervised, read-only capture;
`gleiswerk commissioning verify` then checks it from
the live installation. It does not open a controller connection, command a
turnout, clear a signal, or authorize a train to move. A firmware-pinned CS3+
capture adapter collects the controller configuration and S88 state; the CLI
then validates that capture against immutable, revision-matched configuration.

The `--live-hardware` flag is required. It makes a commissioning run explicit
and prevents a capture from being mistaken for an ordinary development or CI
test. Emulator tests remain authoritative for CI.

```console
gleiswerk commissioning capture layout.yaml installation-binding.yaml \
  http://192.168.0.100 "2.6.1 (Build 3)" --live-hardware > cs3-capture.yaml

gleiswerk commissioning verify layout.yaml installation-binding.yaml \
  cs3-capture.yaml occupancy-expectations.yaml --live-hardware
```

The command exits zero only when every check passes. It emits a YAML report
with the topology revision, captured firmware version and time, plus stable
failure details otherwise. A capture older than the configured 30-second limit
is rejected; use `--maximum-age-seconds` only when the supervised procedure
requires a different limit.

## Capture contract

The capture adapter supplies a complete YAML document. It must be acquired
from the live installation in the same commissioning procedure and must retain
the firmware version whose response shape it understands.

```yaml
topology-revision: sha256:<validated-topology-fingerprint>
captured-at: 2026-08-15T12:00:00Z
firmware-version: <commissioned-CS3-firmware-version>
model: marklin-cs3-plus-60216
endpoint: http://192.168.0.100
acquisition-method: marklin-cs3-webapp-json
acquisition-version: "1"
configuration-snapshot-hash: sha256:<canonical-source-snapshot-hash>
command-channels:
  west-throat-turnout: dcc-accessory-12
feedback-channels:
  west-throat-turnout: turnout-end-sensor-12
  platform-detector: s88-1-1-1
occupancy-states:
  s88-1-1-1: clear
```

`command-channels` compares the CS3+ configured command mapping for every
Control Device. `feedback-channels` compares every occupancy binding and any
independent sensor-position binding. `occupancy-states` contains the S88 state
for each tested occupancy channel. Missing, ambiguous, malformed, stale, or
revision-mismatched data fails closed.

The first adapter is pinned to CS3+ model 60216 and the characterized
firmware. It makes only three HTTP `GET` requests—`/app/api/devs`,
`/app/api/mags`, and `/app/api/mags/state`—and rejects redirects, unknown
firmware, non-DCC command mappings, incomplete S88 state, duplicate addresses,
or changed response shapes. It has no command implementation. Märklin does not
document this as a stable machine API, so a firmware update must be
characterized and released before it can be used; see the [research
note](research/marklin-cs3-commissioning-interface.md).

## Supervised S88 expectation file

During the smoke test, put a known test load on each required track section
and compare the resulting logical states with an explicit expectation file:

```yaml
occupancy-zones:
  platform-detector: clear
```

Run the test again with the section occupied where practical. This tests the
physical S88 path without treating a permanently clear or occupied input as
proof that the circuit works.

## Turnout assumptions

For `sensor` bindings, the capture verifies an independent feedback-channel
mapping. For `assumed-after-delay` bindings, it verifies the CS3+ command
channel only. A later command adapter may create a bounded assumed-position
assertion after its characterized acceptance response and configured delay, as
defined by [ADR 0016](adr/0016-command-acknowledged-turnout-assumptions.md).
It is not physical turnout-position feedback.
