# Schema-v3 topology contract

Status: implementation contract for Issue 68. Schema version 2 remains the
only runtime-supported format until the schema-v3 implementation lands.

This document fixes the schema-version-3 configuration and deterministic
validation contract required by [ADR 0010](adr/0010-resource-complete-topology.md).
It is normative for the parser, topology model, route compiler, and reference
fixtures that follow. It does not authorize movement, define hardware
addresses, or change the current reader.

## Contract conventions

Schema-v3 files are UTF-8 YAML files whose names end in lowercase `.yaml`.
Unknown fields are errors at every level. Examples may reorder declarations,
but declaration order never changes their meaning or diagnostic order.

### YAML document profile

Schema version 3 accepts one YAML 1.2 document whose root is a mapping. Mapping
keys must be strings. Documents with duplicate mapping keys, custom tags,
anchors, aliases, merge keys, complex keys, or additional documents are
errors. The only accepted scalar types are documented strings and the integer
`schema-version`; booleans, nulls, floating-point values, timestamps, and
implicitly coerced values are errors wherever a string is required.

The parser must use YAML 1.2 scalar resolution. Quoting a scalar is always
allowed and is required whenever a YAML implementation would otherwise resolve
it to a non-string. The reference fixtures use plain scalars only where their
YAML 1.2 type is unambiguously a string.

All collection IDs, local port IDs, device position IDs, and rule IDs match:

```text
^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$
```

IDs are unique within their collection. Port IDs are unique within their
owner. A reference never relies on an ID from another collection.

| Reference | Form |
| --- | --- |
| Port | `track-section:<section-id>:<port-id>` or `junction:<junction-id>:<port-id>` |
| Physical resource | `track-section:<id>` or `junction:<id>` |
| Protection resource | `protection-zone:<id>` |
| Claimable resource | Any physical- or protection-resource reference |
| Path constraint | `track-section:<id>`, `connection:<id>`, or `junction-passage:<id>` |
| Protection trigger | A directed path element, route boundary, or route definition as defined below |

References are case-sensitive. They contain exactly the documented number of
colon-separated components; components use the same ID grammar. References
must resolve to the named collection and local port where applicable.

The topology revision fingerprint is not author supplied. After decoding the
file as UTF-8, the loader computes `sha256:<lowercase-hex>` over the exact
source bytes. Route plans and installation bindings identify that fingerprint.
Any byte change, including a comment-only change, conservatively creates a new
revision.

## Top-level grammar

```yaml
schema-version: 3
track-sections: {}
junctions: {}
control-devices: {}
connections: {}
junction-passages: {}
occupancy-zones: {}
protection-zones: {}
protection-rules: {}
route-definitions: {}
```

`schema-version` is required and must be the integer `3`. Each named top-level
collection is optional and, when present, must be a mapping. A layout with no
Track Sections and no Junctions is structurally valid but cannot compile a
route.

## Track Sections and Ports

A Track Section is a claimable linear rail span with exactly two local Port
IDs. Their array order has no movement meaning. `movements` is a nonempty
array of explicit `{from, to}` mappings using those local Port IDs. Each pair
must use distinct Ports, and duplicate pairs are invalid. A movement is
permission to traverse the section, not a second resource identity. Its
reverse is permitted only when separately declared.

`terminal-ports` is optional and defaults to an empty array. It is a set of
local Port IDs. A terminal Port must have no Connection. Every nonterminal
Port must have exactly one Connection.

```yaml
track-sections:
  west-entry:
    ports: [west, east]
    movements:
      - from: west
        to: east
      - from: east
        to: west
    terminal-ports: [west]
```

The only fields are `ports`, `movements`, and `terminal-ports`. Port ownership
is established by the `ports` array; Ports are not also declared in a global
collection.

## Junctions and Junction Passages

A Junction is one atomic, exclusively claimable physical resource. It has at
least two distinct local Ports. `terminal-ports` follows the same rules as for
a Track Section.

```yaml
junctions:
  west-throat:
    ports: [west, platform-1, platform-2]
```

A Junction Passage is an allowed directed movement between two distinct Ports
of one Junction. Reverse movement requires a separate passage. Every passage
claims its owning Junction; no declaration can narrow that claim.

```yaml
junction-passages:
  west-to-platform-1:
    junction: west-throat
    from: west
    to: platform-1
    requirements:
      west-throat-switch: normal
```

The only passage fields are `junction`, `from`, `to`, and `requirements`.
`requirements` is optional and defaults to an empty mapping. Its keys reference
Control Device IDs and its values reference positions declared by those
devices.

