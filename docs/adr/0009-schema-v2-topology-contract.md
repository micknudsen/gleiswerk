# 0009: Schema-v2 topology contract

- Status: Superseded by ADR 0010
- Date: 2026-07-29
- Updated: 2026-08-01

## Context

Earlier pre-release configurations recorded named blocks, turnout positions,
and route resource requirements, but deliberately did not describe how those
resources connect. An ordered block list cannot establish that one step can
physically follow the previous one. Gleiswerk needs a small,
controller-independent topology vocabulary before it can validate route
continuity.

The topology model must be logical rather than geometric. It must describe
which directed passages are allowed, including passages selected by turnout
positions, without introducing controller addresses, commands, occupancy,
reservations, signals, or movement authority.

## Decision

Schema version 2 defines the following topology vocabulary. Gleiswerk is
pre-1.0 and supports this grammar exclusively: a reader requires
`schema-version = 2` and never blends fields from an earlier grammar.

### Block endpoints

Every declared block has exactly two local endpoint IDs in a required
`endpoints` array. Endpoint IDs use the existing lowercase kebab-case rule and
are unique within their block. An endpoint reference is written as
`block-id.endpoint-id`; it identifies a logical boundary, not a coordinate or
physical drawing position.

For example:

```toml
[blocks.platform-1]
endpoints = ["west", "east"]
```

### Directed traversals

The required top-level `traversals` table contains logical directed passages.
Each traversal has a unique traversal ID plus required `from` and `to`
endpoint references. Both references must resolve to declared block endpoints
and must differ. A reverse passage is distinct and must be declared explicitly;
the reader must not infer it from another traversal.

```toml
[traversals.west-entry-to-platform-1]
from = "west-entry.east"
to = "platform-1.west"
```

A traversal describes permitted logical connectivity only. It does not state
geometry, length, direction of train travel, occupancy, reservation, or a
controller command.

### Turnout requirements on traversals

A traversal may contain a `turnouts` table that maps a declared turnout ID to
one of that turnout's declared positions. The mapping is a precondition: the
traversal is available only while every listed turnout has its listed position.
No mapping commands or changes a turnout.

```toml
[traversals.west-entry-to-platform-1]
from = "west-entry.east"
to = "platform-1.west"

[traversals.west-entry-to-platform-1.turnouts]
west-throat = "normal"
```

Each turnout can appear at most once in a traversal. A version-2 route is a
non-empty ordered list of traversal IDs. A future route-continuity validator
will require the `to` endpoint of each traversal to equal the `from` endpoint
of its successor. That future validator will also derive each route's effective
turnout requirements from the union of its traversals and reject contradictory
positions for the same turnout.

Version-2 configuration validation is deterministic. For a syntactically valid
file, it collects and orders structural violations by the established
configuration order, then by traversal and route ID, and finally by documented
field order. Diagnostics use stable codes and configuration paths. Unresolved
endpoints and unsupported turnout positions are validation errors, not inferred
behavior. Route continuity and contradictory route-level turnout requirements
remain future safety validation.

### Versioning policy

Schema version 1 is not supported. Readers reject `schema-version = 1` as an
unsupported version and do not provide migration or compatibility behavior.
Version-2 readers require the topology declarations described here; they do
not guess connectivity from earlier ordered block lists. A layout author must
provide a complete `schema-version = 2` configuration.

The detailed version-2 TOML reference, parser, diagnostics, and migration
guidance will be introduced only after this ADR is accepted.

## Alternatives considered

### Infer topology from ordered block lists

This keeps configuration short, but block ordering is route-specific evidence,
not a reusable layout graph. It cannot distinguish a valid connection from an
accidental adjacent pair, and it makes independent route-continuity validation
impossible.

### Model physical geometry

Coordinates, track shapes, handedness, and drawing-oriented connectors could
produce a richer editor view, but they increase the contract substantially and
are unnecessary for logical continuity. They would also risk coupling the core
model to a particular UI.

### Assume every traversal is bidirectional

This reduces declarations, but it hides one-way or operationally constrained
passages and makes validation depend on an implicit rule. Explicit reverse
traversals preserve a small, inspectable graph.

### Put turnout requirements only on routes

Route-level requirements cannot say which connection they enable. Attaching
them to traversals expresses the local topology constraint while allowing a
route's effective requirements to be checked deterministically.

### Retain schema version 1 compatibility

Keeping an earlier route representation alongside topology routes would make
the domain model and loader permanently version-aware before the first stable
release. It would also preserve a route form that cannot validate continuity
without inferring topology. Rejecting it now keeps the pre-1.0 model small and
unambiguous.

## Consequences

- The core has the controller-independent information needed for future route
  continuity validation without a simulator, UI, or physical layout.
- Layout authors must declare both directions when both are allowed, and must
  make turnout-dependent connections explicit.
- A valid version-2 topology is still not a movement authorization: it says
  nothing about occupancy, reservations, signals, commands, train direction,
  or operational safety.
- Version-2 implementation will need new immutable topology types, parser and
  validator rules, stable diagnostics, examples, and tests; none are created by
  this ADR.
- Existing schema-version 1 configurations are rejected. Their authors must
  provide complete schema-version 2 topology declarations.
- The domain model contains only traversal-defined routes, avoiding a legacy
  block-list route representation and its compatibility burden.
