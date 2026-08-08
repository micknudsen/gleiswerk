# Gleiswerk Domain Context

Gleiswerk uses this language to discuss railway topology and safe movement
independently of any configuration version, controller, simulator, or user
interface.

## Language

**Block**:
An intentionally noncanonical term because it can mean physical track,
detector coverage, an operating section, or a reserved resource. Use Track
Section, Occupancy Zone, or Reservation for the specific meaning.
_Avoid_: using “block” without qualifying its meaning in new domain contracts.

**Track Section**:
A linear physical rail span represented as one claimable topology resource
with exactly two ports. Its identity does not change with travel direction;
permitted travel is declared by explicit `from`/`to` port movements.
_Avoid_: traversal; detector block.

**Port**:
A logical connection boundary owned by one Track Section or one Junction. A
Port has at most one Connection; an unconnected Port must be an explicit
terminal or layout boundary.
_Avoid_: screen connector; inferred adjacency.

**Connection**:
An explicit fixed adjacency between two Ports. It proves continuity but adds no
separate resource claim; adjacent Track Sections remain the claimable
resources.
_Avoid_: fictional Junction; Track Section.

**Junction**:
A local topology resource that joins ports where a path is selected or a
physical conflict area must be claimed, such as a turnout, crossing, or slip.
A Junction is an atomic exclusive claim whose allowed movements are Junction
Passages.
_Avoid_: using Control Device for the physical track arrangement; ordinary
contiguous rail.

**Junction Passage**:
An explicitly allowed directed movement between two ports of one junction,
with any required Control Device positions. The reverse direction is a
separate permission over the same physical junction.
_Avoid_: a long-distance traversal that hides intervening Track Sections.

**Control Device**:
A logical state-bearing device whose required position constrains movement
through the topology. Its position evidence is sensor-observed,
assumed-after-delay, or unknown. Its hardware channel belongs to an
Installation Binding.
_Avoid_: controller address; Junction.

**Occupancy Zone**:
The declared physical coverage of an occupancy observation source. It provides
evidence about covered topology resources but is neither physical track nor a
reservation.
_Avoid_: treating partial, stale, or clear-only coverage as complete evidence.

**Protection Zone**:
A claimable safety resource in addition to a route's nominal wheel path, such
as fouling clearance, flank protection, or an overlap.
_Avoid_: assuming only wheel-path resources can conflict.

**Protection Rule**:
An immutable declaration that attaches additional Protection Zone claims and
Control Device requirements to a directed path element, Route Definition, or
route boundary. Its contributions retain provenance in the compiled Route
Plan.
_Avoid_: using a Protection Rule to add or remove a Track Section or Junction
claim; those claims are derived from the physical path.

**Route Definition**:
Immutable configuration expressing intended entry, exit, and sufficient
constraints to select one path through a topology.
_Avoid_: reservation; movement permission.

**Route Plan**:
The deterministic result of compiling a Route Definition against one immutable
topology revision: a complete directed path, resource claims, Control Device
requirements, and their provenance.
_Avoid_: treating a compiled plan as a Reservation or Movement Authority.

**Reservation**:
Dynamic ownership of exclusive physical and protection claims plus compatible
shared-value Control Device constraints for a particular operation. A
reservation alone does not authorize movement.
_Avoid_: route definition.

**Movement Authority**:
A bounded permission for a train to move that remains valid only while all
required Reservations, observations, device positions, and safety invariants
remain satisfied.
_Avoid_: route plan; successful device command.

**Installation Binding**:
A validated, revision-matched artifact mapping logical Control Devices and
observations to controller-specific channels while keeping those addresses
outside the topology model. It declares each Control Device's position evidence.
_Avoid_: hardware addresses in topology objects.