Passage selection must be deterministic. For passages with the same Junction
and `from` Port, every pair leading to different `to` Ports must be mutually
exclusive: at least one Control Device must occur in both requirement mappings
with different required positions. Compatible or disjoint requirement sets
would allow one effective device state to select two physical exits and are
invalid. Multiple passages to the same exit are also invalid; combine their
requirements into one passage or model a different physical resource.

## Control Devices

A Control Device is a logical state-bearing device. It declares at least two
distinct positions. Hardware addresses, commands, feedback channels, startup
state, and assumed position are not part of this file.

```yaml
control-devices:
  west-throat-switch:
    positions: [normal, reverse]
```

The only field is `positions`. A requirement constrains a position; it never
commands the device and never proves the position was observed.

## Connections

A Connection is a fixed adjacency between exactly two Ports. `ports` is an
unordered pair. `movements` is a nonempty array of explicit `{from, to}`
mappings using the full Port references in `ports`. Each pair must use
distinct Ports, and reverse movement is declared separately.

```yaml
connections:
  entry-to-throat:
    ports:
      - track-section:west-entry:east
      - junction:west-throat:west
    movements:
      - from: track-section:west-entry:east
        to: junction:west-throat:west
      - from: junction:west-throat:west
        to: track-section:west-entry:east
```

The two Port references must differ. A Connection cannot join two Ports of the
same owner, branch, or participate in a claim. Same-owner movement belongs to
a declared Track Section movement or a declared Junction Passage.

Each Port occurs in at most one Connection. A connected Port cannot be
terminal; an unconnected nonterminal Port is invalid. A direct Connection
between two Track Sections proves continuity without creating a Junction.

## Occupancy Zones

An Occupancy Zone represents one logical observation source. Its nonempty
`coverage` array names every claimable resource overlapped by that source.
Each coverage mapping has exactly `resource` and `extent`; `extent` is
`complete` or `partial`.

```yaml
occupancy-zones:
  platform-detector:
    coverage:
      - resource: track-section:platform-west
        extent: complete
      - resource: track-section:platform-east
        extent: complete
      - resource: junction:east-throat
        extent: partial
```

A resource may occur only once in one zone. Several zones may overlap the same
resource, and one zone may completely cover several Track Sections without
merging their identities or claims.

Coverage declarations define evidence semantics but no live state. A resource
can be evidenced clear only when at least one declared zone covers it
completely and every zone that overlaps it is fresh and clear. Occupied,
unknown, faulted, stale, or partial-only evidence keeps it unavailable. A
straddling train therefore affects every overlapped resource. Resources with
no complete coverage remain unknown for movement-authority purposes.

## Protection Zones and rules

A Protection Zone is a named claimable resource outside, or in addition to, a
nominal wheel path. Its declaration is an empty mapping.

```yaml
protection-zones:
  platform-overlap: {}
```

A Protection Rule attaches additional claims and Control Device requirements
to one trigger. It has required `trigger` and at least one nonempty
contribution: `claims` or `requirements`.

```yaml
protection-rules:
  west-arrival-flank:
    trigger:
      kind: junction-passage
      id: west-to-platform-1
    claims: [protection-zone:west-flank]
    requirements:
      siding-trap: protecting
```

Allowed trigger forms are:

| Trigger | Form |
| --- | --- |
| Track Section movement | `{kind: track-section, id: <id>, from: <local-port>, to: <local-port>}` |
| Connection movement | `{kind: connection, id: <id>, from: <port-ref>, to: <port-ref>}` |
| Junction Passage | `{kind: junction-passage, id: <id>}` |
| Route entry boundary | `{kind: route-boundary, route: <route-id>, boundary: entry}` |
| Route exit boundary | `{kind: route-boundary, route: <route-id>, boundary: exit}` |
| Whole Route Definition | `{kind: route-definition, id: <route-id>}` |

Claims may reference Protection Zones only. Physical Track Section and
Junction claims are always derived from the path and cannot be added,
removed, or overridden by configuration. Requirements use the same Control
Device-to-position form as Junction Passages.

Each trigger mapping contains only the fields for its `kind` and must resolve
to a declared movement, passage, or Route Definition as applicable. Every
rule whose trigger occurs in a compiled route contributes its claims and
requirements. Route-boundary and route-definition rules contribute even when
their resources are outside the nominal path. Equal requirements are merged
with all provenance retained; contradictory positions for one device make the
route invalid.

## Route Definitions

