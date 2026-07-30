# Layout configuration

Gleiswerk uses schema version 2 to describe a logical railway topology. It
defines named blocks, endpoints, directed traversals, turnout conditions, and
routes. It does not define controller addresses, geometry, occupancy,
reservations, commands, signals, train movement, simulator behavior, or
hardware behavior.

Schema version 1 is not supported. Before the first stable release, Gleiswerk
uses one topology model rather than retaining a compatibility representation.

Each layout is a UTF-8 TOML file with the `.toml` extension. The checked-in
[reference layout](https://github.com/micknudsen/gleiswerk/blob/master/examples/reference-layout.toml)
exercises the complete vocabulary and is validated by the public command-line
interface in the automated test suite.

## Top-level structure

`schema-version` must be the integer `2`. The top-level tables `blocks`,
`turnouts`, and `routes` are optional; `traversals` is required. Every
collection is keyed by a stable lowercase kebab-case ID:

```text
^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$
```

```toml
schema-version = 2

[blocks.west-entry]
endpoints = ["west", "east"]

[blocks.platform-1]
endpoints = ["west", "east"]

[traversals.west-to-platform]
from = "west-entry.east"
to = "platform-1.west"

[routes.arrival]
traversals = ["west-to-platform"]
```

## Blocks and endpoints

Every block has exactly two distinct local endpoint IDs. An endpoint reference
has the form `block-id.endpoint-id`; it describes a logical boundary, not a
coordinate or physical drawing position. `display-name` is optional operator
metadata and must be a non-empty string when supplied.

## Turnouts

A turnout declares two or more distinct position IDs. Positions are local to
the turnout and describe selectable states only.

```toml
[turnouts.west-throat]
display-name = "West throat turnout"
positions = ["normal", "reverse"]
```

## Traversals

The required `traversals` table declares directed logical passages. Each
traversal has required `from` and `to` endpoint references that resolve to
declared block endpoints and differ from one another. Reverse passages are
separate declarations.

A traversal may have a `turnouts` table mapping turnout IDs to declared
positions. These are availability preconditions only; loading a layout never
commands or changes a turnout.

```toml
[traversals.west-to-platform]
from = "west-entry.east"
to = "platform-1.west"

[traversals.west-to-platform.turnouts]
west-throat = "normal"
```

## Routes

Every route has a non-empty ordered `traversals` array. A route contains no
block list or route-level turnout requirements; traversals are the topology
source of truth.

```toml
[routes.arrival]
display-name = "Arrival"
traversals = ["west-to-platform"]
```

This release validates the shape and references of a topology declaration. It
does not yet validate route continuity or derive route-level turnout
requirements; those are future safety rules.

## Validation and diagnostics

Validation is deterministic. For syntactically valid TOML, diagnostics appear
in configuration order: top-level fields, blocks by ID, turnouts by ID,
traversals by ID, then routes by ID. Each diagnostic has a stable error code,
a configuration path, and a human-readable message.

```text
ERROR E201 traversals.west-to-platform.to:
  references unknown endpoint "platform-1.west"
```

| Range | Concern |
| --- | --- |
| `E0xx` | File suffix/access, UTF-8 decoding, and TOML syntax. |
| `E1xx` | Schema vocabulary, types, identifiers, and local object rules. |
| `E2xx` | Endpoint, turnout-position, and traversal references. |

Unknown fields are errors at every level. This prevents misspelled or
future-version fields from being silently ignored.

## Command-line validation

Validate a layout file before using it with Gleiswerk:

```console
gleiswerk layout validate layout.toml
```

For a valid layout, the command prints the supplied path and exits with status
zero. For an invalid layout it exits with status 1 and writes its ordered
diagnostics to standard error.

## Loading API

Python callers load a layout through the configuration boundary:

```python
from pathlib import Path

from gleiswerk.layout_config import LayoutConfigurationError, load_layout

try:
    layout = load_layout(Path("layout.toml"))
except LayoutConfigurationError as error:
    for diagnostic in error.diagnostics:
        print(diagnostic.format())
```

`load_layout` accepts only an existing, readable regular `.toml` file. It
raises `LayoutConfigurationError` for file, encoding, TOML syntax, and
structural-validation failures. Diagnostics retain their source separately
from their configuration path, so callers never need to parse display text.
