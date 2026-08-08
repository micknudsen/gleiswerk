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

The versioned vocabulary for layout files is documented in [Layout
configuration](layout-configuration.md). It is configuration data only; it
does not yet add railway-control components.

## Layout domain model

The controller-independent core represents schema-v3 topology as immutable
typed objects. It distinguishes directed path elements (Track Section and
Connection movements, plus Junction Passages) from direction-independent
claimable resources (Track Sections, Junctions, and Protection Zones). It also
records Ports, Control Device requirements, and Occupancy Zone coverage.

The YAML reader and validator collect file-specific errors with paths and
codes, then construct valid domain objects. The RoutePlan compiler derives a
complete path, resource claims, device requirements, provenance, and a
topology-revision fingerprint. These layers have no dependency on the
command-line interface, filesystem, simulator, or hardware adapters.

The rationale for current cross-cutting decisions is recorded in the
[ADRs](adr/README.md).
