# 0014: First feedback controller and transport

- Status: Accepted
- Date: 2026-08-14

## Context

Gleiswerk's automation core consumes immutable, controller-independent logical
evidence. Before an adapter can bring live observations into that core, the
project needs one deliberately small, documented hardware target. Selecting a
specific initial target lets the adapter define what a received value does and,
more importantly, what it cannot prove.

The target must supply live occupancy feedback without coupling the core to a
UI, command protocol, or train-control implementation. A lost connection,
unknown initial state, or unmapped physical input must not be interpreted as a
clear track section.

## Decision

The first supported live-feedback target is a **Märklin Central Station 3 plus
(60216)** with **Märklin S88 AC feedback modules (60881)** on its built-in S88
connection. The adapter receives feedback through the CS3's configured
**CAN-over-Ethernet gateway over UDP** on an isolated wired LAN.

This is a feedback-only integration. The adapter may send only the CAN messages
needed to subscribe to S88 events and request an S88 state poll. It must not
issue locomotive, accessory, turnout, power, programming, or any other command.
It must not grant, revoke, or otherwise control train movement. Movement
authority remains a separate core decision defined by ADR 0013.

### Available feedback semantics

An S88 AC module provides sixteen contact inputs. For each explicitly
configured contact, the CS3's S88-event and S88-poll messages expose an active
or inactive state. The adapter maps a received raw state as follows:

| Raw S88 state | Logical result |
| --- | --- |
| Active | `OccupancyEvidence(state=OCCUPIED)` |
| Inactive | `OccupancyEvidence(state=CLEAR)` |
| No successful initial poll, lost UDP gateway, unreadable packet, unmapped contact, or failed health check | No available observation; report `UNKNOWN` or `FAULTED` source status as applicable |

The CS3 does not supply a usable observation timestamp in this interface. The
adapter stamps each successfully decoded event or poll response at receipt time
with an aware UTC clock. The core then applies its configured freshness bound.
UDP is not a reliable transport, so an unchanged contact is not evidence that
the gateway is live. The adapter must run an explicit full S88 poll/liveness
cycle and mark the source unavailable when that cycle fails. A later successful
full poll is required before the source may return to `AVAILABLE`.

This first target supplies only logical occupancy evidence. An S88 contact does
not prove a specific vehicle identity, physical track clear of all rolling
stock, turnout position, accessory state, direction, speed, or permission to
move. `DevicePositionEvidence` is outside this adapter's scope; a future
adapter requires independently detected position feedback and a separate
decision.

### Adapter boundary

The Märklin-specific adapter is an outer infrastructure component. Its inputs
are UDP datagrams, connection/liveness results, and an installation-owned
mapping from `(S88 bus, module number, contact number)` to
`(OccupancyZoneId, EvidenceSourceId, topology revision)`. Its outputs are only
logical `OccupancyEvidence` records or explicit unavailable-source conditions.
The core, CLI, simulator, and UI neither parse Märklin CAN frames nor infer S88
addresses.

The mapping is configuration, not a discovery result. Each mapped contact must
be unique, belong to one validated topology revision, and have a documented
polarity. The adapter must reject duplicate, missing, or stale-revision
mappings rather than guess an Occupancy Zone.

Märklin's CAN-over-Ethernet protocol originates with the CS2 and is not a
versioned, current CS3 public API. Consequently, the first adapter must pin its
supported CS3 firmware version and treat its 13-byte UDP wire contract as a
compatibility boundary. A commissioning capture must prove the exact S88 poll,
event-subscription, and event frame behavior of that firmware; a firmware
change requires rerunning the adapter's protocol conformance suite before live
evidence is enabled.

### Commissioning assumptions

Before any live evidence is used to support a safety decision, the installation
operator must:

1. Wire each monitored section through the intended 60881 channel and record
   the S88 bus, module number, and contact number.
2. Configure the immutable contact-to-zone mapping, source IDs, topology
   revision, and expected active polarity; review it with the physical wiring.
3. Demonstrate, for every mapped contact, an occupied transition and a clear
   transition at the CS3 and at the adapter. A permanently active or inactive
   contact is not commissioned by observation alone.
4. Enable the CS3 CAN-over-Ethernet gateway only on an isolated wired LAN with
   a fixed controller address. Start the adapter with an explicit full S88
   poll, then verify its periodic liveness/poll cycle and its fail-closed
   behavior when the CS3, network path, or S88 bus is disconnected.
5. Record the CS3 firmware version and validate the captured poll and event
   frames against the adapter conformance suite before enabling evidence.
6. Configure the core freshness limit for the installation and verify that a
   stale, unknown, or faulted source denies or revokes authority as ADR 0013
   requires.

Märklin documents the CS3's S88 contact configuration and the S88 connection
paths in its [CS3 manual](https://www.marklin-users.net/upload/community/Docs/Zme/7143_CS3_Manual_EN_final-lo.pdf).
The 60881 is the Märklin 16-contact S88 feedback module used by this decision.
The CAN-over-Ethernet framing and S88 poll/event messages are verified against
the legacy [Märklin CAN protocol version 2.0](https://digitalplayground.be/locomotion/files/cs2CAN-Protokoll-2_0.pdf)
as part of commissioning, rather than assumed to be a stable public CS3 API.

## Alternatives considered

### Märklin Central Station 3 (60226) with Link S88 (60883)

The standard CS3 requires the separate Link S88 to attach feedback modules.
That is a valid expansion path, but it adds a CAN-attached feedback interface
to the first integration. The CS3 plus's built-in S88 connection reaches the
same addressed contact semantics with fewer devices, wiring paths, and failure
modes, so it is the narrower initial safety target.

### Direct S88 integration

Reading S88 modules directly could avoid the CS3 gateway, but would add
electrical timing, bus polling, and device-health concerns to the first adapter.
Using the CS3 preserves one controller boundary and lets Gleiswerk focus on
logical evidence rather than hardware signaling.

### Turnout commands as evidence

An accepted or sent turnout command is not proof of physical alignment. Adding
commands would violate the evidence-only boundary and cannot satisfy the
position-evidence prerequisite of ADR 0013.

## Consequences

- A future Märklin adapter may implement only S88 occupancy ingestion described
  here; it must keep CAN and UDP handling outside the core.
- Tests for that adapter must cover initial unknown state, full polls, events,
  duplicate or unmapped contacts, malformed frames, liveness loss, and recovery
  after a new full poll.
- A future Link S88, controller firmware, different detector family, RailCom
  identity, or turnout-position feedback needs its own adapter contract and,
  where it changes this selection or safety meaning, a new ADR.
- No controller commands or movement-control features are authorized by this
  decision.
