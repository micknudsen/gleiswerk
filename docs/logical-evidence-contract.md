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

Device evidence normally represents an independent position observation. A
revision-matched Installation Binding may instead declare
`assumed-after-delay`. Under ADR 0016, a command adapter may then issue a
fresh, fault-sensitive, bounded position assertion after an acknowledged
command and the declared delay. Its provenance must identify it as an
assumption; it is not sensor evidence or proof that the turnout moved.

## Freshness and outcomes

`EvidenceFreshnessBasis` supplies the evaluation instant and maximum accepted
age explicitly. Its `qualify()` method returns `fresh` at the exact age limit
and `stale` after it. It never reads a clock, so callers and tests choose the
same deterministic basis.

The topology validator returns immutable result values. An
occupancy result is `clear`, `occupied`, `unknown`, `stale`, or `faulted`. A
device-position result is `aligned`, `unaligned`, `unknown`, `stale`, or
`faulted`, and names the required logical position. Alignment is therefore a
comparison against a RoutePlan requirement, not a claim that a command moved a
device.

## Safety boundary

An observation is evidence, not a command outcome. The only permitted
position-assumption exception is ADR 0016's explicit, revision-matched
`assumed-after-delay` policy. Missing, revision-mismatched, unknown, stale,
faulted, occupied, or unaligned evidence or assumptions are not clear evidence
and must fail closed for a later movement-authority decision.

## Topology validation

`validate_evidence()` in `gleiswerk.evidence_validation` assesses observations
against one immutable `Topology`, compiled `RoutePlan`, and explicit freshness
basis. It accepts only evidence whose topology revision exactly matches the
active topology. A plan from a different revision is rejected too.

For every claimed Track Section and Junction, the validator requires exactly
one declared Occupancy Zone with complete coverage. It rejects absent,
ambiguous, duplicate, stale, unknown, faulted, and occupied evidence. Partial
coverage never counts as complete. Each Control Device requirement in the plan
also needs one fresh, available logical observation of the required position.

The returned `EvidenceValidationResult` carries qualified observations and
stable `EvidenceRejection` values with logical targets and source IDs. Its
`is_usable` property is true only when no prerequisite was rejected. Neither
the validator nor its result knows controller addresses or commands devices.