A Route Definition has required `entry` and `exit` Port references and an
optional ordered `via` array. Entry and exit must differ. A `via` item is a
path constraint reference to a Track Section, Connection, or Junction Passage.
Constraints must occur in the declared order but need not list the entire path.

```yaml
route-definitions:
  west-to-platform-1:
    entry: track-section:west-entry:west
    exit: track-section:platform-1:east
    via: [junction-passage:west-to-platform-1]
```

The only fields are `entry`, `exit`, and `via`. Route Definitions do not list
physical claims, device requirements, or an ordered path. Those are compiler
outputs, so authored data cannot omit an intervening resource.

Compilation starts by entering the owner of `entry`. It traverses a declared
Track Section movement or a selected Junction Passage, crosses a declared
Connection movement when continuity requires it, and finishes after traversing
the owner of `exit`. Entry and exit may be any Ports; they need not be layout
terminals. When they are the two Ports of one Track Section, the resulting path
contains that one directed Track Section element and claims the section.

The compiler enumerates paths satisfying movement declarations and all `via`
constraints. Exactly one acyclic path must remain. No path, more than one path,
or any selected path that revisits a physical resource is an error. Reverse
movement uses separately declared Track Section and Connection movements plus
separately declared Junction Passages; it is never inferred.

The immutable Route Plan contains:

1. ordered mappings for Track Section and Connection movements (`kind`, `id`,
   `from`, and `to`) and Junction Passages (`kind` and `id`);
2. the sorted set of physical and Protection Zone claims;
3. the sorted Control Device requirements;
4. provenance from every path element and Protection Rule that contributed a
   claim or requirement; and
5. the exact topology revision fingerprint.

The compiler audits its result before returning it. Every Track Section and
Junction in the ordered path must occur in the claim set, every applicable
Protection Rule contribution must occur, and no undeclared claim or
requirement may occur. A failed audit is a deterministic compilation error,
not a partial plan.

## Static compatibility boundary

The fixtures record only ADR 0010's closed baseline expectations. Two plans
conflict when exclusive claim sets intersect or they require different
positions of one Control Device. The same device position does not cancel a
physical conflict. Plans with disjoint claims and compatible requirements are
compatible. The stable structured compatibility result is intentionally left
to its later contract; this document does not define its API or CLI form.

## Deterministic diagnostics

Diagnostics retain the established format: a stable code, configuration path,
and human-readable message. Load errors stop immediately. For decoded,
syntactically valid YAML, validators collect all diagnostics whose prerequisite
data is valid; they never invent references to continue validation.

Validation proceeds in four phases. A later phase runs for an object only when
the fields it needs passed earlier phases:

1. shape and local values;
2. reference resolution and Port incidence;
3. cross-object topology and protection invariants; and
4. per-route compilation and plan audit.

Within a phase, diagnostics sort by this fixed collection order, then ID,
field order below, array index, and code:

1. `schema-version`;
2. `track-sections` (`ports`, `movements`, `terminal-ports`);
3. `junctions` (`ports`, `terminal-ports`);
4. `control-devices` (`positions`);
5. `connections` (`ports`, `movements`);
6. `junction-passages` (`junction`, `from`, `to`, `requirements`);
7. `occupancy-zones` (`coverage`);
8. `protection-zones`;
9. `protection-rules` (`trigger`, `claims`, `requirements`);
10. `route-definitions` (`entry`, `exit`, `via`).

IDs and set-valued results sort by Unicode code point. Ordered arrays (`ports`,
`via`, and the compiled path) retain semantic array or path order. One invalid
value produces one most-specific diagnostic in its earliest applicable phase;
cascading diagnostics that depend on that value are suppressed.

| Code | Stable meaning |
| --- | --- |
| `E001`–`E005` | Existing suffix, file, UTF-8, read, and YAML syntax failures. |
| `E100` | Root value is not a YAML mapping. |
| `E101` | Required field is missing. |
| `E102` | Field has the wrong YAML type. |
| `E103` | Schema version is unsupported. |
| `E104` | Unknown top-level field. |
| `E105` | A top-level collection is not a mapping. |
| `E106` | Unknown declaration field. |
| `E110` | ID or reference syntax is invalid. |
| `E111` | Array or mapping cardinality is invalid. |
| `E112` | Array contains a duplicate value. |
| `E113` | Values that must differ are equal. |
| `E114` | Enum value is not allowed. |
| `E200` | Reference does not resolve. |
| `E201` | Reference resolves to the wrong resource kind. |
| `E202` | Required Control Device position is not declared. |
| `E203` | A terminal Port participates in a Connection. |
| `E204` | A nonterminal Port has no Connection. |
| `E205` | A Port participates in more than one Connection. |
| `E206` | Connection joins Ports of the same owner. |
| `E207` | Junction Passage Port does not belong to its Junction. |
| `E208` | Occupancy coverage repeats one resource in a zone. |
| `E300` | Junction passage selection is nondeterministic. |
| `E301` | Protection Rule has no contribution. |
| `E400` | No path satisfies the Route Definition. |
| `E401` | More than one path satisfies the Route Definition. |
| `E402` | Selected route is cyclic or revisits a physical resource. |
| `E403` | Route constraints are absent from or out of order in the path. |
| `E404` | Effective Control Device requirements contradict. |
| `E405` | Compiled plan fails claim, requirement, or provenance audit. |

