# Gleiswerk

Gleiswerk is a local-first control and automation project for model railways.
It is being developed in public, starting with a deliberately small and
reproducible distribution foundation.

Release `0.0.2` adds a validated, versioned layout-configuration contract for
named blocks, turnouts, and routes. It remains descriptive only and does not
yet control railway hardware or automate train movements.

## Principles

- Keep railway operation local and understandable.
- Treat safety, explicit operator control, and observable behavior as core
  design constraints.
- Support development and use on macOS, Linux, and Windows through a
  Conda-based toolchain.
- Make important technical decisions discoverable in [architecture decision
  records](adr/README.md).

Start with [Getting started](getting-started.md) to set up a development
environment, or read the [architecture](architecture.md) to understand the
planned boundaries.
