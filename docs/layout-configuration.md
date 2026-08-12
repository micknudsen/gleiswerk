# Layout configuration

Gleiswerk layout files use **schema version 3**. A layout is a UTF-8 YAML
document with a lowercase `.yaml` suffix. Schema version 3 is the only layout
format the reader accepts. Earlier schemas are historical records, not input
formats and not migration sources.

A layout describes logical railway topology: the track sections, junctions,
their ports, the permitted directed movements, and the resources a route needs.
It does not contain controller addresses, screen geometry, reservations,
signals, commands, or permission for a train to move.

The complete field-by-field contract is in the [schema-v3 topology
contract](schema-v3-topology-contract.md). This page is the authoring guide.

## Start with a validated reference layout

The checked-in [station reference layout](https://github.com/micknudsen/gleiswerk/blob/master/tests/fixtures/schema_v3/valid-station.yaml)
shows a complete two-throat station. The smaller [direct-connection
layout](https://github.com/micknudsen/gleiswerk/blob/master/tests/fixtures/schema_v3/valid-direct.yaml)
is useful when learning the vocabulary. Both are loaded and compiled by the
test suite.

Validate a copy before commissioning it:

```console
gleiswerk layout validate layout.yaml
```

The command prints `Layout is valid: ...` and exits zero for a valid document.
It prints ordered diagnostics to standard error and exits one otherwise. For
example, the [dangling-port example](https://github.com/micknudsen/gleiswerk/blob/master/tests/fixtures/schema_v3/invalid-dangling-port.yaml)
is deliberately invalid and is asserted to report `E204` by the test suite.

## Inspect route compatibility

For a valid layout with at least two Route Definitions, inspect every unordered
pair of compiled RoutePlans without changing the layout or any railway state:

```console
gleiswerk layout compatibility layout.yaml
```

The command writes one deterministic YAML document to standard output and exits
zero for both compatible and conflicting layouts. Its shape is the
[RoutePlan compatibility contract](routeplan-compatibility-contract.md):

```yaml
topology-revision: sha256:<hex>
pairs:
  - route-pair: [route-a, route-b]
    compatible: false
    conflicts:
      - kind: overlapping-exclusive-claim
        resource: track-section:shared-section
        provenance:
          route-a: [track-section:shared-section]
          route-b: [track-section:shared-section]
```

Pairs, conflicts, and provenance entries follow the contract's canonical
ordering. Invalid layout configuration, route-compilation failure, or fewer
than two Route Definitions produces a diagnostic on standard error and exits
one. The command is read-only: it does not reserve resources, command devices,
or authorize movement.

## Topology vocabulary

Every collection is keyed by a stable lowercase kebab-case ID:

```text
^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$
```

```yaml
schema-version: 3
track-sections:
  approach:
    ports: [west, east]
    terminal-ports: [west]
    movements:
      - from: west
        to: east
  platform:
    ports: [west, east]
    terminal-ports: [east]
    movements:
      - from: west
        to: east
connections:
  approach-to-platform:
    ports: [track-section:approach:east, track-section:platform:west]
    movements:
      - from: track-section:approach:east
        to: track-section:platform:west
route-definitions:
  arrival:
    entry: track-section:approach:west
    exit: track-section:platform:east
```

`Track Sections` are claimable physical spans. They own named `Ports`, declare
which directed movements are permitted inside the span, and may mark boundary
ports as terminal. A nonterminal port must occur in exactly one `Connection`.

A `Connection` is a fixed adjacency between exactly two ports. It proves that
two owners meet, but it is not itself a claimable physical resource. Its
directed movements must be declared; reverse travel is never inferred.

A `Junction` owns three or more ports. Each permitted movement through it is a
`Junction Passage` with a source port, a destination port, and any required
`Control Device` positions. The compiler claims the whole junction for a
selected passage, not merely one branch through it.

`Occupancy Zones` declare evidence coverage over track sections. `Protection
Zones` and `Protection Rules` add explicit fouling, flank, crossing, or overlap
claims and device requirements. They are topology declarations, not adapter
configuration. Put controller channel names in a separate, revision-matched
Installation Binding.

## Route definitions and compiled plans

A `Route Definition` specifies an `entry`, an `exit`, and optionally an
ordered `via` list of Track Section, Connection, or Junction Passage
constraints. It does not list a path, claims, or turnout requirements:

```yaml
route-definitions:
  west-to-platform-1:
    entry: track-section:west-entry:west
    exit: track-section:platform-1:east
    via: [junction-passage:west-to-platform-1]
```

The RoutePlan compiler finds exactly one non-repeating path using the declared
movements. It then produces an immutable plan containing the ordered path,
all Track Section, Junction, and Protection Zone claims, Control Device
requirements, provenance, and the topology revision fingerprint. If there is
no path, more than one eligible path, or a path revisits a physical resource,
compilation fails instead of choosing a route.

The [route compiler tests](https://github.com/micknudsen/gleiswerk/blob/master/tests/test_route_compiler.py)
exercise the direct, station, protection, ambiguous, and repeated-resource
examples.

## Safety boundary

Validation and compilation are safety checks on declared data. They do **not**
reserve resources, command devices, clear signals, establish movement
authority, or authorize a train to move. Runtime authorization must additionally
use current, complete occupancy and device-position evidence and the exact
topology revision for its Installation Binding.

Unknown, stale, faulted, or partial-only evidence is not clear evidence. It
must keep affected claims unavailable.

## Authoring checklist

1. Give every physical track span and junction its own logical resource.
2. Declare every port boundary, direct connection, and permitted direction.
3. Add junction passages with every required device position.
4. Define routes by entry, exit, and only the constraints needed to make the
   intended path unique.
5. Declare occupancy coverage and non-path protection explicitly.
6. Validate the YAML, compile the routes in tests, and review the resulting
   claims and requirements against the physical layout.