Paths use dotted mapping-key notation and zero-based array indexes, for example
`connections.entry-to-throat.ports[1]`. For mapping keys that are references,
the reference appears literally after the containing field. Compilation errors
use the Route Definition path, adding `.via[index]` when one constraint is the
most specific cause.

## Reference fixture outcomes

The machine-readable manifest at
`tests/fixtures/schema_v3/manifest.yaml` maps every fixture to its expected
validation, compilation, compatibility, or runtime-safety outcome. The
fixtures are contract inputs, not currently executable layouts.

| ADR 0010 scenario | Contract fixture expectation |
| --- | --- |
| 1 | Directly connected sections compile to both section claims and no Junction claim. |
| 2 | The station route contains both throats and every intervening section. |
| 3 | The reverse path uses reverse elements but the same base physical claims. |
| 4 | Disjoint claim and requirement sets are compatible. |
| 5 | Different positions of one device conflict. |
| 6 | Equal device positions do not remove a shared-resource conflict. |
| 7 | Crossing, throat, fouling, flank, and overlap conflicts have declared provenance. |
| 8 | One Occupancy Zone covers several distinct Track Sections. |
| 9 | Occupied, stale, unknown, or partial-only evidence keeps every affected claim unavailable. |
| 10 | A route bounded by the two Ports of one section claims that section. |
| 11 | Invalid fixtures fix expected codes for unresolved references, dangling Ports, contradictory requirements, ambiguous routes, and repeated-resource paths; plan expectations expose omitted claims. |
| 12 | Startup and lost-feedback expectations remain unknown and deny movement authority. |
| 13 | A non-path Protection Zone is present in the compiled claim set. |

## Migration from schema version 2

Migration is explicit and offline. The schema-v3 reader accepts only YAML
version 3; it does not reinterpret, merge, or automatically upgrade
schema-version-2 TOML input. The version-2 file remains unchanged until its
author produces and reviews a complete YAML version-3 replacement.

The following mechanical transformations are safe only after the author has
made the listed physical decisions:

| Version-2 declaration | Version-3 treatment | Why it is not automatic |
| --- | --- | --- |
| `blocks.<id>` | One or more Track Sections, Occupancy Zones, or both. | A Block overloads physical track, detection, operation, and reservation meanings. |
| Block `endpoints` | Candidate local Port names. | The old endpoint pair does not prove physical section boundaries, terminal status, or detector coverage. |
| `traversals.<id>` | One or more Connections and Junction Passages, with every intervening Track Section explicit. | A traversal can hide arbitrary physical resources and may duplicate the reverse direction under another ID. |
| Traversal `turnouts` | Control Device requirements on Junction Passages or Protection Rules. | The old field does not identify the physical Junction footprint or non-path flank requirement. |
| Route `traversals` | Route Definition `entry`, `exit`, and only the `via` constraints needed for uniqueness. | The old ordered list is neither a complete path nor proof that all claims were named. |
| No version-2 equivalent | Occupancy coverage extents. | Detector boundaries and complete versus partial overlap require installation knowledge. |
| No version-2 equivalent | Protection Zones and rules. | Fouling, flank, crossing, and overlap areas require physical commissioning knowledge. |
| No version-2 equivalent | Terminal Ports and explicit Track Section and Connection movements. | Layout boundaries and permitted travel cannot be inferred from missing traversals. |
| TOML document syntax | One strict YAML 1.2 document. | The syntax conversion is mechanical only after every semantic migration decision is complete. |

The migration review must therefore identify every physical rail span and
Junction footprint, place safe resource boundaries, declare direct adjacency,
declare every permitted movement explicitly, map detector coverage, add
protection contributions, translate the reviewed data to YAML, and compare each
compiled Route Plan with the real layout. No tool may claim a complete
migration from schema version 2 without those human decisions.
