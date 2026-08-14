# Gleiswerk

Gleiswerk is a local-first control and automation project for model railways.
It is being developed in public, starting with a deliberately small and
reproducible distribution foundation.

Schema version 3 provides validated, resource-complete logical topology,
compiled route plans, in-memory reservations, and evidence-gated,
time-bounded movement-authority decisions. It describes track sections, direct
connections, junction passages, protection claims, and device requirements,
but remains a safety aid only: it does not control railway hardware or
authorize a real train to move.

## Principles

- Keep railway operation local and understandable.
- Treat safety, explicit operator control, and observable behavior as core
  design constraints.
- Support development and use on macOS, Linux, and Windows through a
  Conda-based toolchain.
- Make important technical decisions discoverable in [architecture decision
  records](adr/README.md).

Start with [Getting started](getting-started.md) to set up a development
environment, read [Layout configuration](layout-configuration.md) to author a
schema-v3 layout, follow the [reservation and movement-authority CLI workflow]
(reservation-cli-workflow.md), or see [architecture](architecture.md) for the
planned boundaries.
