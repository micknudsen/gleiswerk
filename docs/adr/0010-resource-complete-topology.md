# 0010: Resource-complete topology

- Status: Accepted
- Date: 2026-07-31
- Updated: 2026-08-01

## Context

ADR 0009 introduced schema version 2 so Gleiswerk could validate logical
connectivity without relying on a drawing or controller. Its block endpoints
and directed traversals were a useful step, but they do not identify every
physical resource used by a movement.

A version-2 traversal can connect any two block endpoints. If the physical
track between those endpoints passes through other blocks, the traversal does
not name them and the route cannot claim them. Conversely, two traversal IDs
can describe opposite directions over the same physical track without sharing
an identity. Compatibility based on shared traversal IDs would then depend on
configuration naming rather than the layout.

The distinction between a block and a traversal is also overloaded. In railway
practice, “block” can refer to physical track, detector coverage, an operating
section, or a reserved resource. A traversal can mean either a local passage
through a junction or an entire path between distant places. Those meanings
must be separated before Gleiswerk adds route compatibility, reservations, or
movement authority.

A continuous rail span may be split into track sections for occupancy,
operating, or route-boundary reasons. The resulting section boundary needs an
explicit topology connection, but it does not necessarily create a physical
conflict area or a separately claimable resource. Modeling every such boundary
as a junction would introduce fictional resources and obscure the difference
between ordinary continuity and a locally constrained movement.

Gleiswerk needs a coordinate-free model in which every physical resource a
train can occupy or foul is explicit and claimable. The same model must support
the simulator and physical adapters without putting controller addresses,
commands, or UI concepts in the automation core.

## Decision

This ADR establishes the topology direction for schema version 3 and supersedes
ADR 0009 as the target topology contract. It does not itself change the active
reader or implementation: schema version 2 remains the only supported grammar
until a separate schema-version-3 implementation and migration guide are
introduced.

### Physical topology

The model separates topology resources from detection, control, and runtime
safety state:

- A `TrackSection` is a linear physical rail span with exactly two ports. Its
  identity is independent of travel direction, and the section is a claimable
  resource. A path records which port it enters and leaves; any directional
  restriction is explicit rather than encoded as a second section identity.
- A `Port` is a logical connection boundary owned by one track section or one
  junction. A port participates in at most one explicit `Connection`; an
  unconnected port is valid only when declared as a terminal or layout
  boundary. Connections cannot branch; branching belongs to a junction.
- A `Connection` is an explicit fixed adjacency between exactly two ports. For
  example, it can join two immediately adjacent track sections or connect a
  track section to a junction. It establishes path continuity but is not a
  separately claimable resource. Any directional restriction is declared
  explicitly and never encoded as a duplicate track-section identity.
- A `Junction` is an atomic, exclusively claimable local resource joining
  ports where a path is selected or a physical conflict area must be
  protected. Turnouts, crossings, slips, and similarly constrained local
  arrangements use this concept. Physically independent movements require
  distinct junction resources; there is no nonexclusive-junction flag.
- A `JunctionPassage` is an explicitly allowed directed passage from one port
  of a junction to another. Reverse movement is available only when declared,
  but the reverse passage claims the same physical junction resource. Passage
  requirements must resolve to declared logical device positions and be
  internally consistent. For a given entry and effective device state, the
  physical exit must be deterministic.
- A `ControlDevice` is a logical state-bearing device whose required position
  can constrain one or more junction passages. It is distinct from both the
  physical junction, its runtime observation, and any hardware address used to
  operate it.
- An `OccupancyZone` describes the declared coverage of an observation source.
  It can cover one or more topology resources and is not itself the identity of
  the physical track or the unit of reservation.
- A `ProtectionZone` is an additional claimable safety resource, such as
  fouling clearance, flank protection, or an overlap.

Every rail span, junction area, and additional area that can be occupied or
fouled must be represented by a claimable resource. Every junction passage
automatically claims the full commissioned footprint of its owning junction;
an opposite-direction declaration cannot narrow that common physical claim.
Direction-specific protection may add further claims and requirements.
Declared protection rules can attach to any path element, route boundary, or
route definition and contribute both non-path protection claims and non-path
device requirements to a route plan.

A `Connection` contributes an ordered path transition but no separate claim.
If its physical boundary has a clearance, fouling, or protection consequence,
that area belongs in an adjacent claimable resource or a declared
`ProtectionZone`, not in a fictional junction.

