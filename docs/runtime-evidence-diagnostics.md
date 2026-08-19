# Runtime evidence diagnostics

`gleiswerk runtime-evidence diagnose SCENARIO` is a deterministic, offline
supervision workflow for the `RuntimeEvidenceService` contract. It uses no
controller endpoint, protocol frame, or hardware connection, and it cannot
command hardware. Consequently, it has no live-hardware option or
acknowledgement requirement. Any future command that opens a controller
connection must require an explicit `--live-hardware` acknowledgement before
it does so.

The command accepts a deliberately bounded YAML scenario. It configures only
logical targets and drives the service with explicit baseline, update, loss,
malformed-input, and recovery events. The clock begins at zero and advances
only through `advance-time`, making the result reproducible.

```yaml
topology-revision: demo-revision
maximum-age-seconds: 30 # Optional; defaults to 30.
targets:
  - {zone: platform, source: platform-s88}
  - {zone: siding, source: siding-s88}
operations:
  - operation: baseline
    observations:
      - {zone: platform, state: clear}
      - {zone: siding, state: occupied}
  - {operation: update, order: 1, observations: [{zone: platform, state: occupied}]}
```

Each target needs a unique logical zone and source. A `baseline` must include
every target. An `update` has an integer order and may include one or more
targets. It can set `redelivered: true` only for a proven identical repeated
update. `transport-lost` and `malformed-input` accept an optional stable
`detail`; `advance-time` takes a nonnegative `seconds` value.

The YAML report includes topology revision, session identity, source status,
completeness, every source's identity, state, receipt-relative observation
time, and freshness. Faulted reports also include the stable fault kind and
detail. The command exits zero only for a complete, available, fresh snapshot;
unknown, stale, or faulted evidence exits one. A loss, malformed input,
incomplete baseline, duplicate target, or unordered update clears all values
and fails closed. Recovery requires another complete baseline, which begins a
new session.
