"""Loading and validation for versioned layout configuration files."""

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
    Layout,
    PositionId,
    Route,
    RouteId,
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
        location = ""
        if self.source is not None:
            location = str(self.source)
        if self.path:
            location = f"{location}:{self.path}" if location else self.path
        return f"ERROR {self.code} {location}:\n  {self.message}"


class LayoutConfigurationError(Exception):
    """Raised when a layout configuration cannot be loaded or validated."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(diagnostic.format() for diagnostic in diagnostics))


def load_layout(path: Path) -> Layout:
    """Load a validated version-1 layout from an exact lowercase ``.toml`` file."""
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
    """Return all deterministic structural diagnostics for a parsed layout."""
    if not _is_table(data):
        return (Diagnostic("E100", None, "expected a TOML table", source),)

    diagnostics: list[Diagnostic] = []
    _validate_top_level(data, diagnostics, source)
    blocks = _collection(data, "blocks")
    turnouts = _collection(data, "turnouts")
    routes = _collection(data, "routes")

    _validate_blocks(blocks, diagnostics, source)
    _validate_turnouts(turnouts, diagnostics, source)
    _validate_routes(routes, diagnostics, source)
    _validate_references(blocks, turnouts, routes, diagnostics, source)
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
    if not _is_string(value):
        return False
    # Keep the configuration boundary's check aligned with the domain model.
    return re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) is not None


def _collection(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name)
    return value if _is_table(value) else {}


def _validate_top_level(
    data: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    allowed = {"schema-version", "blocks", "turnouts", "routes"}
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
            Diagnostic("E102", "schema-version", "expected integer 1", source)
        )
    elif version != 1:
        diagnostics.append(
            Diagnostic(
                "E103",
                "schema-version",
                f"unsupported schema version {version}",
                source,
            )
        )

    for name in ("blocks", "turnouts", "routes"):
        if name in data and not _is_table(data[name]):
            diagnostics.append(Diagnostic("E105", name, "expected a table", source))


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
        _validate_fields(block, path, {"display-name"}, diagnostics, source)
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
        positions = turnout.get("positions")
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
                        Diagnostic(
                            "E125", position_path, "duplicate position ID", source
                        )
                    )
                seen.add(position) if _is_string(position) else None
        _validate_display_name(turnout, path, diagnostics, source)


def _validate_routes(
    routes: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for route_id in sorted(routes):
        path = f"routes.{route_id}"
        if not _is_identifier(route_id):
            diagnostics.append(Diagnostic("E130", path, "invalid route ID", source))
        route = routes[route_id]
        if not _is_table(route):
            diagnostics.append(Diagnostic("E131", path, "expected a table", source))
            continue
        _validate_fields(
            route, path, {"blocks", "turnouts", "display-name"}, diagnostics, source
        )
        blocks = route.get("blocks")
        if blocks is None:
            diagnostics.append(
                Diagnostic("E132", f"{path}.blocks", "field is required", source)
            )
        elif not _is_array(blocks):
            diagnostics.append(
                Diagnostic("E133", f"{path}.blocks", "expected an array", source)
            )
        else:
            if not blocks:
                diagnostics.append(
                    Diagnostic("E134", f"{path}.blocks", "must not be empty", source)
                )
            seen: set[str] = set()
            for index, block_id in enumerate(blocks):
                block_path = f"{path}.blocks[{index}]"
                if not _is_identifier(block_id):
                    diagnostics.append(
                        Diagnostic("E136", block_path, "invalid block ID", source)
                    )
                elif block_id in seen:
                    diagnostics.append(
                        Diagnostic("E135", block_path, "duplicate block ID", source)
                    )
                seen.add(block_id) if _is_string(block_id) else None
        requirements = route.get("turnouts")
        if requirements is not None and not _is_table(requirements):
            diagnostics.append(
                Diagnostic("E137", f"{path}.turnouts", "expected a table", source)
            )
        elif _is_table(requirements):
            for turnout_id in sorted(requirements):
                requirement_path = f"{path}.turnouts.{turnout_id}"
                if not _is_identifier(turnout_id):
                    diagnostics.append(
                        Diagnostic(
                            "E138", requirement_path, "invalid turnout ID", source
                        )
                    )
                if not _is_identifier(requirements[turnout_id]):
                    diagnostics.append(
                        Diagnostic(
                            "E139",
                            requirement_path,
                            "invalid turnout position ID",
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
    routes: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    block_ids = set(blocks)
    turnout_positions: dict[str, list[object]] = {}
    for turnout_id, turnout in turnouts.items():
        if not _is_table(turnout):
            continue
        positions = turnout.get("positions")
        if _is_array(positions):
            turnout_positions[turnout_id] = positions
    for route_id in sorted(routes):
        route = routes[route_id]
        if not _is_table(route):
            continue
        path = f"routes.{route_id}"
        route_blocks = route.get("blocks")
        if _is_array(route_blocks):
            for index, block_id in enumerate(route_blocks):
                if _is_identifier(block_id) and block_id not in block_ids:
                    diagnostics.append(
                        Diagnostic(
                            "E201",
                            f"{path}.blocks[{index}]",
                            f"references unknown block {block_id!r}",
                            source,
                        )
                    )
        requirements = route.get("turnouts")
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


def _build_layout(data: Mapping[str, object]) -> Layout:
    blocks = tuple(
        _build_block(block_id, block)
        for block_id, block in sorted(_collection(data, "blocks").items())
    )
    turnouts = tuple(
        _build_turnout(turnout_id, turnout)
        for turnout_id, turnout in sorted(_collection(data, "turnouts").items())
    )
    routes = tuple(
        _build_route(route_id, route)
        for route_id, route in sorted(_collection(data, "routes").items())
    )
    return Layout(blocks, turnouts, routes)


def _build_block(block_id: str, value: object) -> Block:
    assert _is_table(value)
    return Block(BlockId(block_id), _display_name(value))


def _build_turnout(turnout_id: str, value: object) -> Turnout:
    assert _is_table(value)
    positions = value["positions"]
    assert _is_array(positions)
    position_ids = _string_values(positions)
    return Turnout(
        TurnoutId(turnout_id),
        tuple(PositionId(position) for position in position_ids),
        _display_name(value),
    )


def _build_route(route_id: str, value: object) -> Route:
    assert _is_table(value)
    blocks = value["blocks"]
    assert _is_array(blocks)
    block_ids = _string_values(blocks)
    requirements = value.get("turnouts", {})
    assert _is_table(requirements)
    turnout_positions = {
        turnout_id: position
        for turnout_id, position in requirements.items()
        if _is_string(position)
    }
    assert len(turnout_positions) == len(requirements)
    return Route(
        RouteId(route_id),
        tuple(BlockId(block_id) for block_id in block_ids),
        {
            TurnoutId(turnout_id): PositionId(position)
            for turnout_id, position in turnout_positions.items()
        },
        _display_name(value),
    )


def _display_name(value: Mapping[str, object]) -> str | None:
    display_name = value.get("display-name")
    return display_name if _is_string(display_name) else None


def _string_values(values: list[object]) -> tuple[str, ...]:
    string_values = tuple(value for value in values if _is_string(value))
    assert len(string_values) == len(values)
    return string_values
