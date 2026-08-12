# Logical evidence contract

Status: implementation contract. This document defines the immutable values in
`gleiswerk.evidence` that represent controller-independent logical occupancy
and Control Device position observations. They neither ingest controller
feedback nor issue movement authority.

## Observations

`OccupancyEvidence` identifies exactly one `OccupancyZone`; `DevicePositionEvidence`
identifies exactly one `ControlDevice`. Each observation carries the exact
topology revision, a stable logical source ID, source status, and a
timezone-aware observation time. It intentionally contains no controller
address, command channel, or accepted command result.

A source is `available`, `unknown`, or `faulted`. Available occupancy evidence
must carry either `clear` or `occupied`; available device evidence must carry a
declared logical position. Unknown and faulted evidence carries neither. Thus
an absent or unhealthy source cannot be represented as a known-safe state.

## Freshness and outcomes

`EvidenceFreshnessBasis` supplies the evaluation instant and maximum accepted
age explicitly. Its `qualify()` method returns `fresh` at the exact age limit
and `stale` after it. It never reads a clock, so callers and tests choose the
same deterministic basis.

The validator introduced by the next layer returns immutable result values. An
occupancy result is `clear`, `occupied`, `unknown`, `stale`, or `faulted`. A
device-position result is `aligned`, `unaligned`, `unknown`, `stale`, or
`faulted`, and names the required logical position. Alignment is therefore a
comparison against a RoutePlan requirement, not a claim that a command moved a
device.

## Safety boundary

An observation is evidence, not a command outcome. Missing, revision-mismatched,
unknown, stale, faulted, occupied, or unaligned evidence is not clear evidence
and must fail closed for a later movement-authority decision.
