# Architecture

Gleiswerk has not yet introduced railway-control components. The initial
architecture establishes boundaries that later work should preserve.

```text
Command-line interface
        |
Application services
        |
Railway domain and safety rules
        |
Hardware adapters and simulator
```

The command-line interface is the current public entry point. Future work will
add application services, domain rules, adapters, and a simulator in small,
testable slices. Hardware-specific code should remain behind adapter boundaries
so the core can be exercised without a physical layout.

The initial, versioned vocabulary for layout files is documented in
[Layout configuration](layout-configuration.md). It is configuration data only;
it does not yet add railway-control components.

## Layout domain model

The controller-independent core represents the approved topology vocabulary as
immutable typed objects: `Block`, `EndpointReference`, `Turnout`, `Traversal`,
`Route`, and `Layout`. Stable identifier types distinguish blocks, endpoints,
turnouts, traversals, routes, and turnout positions in the public API. A
`Layout` verifies that traversal endpoints, traversal turnout requirements, and
route traversal references resolve to declared objects.

The model is deliberately not a configuration-file parser or diagnostic
reporter. The TOML reader and validator collect file-specific errors with paths
and codes, then construct valid domain objects. The model has no dependency on
the command-line interface, filesystem, simulator, or hardware adapters.

The schema-v3 topology vocabulary is being introduced as a separate, additive
domain model. Its immutable values distinguish directed path elements (Track
Section movements, Connection movements, and Junction Passages) from
direction-independent claimable resources (Track Sections, Junctions, and
Protection Zones). It also records Ports, Control Device requirements, and
Occupancy Zone coverage without loading YAML, compiling routes, reserving
resources, or communicating with an adapter.

The rationale for current cross-cutting decisions is recorded in the
[ADRs](adr/README.md).
