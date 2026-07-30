"""Loading and validation for schema-version 2 layout configuration files."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, TypeGuard

from gleiswerk.layout import (
    Block,
    BlockId,
    EndpointId,
    EndpointReference,
    Layout,
    PositionId,
    Route,
    RouteId,
    Traversal,
    TraversalId,
    Turnout,
    TurnoutId,
)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One actionable layout-configuration problem."""

    code: str
    path: str | None
    message: str
    source: Path | None = None

    def format(self) -> str:
        """Format the diagnostic for a human-facing command-line interface."""
        location = str(self.source) if self.source is not None else ""
        if self.path:
            location = f"{location}:{self.path}" if location else self.path
        return f"ERROR {self.code} {location}:\n  {self.message}"


class LayoutConfigurationError(Exception):
    """Raised when a layout configuration cannot be loaded or validated."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(diagnostic.format() for diagnostic in diagnostics))


def load_layout(path: Path) -> Layout:
    """Load a validated schema-version 2 layout from a lowercase ``.toml`` file."""
    source = Path(path)
    if source.suffix != ".toml":
        _raise(Diagnostic("E001", None, "expected a file with a .toml suffix", source))
    if not source.is_file():
        _raise(Diagnostic("E002", None, "expected an existing regular file", source))
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _raise(Diagnostic("E003", None, "expected UTF-8 encoded text", source))
    except OSError as error:
        _raise(
            Diagnostic("E004", None, f"could not read file: {error.strerror}", source)
        )
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        _raise(Diagnostic("E005", None, f"invalid TOML: {error}", source))

    diagnostics = validate_layout_data(data, source=source)
    if diagnostics:
        raise LayoutConfigurationError(diagnostics)
    return _build_layout(data)


def validate_layout_data(
    data: object, *, source: Path | None = None
) -> tuple[Diagnostic, ...]:
    """Return all deterministic structural diagnostics for parsed TOML data."""
    if not _is_table(data):
        return (Diagnostic("E100", None, "expected a TOML table", source),)

    diagnostics: list[Diagnostic] = []
    _validate_top_level(data, diagnostics, source)
    blocks = _collection(data, "blocks")
    turnouts = _collection(data, "turnouts")
    traversals = _collection(data, "traversals")
    routes = _collection(data, "routes")
    _validate_blocks(blocks, diagnostics, source)
    _validate_turnouts(turnouts, diagnostics, source)
    _validate_traversals(traversals, diagnostics, source)
    _validate_routes(routes, diagnostics, source)
    _validate_references(blocks, turnouts, traversals, routes, diagnostics, source)
    return tuple(diagnostics)


def _raise(diagnostic: Diagnostic) -> NoReturn:
    raise LayoutConfigurationError((diagnostic,))


def _is_table(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_array(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_string(value: object) -> TypeGuard[str]:
    return isinstance(value, str)


def _is_identifier(value: object) -> bool:
    return (
        _is_string(value)
        and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) is not None
    )


def _is_endpoint_reference(value: object) -> bool:
    if not _is_string(value):
        return False
    try:
        EndpointReference.from_string(value)
    except ValueError:
        return False
    return True


def _collection(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name)
    return value if _is_table(value) else {}


def _validate_top_level(
    data: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    allowed = {"schema-version", "blocks", "turnouts", "traversals", "routes"}
    for key in sorted(data):
        if key not in allowed:
            diagnostics.append(
                Diagnostic("E104", key, "unknown top-level field", source)
            )
    version = data.get("schema-version")
    if version is None:
        diagnostics.append(
            Diagnostic("E101", "schema-version", "field is required", source)
        )
    elif not isinstance(version, int) or isinstance(version, bool):
        diagnostics.append(
            Diagnostic("E102", "schema-version", "expected integer 2", source)
        )
    elif version != 2:
        diagnostics.append(
            Diagnostic(
                "E103",
                "schema-version",
                f"unsupported schema version {version}",
                source,
            )
        )
    for name in ("blocks", "turnouts", "traversals", "routes"):
        if name in data and not _is_table(data[name]):
            diagnostics.append(Diagnostic("E105", name, "expected a table", source))
    if data.get("schema-version") == 2 and "traversals" not in data:
        diagnostics.append(
            Diagnostic("E108", "traversals", "field is required", source)
        )


def _validate_blocks(
    blocks: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for block_id in sorted(blocks):
        path = f"blocks.{block_id}"
        if not _is_identifier(block_id):
            diagnostics.append(Diagnostic("E110", path, "invalid block ID", source))
        block = blocks[block_id]
        if not _is_table(block):
            diagnostics.append(Diagnostic("E111", path, "expected a table", source))
            continue
        _validate_fields(
            block, path, {"endpoints", "display-name"}, diagnostics, source
        )
        endpoints = block.get("endpoints")
        if endpoints is None:
            diagnostics.append(
                Diagnostic("E112", f"{path}.endpoints", "field is required", source)
            )
        elif not _is_array(endpoints):
            diagnostics.append(
                Diagnostic("E113", f"{path}.endpoints", "expected an array", source)
            )
        else:
            if len(endpoints) != 2:
                diagnostics.append(
                    Diagnostic(
                        "E114",
                        f"{path}.endpoints",
                        "expected exactly two endpoints",
                        source,
                    )
                )
            seen: set[str] = set()
            for index, endpoint in enumerate(endpoints):
                endpoint_path = f"{path}.endpoints[{index}]"
                if not _is_identifier(endpoint):
                    diagnostics.append(
                        Diagnostic("E116", endpoint_path, "invalid endpoint ID", source)
                    )
                elif endpoint in seen:
                    diagnostics.append(
                        Diagnostic(
                            "E115", endpoint_path, "duplicate endpoint ID", source
                        )
                    )
                if _is_string(endpoint):
                    seen.add(endpoint)
        _validate_display_name(block, path, diagnostics, source)


def _validate_turnouts(
    turnouts: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for turnout_id in sorted(turnouts):
        path = f"turnouts.{turnout_id}"
        if not _is_identifier(turnout_id):
            diagnostics.append(Diagnostic("E120", path, "invalid turnout ID", source))
        turnout = turnouts[turnout_id]
        if not _is_table(turnout):
            diagnostics.append(Diagnostic("E121", path, "expected a table", source))
            continue
        _validate_fields(
            turnout, path, {"positions", "display-name"}, diagnostics, source
        )
        _validate_positions(turnout.get("positions"), path, diagnostics, source)
        _validate_display_name(turnout, path, diagnostics, source)


def _validate_positions(
    positions: object, path: str, diagnostics: list[Diagnostic], source: Path | None
) -> None:
    if positions is None:
        diagnostics.append(
            Diagnostic("E122", f"{path}.positions", "field is required", source)
        )
    elif not _is_array(positions):
        diagnostics.append(
            Diagnostic("E123", f"{path}.positions", "expected an array", source)
        )
    else:
        if len(positions) < 2:
            diagnostics.append(
                Diagnostic(
                    "E124",
                    f"{path}.positions",
                    "expected at least two positions",
                    source,
                )
            )
        seen: set[str] = set()
        for index, position in enumerate(positions):
            position_path = f"{path}.positions[{index}]"
            if not _is_identifier(position):
                diagnostics.append(
                    Diagnostic("E126", position_path, "invalid position ID", source)
                )
            elif position in seen:
                diagnostics.append(
                    Diagnostic("E125", position_path, "duplicate position ID", source)
                )
            if _is_string(position):
                seen.add(position)


def _validate_traversals(
    traversals: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for traversal_id in sorted(traversals):
        path = f"traversals.{traversal_id}"
        if not _is_identifier(traversal_id):
            diagnostics.append(Diagnostic("E130", path, "invalid traversal ID", source))
        traversal = traversals[traversal_id]
        if not _is_table(traversal):
            diagnostics.append(Diagnostic("E131", path, "expected a table", source))
            continue
        _validate_fields(
            traversal, path, {"from", "to", "turnouts"}, diagnostics, source
        )
        for field in ("from", "to"):
            value = traversal.get(field)
            field_path = f"{path}.{field}"
            if value is None:
                diagnostics.append(
                    Diagnostic("E132", field_path, "field is required", source)
                )
            elif not _is_endpoint_reference(value):
                diagnostics.append(
                    Diagnostic("E133", field_path, "invalid endpoint reference", source)
                )
        from_endpoint = traversal.get("from")
        to_endpoint = traversal.get("to")
        if _is_endpoint_reference(from_endpoint) and from_endpoint == to_endpoint:
            diagnostics.append(
                Diagnostic("E134", path, "traversal endpoints must differ", source)
            )
        _validate_turnout_requirements(
            traversal.get("turnouts"), path, diagnostics, source
        )


def _validate_turnout_requirements(
    requirements: object, path: str, diagnostics: list[Diagnostic], source: Path | None
) -> None:
    if requirements is not None and not _is_table(requirements):
        diagnostics.append(
            Diagnostic("E135", f"{path}.turnouts", "expected a table", source)
        )
    elif _is_table(requirements):
        for turnout_id in sorted(requirements):
            requirement_path = f"{path}.turnouts.{turnout_id}"
            if not _is_identifier(turnout_id):
                diagnostics.append(
                    Diagnostic("E136", requirement_path, "invalid turnout ID", source)
                )
            if not _is_identifier(requirements[turnout_id]):
                diagnostics.append(
                    Diagnostic(
                        "E137", requirement_path, "invalid turnout position ID", source
                    )
                )


def _validate_routes(
    routes: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for route_id in sorted(routes):
        path = f"routes.{route_id}"
        if not _is_identifier(route_id):
            diagnostics.append(Diagnostic("E140", path, "invalid route ID", source))
        route = routes[route_id]
        if not _is_table(route):
            diagnostics.append(Diagnostic("E141", path, "expected a table", source))
            continue
        _validate_fields(
            route, path, {"traversals", "display-name"}, diagnostics, source
        )
        traversals = route.get("traversals")
        if traversals is None:
            diagnostics.append(
                Diagnostic("E142", f"{path}.traversals", "field is required", source)
            )
        elif not _is_array(traversals):
            diagnostics.append(
                Diagnostic("E143", f"{path}.traversals", "expected an array", source)
            )
        else:
            if not traversals:
                diagnostics.append(
                    Diagnostic(
                        "E144", f"{path}.traversals", "must not be empty", source
                    )
                )
            for index, traversal_id in enumerate(traversals):
                if not _is_identifier(traversal_id):
                    diagnostics.append(
                        Diagnostic(
                            "E145",
                            f"{path}.traversals[{index}]",
                            "invalid traversal ID",
                            source,
                        )
                    )
        _validate_display_name(route, path, diagnostics, source)


def _validate_fields(
    data: Mapping[str, object],
    path: str,
    allowed: set[str],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    for key in sorted(data):
        if key not in allowed:
            diagnostics.append(
                Diagnostic("E106", f"{path}.{key}", "unknown field", source)
            )


def _validate_display_name(
    data: Mapping[str, object],
    path: str,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    if "display-name" in data and (
        not _is_string(data["display-name"]) or not data["display-name"]
    ):
        diagnostics.append(
            Diagnostic(
                "E107", f"{path}.display-name", "expected a non-empty string", source
            )
        )


def _validate_references(
    blocks: Mapping[str, object],
    turnouts: Mapping[str, object],
    traversals: Mapping[str, object],
    routes: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    endpoints: set[str] = set()
    for block_id, block in blocks.items():
        if not _is_identifier(block_id) or not _is_table(block):
            continue
        declared_endpoints = block.get("endpoints")
        if not _is_array(declared_endpoints):
            continue
        endpoints.update(
            f"{block_id}.{endpoint}"
            for endpoint in declared_endpoints
            if _is_identifier(endpoint)
        )
    turnout_positions = {
        turnout_id: positions
        for turnout_id, turnout in turnouts.items()
        if _is_identifier(turnout_id)
        and _is_table(turnout)
        and _is_array(positions := turnout.get("positions"))
    }
    for traversal_id in sorted(traversals):
        traversal = traversals[traversal_id]
        if not _is_table(traversal):
            continue
        path = f"traversals.{traversal_id}"
        for field in ("from", "to"):
            endpoint = traversal.get(field)
            if _is_endpoint_reference(endpoint) and endpoint not in endpoints:
                diagnostics.append(
                    Diagnostic(
                        "E201",
                        f"{path}.{field}",
                        f"references unknown endpoint {endpoint!r}",
                        source,
                    )
                )
        requirements = traversal.get("turnouts")
        if not _is_table(requirements):
            continue
        for turnout_id in sorted(requirements):
            position = requirements[turnout_id]
            requirement_path = f"{path}.turnouts.{turnout_id}"
            if not _is_identifier(turnout_id) or not _is_identifier(position):
                continue
            if turnout_id not in turnout_positions:
                diagnostics.append(
                    Diagnostic(
                        "E202",
                        requirement_path,
                        f"references unknown turnout {turnout_id!r}",
                        source,
                    )
                )
            elif position not in turnout_positions[turnout_id]:
                diagnostics.append(
                    Diagnostic(
                        "E203",
                        requirement_path,
                        f"requires unsupported turnout position {position!r}",
                        source,
                    )
                )
    traversal_ids = set(traversals)
    for route_id in sorted(routes):
        route = routes[route_id]
        if not _is_table(route):
            continue
        route_traversals = route.get("traversals")
        if not _is_array(route_traversals):
            continue
        for index, traversal_id in enumerate(route_traversals):
            if _is_identifier(traversal_id) and traversal_id not in traversal_ids:
                diagnostics.append(
                    Diagnostic(
                        "E204",
                        f"routes.{route_id}.traversals[{index}]",
                        f"references unknown traversal {traversal_id!r}",
                        source,
                    )
                )


def _build_layout(data: Mapping[str, object]) -> Layout:
    blocks = tuple(
        _build_block(block_id, value)
        for block_id, value in sorted(_collection(data, "blocks").items())
    )
    turnouts = tuple(
        _build_turnout(turnout_id, value)
        for turnout_id, value in sorted(_collection(data, "turnouts").items())
    )
    traversals = tuple(
        _build_traversal(traversal_id, value)
        for traversal_id, value in sorted(_collection(data, "traversals").items())
    )
    routes = tuple(
        _build_route(route_id, value)
        for route_id, value in sorted(_collection(data, "routes").items())
    )
    return Layout(blocks, turnouts, traversals, routes)


def _build_block(block_id: str, value: object) -> Block:
    assert _is_table(value)
    endpoints = value["endpoints"]
    assert _is_array(endpoints) and len(endpoints) == 2
    return Block(
        BlockId(block_id),
        (
            EndpointId(_string_values(endpoints)[0]),
            EndpointId(_string_values(endpoints)[1]),
        ),
        _display_name(value),
    )


def _build_turnout(turnout_id: str, value: object) -> Turnout:
    assert _is_table(value)
    positions = value["positions"]
    assert _is_array(positions)
    return Turnout(
        TurnoutId(turnout_id),
        tuple(PositionId(position) for position in _string_values(positions)),
        _display_name(value),
    )


def _build_traversal(traversal_id: str, value: object) -> Traversal:
    assert _is_table(value)
    from_value, to_value = value["from"], value["to"]
    assert _is_string(from_value) and _is_string(to_value)
    requirements = value.get("turnouts", {})
    assert _is_table(requirements)
    return Traversal(
        TraversalId(traversal_id),
        EndpointReference.from_string(from_value),
        EndpointReference.from_string(to_value),
        {
            TurnoutId(turnout_id): PositionId(position)
            for turnout_id, position in requirements.items()
            if _is_string(position)
        },
    )


def _build_route(route_id: str, value: object) -> Route:
    assert _is_table(value)
    traversals = value["traversals"]
    assert _is_array(traversals)
    return Route(
        RouteId(route_id),
        tuple(TraversalId(value) for value in _string_values(traversals)),
        _display_name(value),
    )


def _display_name(value: Mapping[str, object]) -> str | None:
    display_name = value.get("display-name")
    return display_name if _is_string(display_name) else None


def _string_values(values: list[object]) -> tuple[str, ...]:
    strings = tuple(value for value in values if _is_string(value))
    assert len(strings) == len(values)
    return strings
