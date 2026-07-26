# 0001: Runtime and platform support

- Status: Accepted
- Date: 2026-07-26

## Context

Gleiswerk will run beside a physical model railway, initially on macOS. Its
controller-independent core, command-line interface, and simulator do not need
to be tied to that operating system.

Supporting several operating systems early reduces accidental platform
coupling. At the same time, hardware behavior should only be claimed where it
has actually been validated.

## Decision

Gleiswerk requires Python 3.11 or newer.

The core, command-line interface, and simulator target macOS, Linux, and
Windows. The Conda package will be platform-independent whenever its
dependencies allow a `noarch: python` package.

Physical Märklin CS3+ integration will be validated on macOS first. Other
platforms remain design and continuous-integration targets until their physical
adapter behavior has also been tested with hardware.

## Consequences

- Core code must not rely on operating-system-specific behavior.
- Continuous integration must exercise supported Python versions across macOS,
  Linux, and Windows.
- Hardware support documentation must distinguish CI-tested portability from
  validation against a physical layout.
