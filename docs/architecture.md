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

The controller-independent core now represents the approved layout vocabulary
as immutable typed objects: `Block`, `Turnout`, `Route`, and `Layout`. Stable
identifier types distinguish block, turnout, route, and turnout-position
references in the public API. A `Layout` verifies that route references resolve
to its declared blocks and turnouts, and that each required turnout position is
supported.

The model is deliberately not a configuration-file parser or diagnostic
reporter. A future TOML reader and validator will collect file-specific errors
with paths and codes, then construct these valid domain objects. The model has
no dependency on the command-line interface, filesystem, simulator, or
hardware adapters.

The rationale for current cross-cutting decisions is recorded in the
[ADRs](adr/README.md).
