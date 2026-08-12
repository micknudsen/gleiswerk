# RoutePlan compatibility contract

Status: implementation contract. This document defines the stable, structured
result of static compatibility analysis for validated schema-v3 `RoutePlan`
objects. The controller-independent core API is
`gleiswerk.route_compatibility.analyze_route_plans`; this contract defines its
stable result shape. `gleiswerk layout compatibility FILE` emits this shape as
a YAML document after loading and compiling every Route Definition in `FILE`.

## Boundary and inputs

Compatibility analysis compares two or more immutable `RoutePlan` objects
compiled from the same topology revision. The input collection must contain
unique Route Definition IDs. Passing plans from different revisions or two
plans with the same Route Definition ID is a caller error; it does not produce
a compatible or conflicting result.

Analysis is static: it compares declared exclusive claims and required Control
Device positions. It does not infer physical geometry, prove live clearance,
reserve resources, or authorize movement. It also does not command a device.
Those decisions remain runtime safety concerns; a compatible result is an
explanation of declared plans, not permission for a train to move.

The closed baseline has exactly two conflict kinds:

1. `overlapping-exclusive-claim`: both plans claim the same Track Section,
   Junction, or Protection Zone.
2. `incompatible-control-device-requirement`: both plans require different
   positions from the same Control Device.

Equal requirements for one Control Device are not a conflict. They also never
remove an overlapping exclusive-claim conflict. No other fact can make two
plans conflict in this contract; adding a conflict kind is a contract change.

## CLI workflow

Use the CLI after validating a schema-v3 layout. It compiles every Route
Definition in the file and reports every unordered pair. The command is
read-only and exits zero whether the report contains compatible or conflicting
pairs; use the `compatible` field and `conflicts` list to interpret the
report.

The checked-in reference layouts provide runnable examples. From a development
checkout, run:

```console
gleiswerk layout compatibility tests/fixtures/schema_v3/valid-station.yaml
```

The station report includes an explicitly compatible pair:

```yaml
route-pair: [depot-only, west-to-east-via-platform-1]
compatible: true
conflicts: []
```

`valid-direct.yaml` provides a minimal conflicting layout:

```console
gleiswerk layout compatibility tests/fixtures/schema_v3/valid-direct.yaml
```

It reports the shared `platform` Track Section and why each route claims it:

```yaml
route-pair: [direct-arrival, within-platform]
compatible: false
conflicts:
  - kind: overlapping-exclusive-claim
    resource: track-section:platform
    provenance:
      direct-arrival: [track-section:platform]
      within-platform: [track-section:platform]
```

The automated CLI tests run both commands against these exact reference
layouts. The full output also has a `topology-revision` value; it identifies
the declared topology used to compile the compared plans.

CLI reports use block-style collections for records and compact flow-style
sequences for scalar references, route pairs, and empty lists. This preserves
the structure of each report while keeping short deterministic values easy to
compare.

### Reading conflicts

`overlapping-exclusive-claim` means both compiled plans declare the same
exclusive Track Section, Junction, or Protection Zone. The `resource` names
what they share, while `provenance` lists every path or protection rule that
caused each plan to claim it.

`incompatible-control-device-requirement` means both plans name the same
Control Device but require different declared positions. Its
`required-positions` mapping shows the disagreement, and `provenance` names
the passages or rules that imposed those positions. Matching positions do not
produce this conflict, but they do not make a shared resource safe to use.

The result is deterministic: route pairs, conflicts, and every provenance list
always have the canonical order described below. That makes reports suitable
for review, regression tests, and repeatable tooling; it does not add any live
railway-state knowledge.

## Result model

The result is an immutable `CompatibilityAnalysisResult` with this logical
shape. Field names are normative for a serialized or public API form.

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
      - kind: incompatible-control-device-requirement
        control-device: shared-turnout
        required-positions:
          route-a: normal
          route-b: reverse
        provenance:
          route-a: [junction-passage:route-a-passage]
          route-b: [junction-passage:route-b-passage]
```

`topology-revision` is the common revision from the input plans. `pairs`
contains one `PairCompatibilityResult` for every unordered pair of inputs.
`route-pair` contains exactly two Route Definition IDs. Its first ID names the
left plan used in each conflict payload; its second ID names the right plan.

`compatible` is `true` exactly when `conflicts` is empty. A compatible pair is
therefore explicit rather than omitted:

```yaml
route-pair: [depot-only, west-to-east-via-platform-1]
compatible: true
conflicts: []
```

An `overlapping-exclusive-claim` conflict has `kind`, `resource`, and
`provenance`. `resource` is one claimable-resource reference. Its provenance
maps both Route Definition IDs in `route-pair` to the complete nonempty list
of source strings from that plan's `claim_provenance[resource]`.

An `incompatible-control-device-requirement` conflict has `kind`,
`control-device`, `required-positions`, and `provenance`. Both mappings have
exactly the Route Definition IDs in `route-pair`. `required-positions` gives
each plan's declared position ID. `provenance` gives the complete nonempty list
of source strings from that plan's `requirement_provenance[control-device]`.

The strings in provenance retain the compiled-plan vocabulary: a path source
is `track-section:<id>` or `junction-passage:<id>`; a rule source is
`protection-rule:<id>`. Provenance explains the declared contribution. It does
not claim a live device state, a reservation holder, or an authority decision.

## Canonical order

All ordering is deterministic and independent of input order:

- Normalize every route pair by Unicode code-point ordering of its two Route
  Definition IDs, then sort `pairs` lexicographically by that tuple.
- Sort conflicts by `kind` in Unicode code-point order. Within one kind, sort
  claim conflicts by `(resource kind, resource ID)` and requirement conflicts
  by Control Device ID, again in Unicode code-point order.
- Sort source strings in each provenance list by Unicode code point. Do not
  deduplicate sources: each list preserves every contribution after sorting.

The `claims`, `requirements`, and provenance already present in `RoutePlan`
are inputs, not a result-order exception. The analysis must compare their
identity values, then emit its own result using the order above.

## Reference expected results

The schema-v3 fixture manifest contains representative `expected-result`
objects for one compatible pair and each baseline conflict kind. They are
contract fixtures, not analyzer output checked by the current compiler. A
future analyzer must produce these result shapes and values exactly.