Resource boundaries must coincide with safe clearance boundaries. Otherwise,
the adjacent resources must share a protection claim representing the
overlap. Software can validate the consistency of those declarations, but it
cannot prove physical independence from a coordinate-free model. That mapping
is an explicit installation and commissioning assertion; uncertain areas must
remain one conservative resource.

Occupancy coverage declarations must distinguish complete coverage from
partial overlap. A topology resource is evidenced clear only when its declared
coverage is complete, every required observation is fresh and clear, and no
relevant observation is occupied, unknown, or faulted. If coverage cannot be
expressed completely, the resource remains unknown or must be divided at the
coverage boundary.

The topology remains logical and coordinate-free. Lengths, curves, screen
positions, controller protocols, and hardware addresses are not needed to
prove path continuity or resource overlap.

### Route definitions and compiled plans

A `RouteDefinition` expresses route intent with explicit entry and exit ports
and enough passage or via constraints to select the intended path. It may be
concise, but it may not make the resulting safety model incomplete.

A deterministic route compiler resolves a definition against one immutable
topology revision. Resolution must produce exactly one path; a missing,
ambiguous, or cyclic path is a validation error. The initial model rejects a
plan that revisits a physical resource rather than implying phased device
changes or release behavior. The compiler produces a `RoutePlan` that contains:

- the complete ordered directed path, including every intervening track
  section, connection, and junction passage;
- the complete set of physical and protection resources claimed by the path
  and its declared protection rules;
- the required logical positions of control devices, including non-path flank
  requirements;
- provenance explaining which path element caused each claim and requirement;
  and
- the identity or fingerprint of the topology revision used to compile it.

The ordered path and claim set serve different purposes. The path explains
continuity and direction; the claim set establishes physical exclusion.
Opposite-direction plans use different directed path elements while retaining
the same physical resource identities.

Compatibility is derived from compiled plans, not route or traversal names.
Two plans conflict when their exclusive physical or protection claim sets
intersect, or when they require different logical positions from the same
control device. Sharing a required control-device position does not by itself
make plans compatible: their physical claims still apply. These are the closed
baseline conflict modes; adding another mode is an explicit contract change.
Conflict results and their provenance are deterministic.

Route definitions and plans are immutable configuration artifacts. They are
not reservations, commands, signal aspects, or permission for a train to move.

### Runtime and physical-layout boundary

A `Reservation` holds a plan's exclusive physical and protection claims plus
shared-value constraints on required control-device positions. Reservations
may share one device constraint only when they require the same value, and a
conflicting change remains prohibited until every holder releases it. A
`MovementAuthority` is a separate, bounded permission to move that can be
issued only after the required reservations, fresh observations, configured
control-device position evidence, and other safety invariants have been
satisfied.

Runtime use of a compiled plan requires an exact match with the active topology
revision, and the active installation binding must identify that same revision.
A stale plan or binding is rejected even when its referenced IDs still exist.

Physical adapters bind logical control devices and occupancy observations to
controller-specific channels through a validated `InstallationBinding`
artifact. The binding identifies the topology revision it implements and
declares mapping completeness, channel uniqueness, signal interpretation, and
feedback capability. Adapters consume that artifact; they do not define these
safety meanings privately.

The core issues logical intents and consumes typed, freshness-qualified logical
observations; it does not know bus addresses or protocol commands. A command
outcome is not an observation. The simulator implements the same boundary with
simulated channels.

Commanded state and observed state remain distinct. Startup, stale input,
communication loss, incomplete detector coverage, and device faults produce
unknown or faulted evidence rather than an assumed clear or correctly aligned
state. A successful command alone cannot satisfy a movement-authority
precondition. An explicitly configured `assumed-after-delay` policy may satisfy
the precondition after its delay; it remains distinct from sensor-observed
position. A device moving away from a held requirement or losing valid feedback
immediately invalidates dependent movement authority. Required constraints and
evidence remain continuous invariants for the life of the authority; losing
them never releases reservations automatically. Claims remain held until
fail-safe release rules establish that the train has cleared them.

### Acceptance scenarios for the detailed schema

The schema-version-3 design and implementation must make the following
scenarios explicit and testable:

