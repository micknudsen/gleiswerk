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

The rationale for current cross-cutting decisions is recorded in the
[ADRs](adr/README.md).
