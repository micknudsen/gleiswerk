# 0015: Märklin feedback binding and evidence trust contract

- Status: Accepted
- Date: 2026-08-14

## Context

ADR 0014 selects a Märklin Central Station 3 plus with S88 feedback as the
first live-feedback target. Before implementing its adapter, Gleiswerk needs a
commissioning artifact that binds that controller's physical contacts to the
immutable logical topology, and a total rule for when received data is
trustworthy. A controller address or an S88 contact is not a topology fact: it
can change when hardware or cabling changes, while a topology revision defines
the logical safety model that consumes the evidence.

## Decision

Each deployment shall provide one separate, read-only **Märklin feedback
binding**. It is not part of a topology document and it is loaded only after
the referenced topology has validated. It contains the CS3 UDP endpoint and
the complete physical-to-logical mapping for exactly one topology revision.

```yaml
schema-version: 1
topology-revision: sha256:<validated-topology-fingerprint>
adapter:
  kind: marklin-cs3-s88-udp
  endpoint:
    host: 192.0.2.17
    port: 15731
  firmware-version: <commissioned-CS3-firmware-version>
  poll-interval-seconds: 5
occupancy-sources:
  platform-1-s88:
    occupancy-zone: platform-1-detector
    s88-contact: {bus: 1, module: 1, contact: 1}
    active-state: occupied
```

`host` is an installation-owned fixed IPv4 or DNS endpoint on the isolated
wired LAN. `port` is the commissioned CS3 CAN-over-Ethernet UDP port. The
adapter accepts only `marklin-cs3-s88-udp`, the firmware version recorded at
commissioning, and a positive poll interval. A firmware or endpoint change is
a binding change and requires recommissioning; it is never silently accepted.

Every `occupancy-sources` entry has a nonempty, unique source ID; references
one existing Occupancy Zone in the named topology revision; and has a unique
`(bus, module, contact)` tuple. Bus, module, and contact numbers are positive
integers in the commissioned S88 address space. `active-state` is currently
only `occupied`: an active contact maps to `OccupancyState.OCCUPIED`, and an
inactive contact maps to `OccupancyState.CLEAR`. The adapter emits the entry's
source ID as `EvidenceSourceId`, the named logical zone as `OccupancyZoneId`,
and the binding's revision as the evidence topology revision. A binding with a
missing, duplicate, unknown, or stale topology reference is rejected before
any UDP traffic is used. The earlier generic Installation Binding remains a
separate commissioning artifact; this adapter-specific artifact does not add
controller addresses to topology or alter its semantics.

### Evidence trust state

The adapter is fail-closed. Its source state is either `AVAILABLE`, `UNKNOWN`,
or `FAULTED`; only `AVAILABLE` can carry a known occupancy state. It stamps a
successfully decoded observation with its own aware UTC receipt time. The core
applies the installation's existing freshness bound to that timestamp.

| Condition | Adapter result |
| --- | --- |
| Startup, before a complete successful S88 poll | `UNKNOWN` for every configured source; no known occupancy evidence. |
| Complete valid poll covering every configured contact | `AVAILABLE` evidence for every contact, using the poll receipt time. |
| Valid event for a configured contact while the source is available | Replace only that source's evidence with the mapped value and event receipt time. |
| Valid event for an unmapped contact | Ignore the contact and record a diagnostic; it must not be guessed as a logical zone. |
| Malformed, unsupported, or internally inconsistent CAN datagram | `FAULTED` for every configured source and require recovery. |
| UDP socket or gateway failure, missed liveness/poll cycle, or incomplete poll | `FAULTED` for every configured source and require recovery. |
| Duplicate valid event, including one with the same mapped state | Treat as another observation for that one source and refresh only its receipt time. UDP provides no trustworthy global duplicate sequence. |
| Available evidence older than the core freshness limit | The core treats it as stale and denies or revokes authority; the adapter does not relabel an otherwise healthy source. |
| First complete successful poll after `UNKNOWN` or `FAULTED` | Recover every configured source to `AVAILABLE` from that poll; events alone cannot recover the adapter. |

An event may not establish initial state, prove gateway liveness, recover a
fault, refresh another contact, or change the binding revision. A complete poll
means one decoded response that accounts for every configured contact; a
partial response is an incomplete poll. Since UDP loss cannot be distinguished
from a quiet sensor, periodic complete polls are mandatory even when events
continue to arrive.

No output, accessory, locomotive, turnout, power, programming, or authority
message is permitted. The adapter's only outward values are immutable logical
occupancy evidence and explicit unavailable-source conditions. It provides no
turnout-position evidence.

## Alternatives considered

### Put endpoint and S88 addresses in topology

This would let a commissioning or network change alter the logical model's
identity and would invite adapters to redefine safety semantics. A separate,
revision-matched binding keeps those concerns distinct.

### Trust events without an initial or periodic poll

UDP events may be lost, and an unchanged input does not demonstrate that the
gateway remains live. This would turn silence into an implicit clear state.

### Recover from the next event

One event says nothing about every other mapped contact. A complete poll is
the minimum observation that can reestablish availability for the configured
set.

## Consequences

- The forthcoming adapter validates this binding before opening its socket and
  has a narrow output boundary of `OccupancyEvidence` plus availability state.
- Emulator tests must cover startup, complete and partial polls, events,
  unmapped and duplicate contacts, malformed frames, disconnect, staleness,
  and recovery only after a complete poll.
- Commissioning records the exact binding and CS3 firmware alongside the
  topology revision. A revised layout, mapping, endpoint, or firmware requires
  a new validated binding and commissioning run.
- This decision does not authorize an adapter connection, controller command,
  turnout feedback, or live movement permission.