1. Two immediately adjacent track sections linked by a direct `Connection`
   compile to one continuous path. The plan claims both sections and does not
   invent a junction claim.
2. A route from a west entry through a west throat, platform track, east
   throat, and east exit compiles to a plan containing both throats and every
   intervening track section.
3. The reverse route has explicit reverse-directed path elements and claims
   the same base physical sections and junction footprints, while allowing
   additional direction-specific protection.
4. Two routes over genuinely disjoint physical and protection resources can
   be compatible.
5. Two routes requiring different positions of one control device conflict
   even if their named endpoints differ.
6. Two routes requiring the same control-device position still conflict when
   they share track, a junction, or a protection resource.
7. Crossing, common-throat, fouling, flank-protection, and overlap conflicts
   are explainable through shared declared claims and required device
   positions, including requirements outside the nominal path.
8. One detector covering several track sections does not merge those sections
   into one topology resource.
9. A train straddling two occupancy zones keeps every affected route claim
   unavailable. Partial, stale, or clear-only coverage cannot override occupied
   or unknown evidence elsewhere.
10. A route wholly within one track section has explicit entry and exit limits
   and still claims that section.
11. Unconnected nonterminal ports, missing connections, declared path resources
    omitted from a plan, contradictory requirements, ambiguous paths, cycles,
    and repeated resources are rejected rather than guessed. Physical omissions
    that declarations cannot expose remain a commissioning concern.
12. After startup or lost feedback, affected occupancy and control evidence is
    unknown and cannot support movement authority.
13. A protection resource can be claimed even though it does not occur in the
    route's nominal wheel path.

These are semantic acceptance scenarios, not a commitment to exact
configuration field names. The subsequently reviewed field names, reference
forms, validation rules, and fixtures are fixed by the
[schema-v3 topology contract](../schema-v3-topology-contract.md).

## Alternatives considered

### Keep traversal IDs as conflict resources

This is simple but makes safety depend on authors reusing the same name for the
same physical track. Reverse-direction traversals and different path
abstractions can bypass the intended exclusion.

### Add block lists to version-2 traversals

An additional list could patch the immediate omission, but it would duplicate
path data and leave block, detector, junction, and reservation meanings
entangled. Continuity and completeness could disagree between the traversal
endpoints and the added list.

### Model every fixed adjacency as a junction

This gives the graph a uniform alternating shape, but an ordinary track-section
boundary has no independent path selection or exclusion meaning. It would
force authors to declare fictional junctions and make plans carry claims that
do not correspond to a physical safety resource. Explicit non-claimable
connections preserve continuity without that distortion.

### Make blocks multi-port topology nodes

A sufficiently rich block type could represent track, turnouts, and crossings,
but then linear occupancy, local passage rules, detector coverage, and
claimable junction areas would share one overloaded abstraction. Separate
track sections and junctions make those invariants visible.

### Infer reverse movement or geometry

Automatically reversing passages or interpreting a drawing would reduce
configuration, but it would introduce permissions and connections that were
never explicitly declared. Geometry is presentation evidence, not a safety
contract.

### Reinterpret schema version 2 in place

Changing the meaning of existing fields would hide a breaking contract change
from layout authors and tests. A new schema version makes the migration and
validation boundary explicit.

## Consequences

- Route compatibility work pauses until it can consume resource-complete route
  plans.
- The future configuration is richer, but routes can be checked independently
  of author naming conventions and travel direction.
- Adjacent track sections are linked through explicit connections, which remain
  visible in path provenance without adding false reservation claims.
- Track topology, observation coverage, device control, reservation, and
  movement authority have distinct boundaries and can evolve independently.
- The simulator and physical adapters can exercise the same core model while
  consuming the same validated installation-binding contract.
- Configuration and compilation diagnostics must remain deterministic and
  explain every derived path element, claim, and device requirement.
- Implementing this decision will be a breaking schema change with new immutable
  types, validation, examples, tests, and migration documentation.
- A version-2 block has no assumed one-to-one migration to a track section or
  occupancy zone; migration must use its actual physical and detection meaning.
- Configuration validation cannot certify the real installation. Commissioning
  must verify resource boundaries, detector coverage, control bindings, and
  fail-safe behavior against the physical layout.
- ADR 0009 is superseded. Its schema-version-2 implementation remains active
  only until schema version 3 is implemented and migration guidance is
  available.
