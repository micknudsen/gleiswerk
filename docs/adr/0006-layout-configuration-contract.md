# 0006: Initial layout-configuration contract

- Status: Superseded by [0009](0009-schema-v2-topology-contract.md)
- Date: 2026-07-26

## Context

Gleiswerk needs a stable, user-authored way to name the basic elements of a
layout before it can add a parser, simulator, controller adapter, or safety
logic. The first contract must be small enough to explain and validate
unambiguously, while leaving room for deliberate versioned evolution.

## Decision

Version 1 layout configurations are UTF-8 TOML files with a `.toml` extension.
They contain a required integer `schema-version = 1` and optional `blocks`,
`turnouts`, and `routes` tables. This permits an empty, versioned layout. IDs
use lowercase kebab-case and are the only machine references; `display-name` is
optional operator-facing metadata that defaults to the ID when absent.

Blocks are declarations with optional `display-name`. Turnouts declare two or
more distinct, kebab-case position IDs and may have an optional `display-name`.
Routes have a required ordered non-empty list of distinct declared block IDs,
optional display name, and an optional mapping from declared turnout IDs to a
position declared by that turnout. Repeated block visits are deferred with loop
and reversal semantics to a later topology model. Turnout positions describe
selectable states only; physical geometry and handedness remain out of scope.

Readers reject unsupported schema versions and unknown fields at every level.
For syntactically valid files, validation accumulates all contract violations
and reports them in deterministic order with stable codes and configuration
paths. Version 1 deliberately excludes physical topology, controller mapping,
occupancy, commands, movement, signalling, route conflict detection,
dispatching, hardware, and simulator behavior.

The normative schema reference is [Layout configuration](../layout-configuration.md).

## Alternatives considered

### YAML

YAML is approachable for hand-authored nested data, but it requires a parser
dependency and has more scalar and syntax ambiguity than needed for this first
contract.

### JSON

JSON has wide tooling support but is verbose for a hand-maintained layout and
does not support comments.

### Unversioned configuration

An unversioned format would make future changes ambiguous: readers could not
reliably tell whether a field was misspelled, unsupported, or newly intended.

### Include controller or operational data now

Adding addresses, occupancy, topology, interlocking, or commands now would
couple the first vocabulary to hardware and safety decisions that have not yet
been made.

## Consequences

- Python 3.11's standard-library `tomllib` can read the chosen format when a
  parser is introduced, without adding a runtime dependency.
- Layout authors get explicit failures for misspelled and future fields rather
  than silent acceptance.
- Later work can add a schema version with topology, adapter mappings, or
  operational concepts without reinterpreting version 1.
- Version 1 routes are declarations, not executable movement or hardware
  commands.
