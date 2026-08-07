# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportMissingModuleSource=false, reportOperatorIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Strict schema-version 3 core-topology loading and validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, TypeGuard, cast

import yaml

from gleiswerk.topology import (
    Connection,
    ConnectionId,
    ConnectionMovement,
    ControlDevice,
    ControlDeviceId,
    DevicePositionId,
    DeviceRequirement,
    Junction,
    JunctionId,
    JunctionPassage,
    JunctionPassageId,
    JunctionPort,
    PortId,
    PortReference,
    Topology,
    TrackSection,
    TrackSectionId,
    TrackSectionMovement,
    TrackSectionPort,
)

_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_TOP_LEVEL_FIELDS = {
    "schema-version",
    "track-sections",
    "junctions",
    "control-devices",
    "connections",
    "junction-passages",
}


class _StrictYamlLoader(yaml.SafeLoader):  # pyright: ignore[reportUntypedBaseClass]
    """Safe YAML loading with duplicate mapping keys rejected."""

    def construct_mapping(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[str, object]:
        keys: set[str] = set()
        for key_node, _value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode):
                raise yaml.YAMLError("mapping keys must be strings")
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.YAMLError("mapping keys must be strings")
            if key in keys:
                raise yaml.YAMLError(f"duplicate mapping key: {key}")
            keys.add(key)
        return cast(dict[str, object], super().construct_mapping(node, deep=deep))


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One stable, actionable schema-v3 configuration problem."""

    code: str
    path: str | None
    message: str
    source: Path | None = None

    def format(self) -> str:
        location = str(self.source) if self.source is not None else ""
        if self.path:
            location = f"{location}:{self.path}" if location else self.path
        return f"ERROR {self.code} {location}:\n  {self.message}"


class TopologyConfigurationError(Exception):
    """Raised when a schema-v3 core topology cannot be loaded."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(diagnostic.format() for diagnostic in diagnostics))


def load_topology(path: Path) -> Topology:
    """Load a validated schema-version 3 core topology from a YAML file."""
    source = Path(path)
    if source.suffix != ".yaml":
        _raise(Diagnostic("E001", None, "expected a file with a .yaml suffix", source))
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
        _reject_yaml_anchors_and_aliases(text)
        data = yaml.load(text, Loader=_StrictYamlLoader)
    except yaml.YAMLError as error:
        _raise(Diagnostic("E005", None, f"invalid YAML: {error}", source))
    diagnostics = validate_topology_data(data, source=source)
    if diagnostics:
        raise TopologyConfigurationError(diagnostics)
    assert isinstance(data, Mapping)
    return _build_topology(data)


def validate_topology_data(
    data: object, *, source: Path | None = None
) -> tuple[Diagnostic, ...]:
    """Return deterministic diagnostics for a decoded schema-v3 core topology."""
    if not _is_mapping(data):
        return (Diagnostic("E100", None, "expected a YAML mapping", source),)

    diagnostics: list[Diagnostic] = []
    _validate_top_level(data, diagnostics, source)
    sections = _collection(data, "track-sections")
    junctions = _collection(data, "junctions")
    devices = _collection(data, "control-devices")
    connections = _collection(data, "connections")
    passages = _collection(data, "junction-passages")
    _validate_sections(sections, diagnostics, source)
    _validate_junctions(junctions, diagnostics, source)
    _validate_devices(devices, diagnostics, source)
    _validate_connections(connections, diagnostics, source)
    _validate_passages(passages, diagnostics, source)
    _validate_local_port_references(sections, diagnostics, source, "track-sections")
    _validate_local_port_references(junctions, diagnostics, source, "junctions")
    _validate_references(
        sections, junctions, devices, connections, passages, diagnostics, source
    )
    return tuple(diagnostics)


def _reject_yaml_anchors_and_aliases(text: str) -> None:
    for event in yaml.parse(text):
        if getattr(event, "anchor", None) is not None:
            raise yaml.YAMLError("anchors and aliases are not allowed")


def _raise(diagnostic: Diagnostic) -> NoReturn:
    raise TopologyConfigurationError((diagnostic,))


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping) and all(isinstance(key, str) for key in value)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_identifier(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def _collection(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name, {})
    return value if _is_mapping(value) else {}


def _validate_top_level(
    data: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    version = data.get("schema-version")
    if version is None:
        diagnostics.append(
            Diagnostic("E101", "schema-version", "field is required", source)
        )
    elif type(version) is not int:
        diagnostics.append(
            Diagnostic("E102", "schema-version", "expected integer 3", source)
        )
    elif version != 3:
        diagnostics.append(
            Diagnostic(
                "E103",
                "schema-version",
                f"unsupported schema version {version}",
                source,
            )
        )
    for field in sorted(set(data) - _TOP_LEVEL_FIELDS):
        diagnostics.append(Diagnostic("E104", field, "unknown top-level field", source))
    for field in sorted(_TOP_LEVEL_FIELDS - {"schema-version"}):
        if field in data and not _is_mapping(data[field]):
            diagnostics.append(Diagnostic("E105", field, "expected a mapping", source))


def _validate_sections(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"track-sections.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid track section ID", source)
            )
            continue
        _validate_linear_declaration(declaration, path, diagnostics, source)


def _validate_junctions(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"junctions.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(Diagnostic("E110", path, "invalid junction ID", source))
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(
            declaration, {"ports", "terminal-ports"}, path, diagnostics, source
        )
        _validate_ports(
            declaration.get("ports"), f"{path}.ports", 2, diagnostics, source
        )
        _validate_terminal_ports(declaration, path, diagnostics, source)


def _validate_linear_declaration(
    declaration: object, path: str, diagnostics: list[Diagnostic], source: Path | None
) -> None:
    if not _is_mapping(declaration):
        diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
        return
    _unknown_fields(
        declaration, {"ports", "movements", "terminal-ports"}, path, diagnostics, source
    )
    _validate_ports(
        declaration.get("ports"), f"{path}.ports", 2, diagnostics, source, exact=True
    )
    _validate_movements(
        declaration.get("movements"),
        f"{path}.movements",
        diagnostics,
        source,
        local=True,
    )
    _validate_terminal_ports(declaration, path, diagnostics, source)


def _validate_devices(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"control-devices.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid control device ID", source)
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(declaration, {"positions"}, path, diagnostics, source)
        _validate_identifier_array(
            declaration.get("positions"), f"{path}.positions", 2, diagnostics, source
        )


def _validate_connections(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"connections.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid connection ID", source)
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(declaration, {"ports", "movements"}, path, diagnostics, source)
        _validate_references_array(
            declaration.get("ports"), f"{path}.ports", 2, diagnostics, source
        )
        _validate_movements(
            declaration.get("movements"),
            f"{path}.movements",
            diagnostics,
            source,
            local=False,
        )


def _validate_passages(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"junction-passages.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid junction passage ID", source)
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(
            declaration,
            {"junction", "from", "to", "requirements"},
            path,
            diagnostics,
            source,
        )
        for field in ("junction", "from", "to"):
            value = declaration.get(field)
            if value is None:
                diagnostics.append(
                    Diagnostic("E101", f"{path}.{field}", "field is required", source)
                )
            elif not _is_identifier(value):
                diagnostics.append(
                    Diagnostic(
                        "E110", f"{path}.{field}", "expected an identifier", source
                    )
                )
        if declaration.get("from") == declaration.get("to") and _is_identifier(
            declaration.get("from")
        ):
            diagnostics.append(
                Diagnostic("E113", f"{path}.to", "from and to must differ", source)
            )
        requirements = declaration.get("requirements", {})
        if not _is_mapping(requirements):
            diagnostics.append(
                Diagnostic("E102", f"{path}.requirements", "expected a mapping", source)
            )
        else:
            for device, position in sorted(requirements.items()):
                requirement_path = f"{path}.requirements.{device}"
                if not _is_identifier(device) or not _is_identifier(position):
                    diagnostics.append(
                        Diagnostic(
                            "E110",
                            requirement_path,
                            "expected identifier references",
                            source,
                        )
                    )


def _unknown_fields(
    declaration: Mapping[str, object],
    allowed: set[str],
    path: str,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    for field in sorted(set(declaration) - allowed):
        diagnostics.append(
            Diagnostic("E106", f"{path}.{field}", "unknown declaration field", source)
        )


def _validate_ports(
    value: object,
    path: str,
    minimum: int,
    diagnostics: list[Diagnostic],
    source: Path | None,
    *,
    exact: bool = False,
) -> None:
    _validate_identifier_array(value, path, minimum, diagnostics, source, exact=exact)


def _validate_identifier_array(
    value: object,
    path: str,
    minimum: int,
    diagnostics: list[Diagnostic],
    source: Path | None,
    *,
    exact: bool = False,
) -> None:
    if not _is_list(value):
        diagnostics.append(Diagnostic("E102", path, "expected an array", source))
        return
    if (exact and len(value) != minimum) or (not exact and len(value) < minimum):
        diagnostics.append(
            Diagnostic(
                "E111",
                path,
                f"expected {'exactly' if exact else 'at least'} {minimum} values",
                source,
            )
        )
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _is_identifier(item):
            diagnostics.append(
                Diagnostic("E110", item_path, "expected an identifier", source)
            )
        elif item in seen:
            diagnostics.append(Diagnostic("E112", item_path, "duplicate value", source))
        seen.add(item) if isinstance(item, str) else None


def _validate_terminal_ports(
    declaration: Mapping[str, object],
    path: str,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    if "terminal-ports" in declaration:
        _validate_identifier_array(
            declaration["terminal-ports"],
            f"{path}.terminal-ports",
            0,
            diagnostics,
            source,
        )


def _validate_local_port_references(
    items: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
    collection: str,
) -> None:
    for identifier, declaration in items.items():
        if not _is_mapping(declaration) or not _is_list(declaration.get("ports")):
            continue
        ports = declaration["ports"]
        base_path = f"{collection}.{identifier}"
        terminal_ports = declaration.get("terminal-ports", [])
        if _is_list(terminal_ports):
            for index, port in enumerate(terminal_ports):
                if _is_identifier(port) and port not in ports:
                    diagnostics.append(
                        Diagnostic(
                            "E200",
                            f"{base_path}.terminal-ports[{index}]",
                            "port reference does not resolve",
                            source,
                        )
                    )
        movements = declaration.get("movements", [])
        if _is_list(movements):
            for index, movement in enumerate(movements):
                if not _is_mapping(movement):
                    continue
                for field in ("from", "to"):
                    port = movement.get(field)
                    if _is_identifier(port) and port not in ports:
                        diagnostics.append(
                            Diagnostic(
                                "E200",
                                f"{base_path}.movements[{index}].{field}",
                                "port reference does not resolve",
                                source,
                            )
                        )


def _validate_references_array(
    value: object,
    path: str,
    count: int,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    if not _is_list(value):
        diagnostics.append(Diagnostic("E102", path, "expected an array", source))
        return
    if len(value) != count:
        diagnostics.append(
            Diagnostic("E111", path, f"expected exactly {count} values", source)
        )
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not _parse_port_reference(item):
            diagnostics.append(
                Diagnostic("E110", f"{path}[{index}]", "invalid port reference", source)
            )
        elif item in seen:
            diagnostics.append(
                Diagnostic("E112", f"{path}[{index}]", "duplicate value", source)
            )
        seen.add(item) if isinstance(item, str) else None


def _validate_movements(
    value: object,
    path: str,
    diagnostics: list[Diagnostic],
    source: Path | None,
    *,
    local: bool,
) -> None:
    if not _is_list(value):
        diagnostics.append(Diagnostic("E102", path, "expected an array", source))
        return
    if not value:
        diagnostics.append(
            Diagnostic("E111", path, "expected at least one movement", source)
        )
    seen: set[tuple[str, str]] = set()
    for index, movement in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _is_mapping(movement):
            diagnostics.append(
                Diagnostic("E102", item_path, "expected a mapping", source)
            )
            continue
        _unknown_fields(movement, {"from", "to"}, item_path, diagnostics, source)
        origin, destination = movement.get("from"), movement.get("to")
        validator = _is_identifier if local else _parse_port_reference
        for field, item in (("from", origin), ("to", destination)):
            if item is None:
                diagnostics.append(
                    Diagnostic(
                        "E101", f"{item_path}.{field}", "field is required", source
                    )
                )
            elif not validator(item):
                diagnostics.append(
                    Diagnostic(
                        "E110",
                        f"{item_path}.{field}",
                        "invalid port reference"
                        if not local
                        else "expected an identifier",
                        source,
                    )
                )
        if isinstance(origin, str) and origin == destination:
            diagnostics.append(
                Diagnostic("E113", f"{item_path}.to", "from and to must differ", source)
            )
        if isinstance(origin, str) and isinstance(destination, str):
            pair = (origin, destination)
            if pair in seen:
                diagnostics.append(
                    Diagnostic("E112", item_path, "duplicate movement", source)
                )
            seen.add(pair)


def _parse_port_reference(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 3 or parts[0] not in {"track-section", "junction"}:
        return None
    if not _is_identifier(parts[1]) or not _is_identifier(parts[2]):
        return None
    return parts[0], parts[1], parts[2]


def _validate_references(
    sections: Mapping[str, object],
    junctions: Mapping[str, object],
    devices: Mapping[str, object],
    connections: Mapping[str, object],
    passages: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    ports = _declared_ports(sections, junctions)
    incidence: dict[tuple[str, str, str], list[str]] = {}
    for identifier in sorted(connections):
        declaration = connections[identifier]
        if not _is_mapping(declaration) or not _is_list(declaration.get("ports")):
            continue
        refs = [_parse_port_reference(value) for value in declaration["ports"]]
        for index, reference in enumerate(refs):
            path = f"connections.{identifier}.ports[{index}]"
            if reference is None:
                continue
            if reference not in ports:
                diagnostics.append(
                    Diagnostic("E200", path, "port reference does not resolve", source)
                )
            else:
                incidence.setdefault(reference, []).append(path)
        if (
            len(refs) == 2
            and refs[0] is not None
            and refs[1] is not None
            and refs[0][:2] == refs[1][:2]
        ):
            diagnostics.append(
                Diagnostic(
                    "E206",
                    f"connections.{identifier}.ports",
                    "connection joins ports of the same owner",
                    source,
                )
            )
        _validate_connection_movements(
            identifier, declaration, refs, diagnostics, source
        )
    for _port, uses in sorted(incidence.items()):
        if len(uses) > 1:
            for path in uses[1:]:
                diagnostics.append(
                    Diagnostic(
                        "E205",
                        path,
                        "port participates in more than one connection",
                        source,
                    )
                )
    for owner_kind, owner_id, port_id in sorted(ports):
        declaration = (sections if owner_kind == "track-section" else junctions)[
            owner_id
        ]
        assert _is_mapping(declaration)
        terminal_value = declaration.get("terminal-ports", [])
        terminal = set(terminal_value) if _is_list(terminal_value) else set()
        connected = (owner_kind, owner_id, port_id) in incidence
        path = f"{'track-sections' if owner_kind == 'track-section' else 'junctions'}.{owner_id}.ports"
        index = (
            declaration["ports"].index(port_id)
            if _is_list(declaration.get("ports"))
            else 0
        )
        if port_id in terminal and connected:
            diagnostics.append(
                Diagnostic(
                    "E203",
                    f"{path}[{index}]",
                    "terminal port participates in a connection",
                    source,
                )
            )
        elif port_id not in terminal and not connected:
            diagnostics.append(
                Diagnostic(
                    "E204",
                    f"{path}[{index}]",
                    "nonterminal port has no connection",
                    source,
                )
            )
    _validate_passage_references(passages, junctions, devices, diagnostics, source)


def _declared_ports(
    sections: Mapping[str, object], junctions: Mapping[str, object]
) -> set[tuple[str, str, str]]:
    result: set[tuple[str, str, str]] = set()
    for kind, collection in (("track-section", sections), ("junction", junctions)):
        for identifier, declaration in collection.items():
            if _is_mapping(declaration) and _is_list(declaration.get("ports")):
                result.update(
                    (kind, identifier, port)
                    for port in declaration["ports"]
                    if _is_identifier(port)
                )
    return result


def _validate_connection_movements(
    identifier: str,
    declaration: Mapping[str, object],
    ports: list[tuple[str, str, str] | None],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    movements = declaration.get("movements")
    if not _is_list(movements) or len(ports) != 2 or None in ports:
        return
    expected = {ports[0], ports[1]}
    for index, movement in enumerate(movements):
        if not _is_mapping(movement):
            continue
        pair = {
            _parse_port_reference(movement.get("from")),
            _parse_port_reference(movement.get("to")),
        }
        if None not in pair and pair != expected:
            diagnostics.append(
                Diagnostic(
                    "E200",
                    f"connections.{identifier}.movements[{index}]",
                    "movement does not use the connection ports",
                    source,
                )
            )


def _validate_passage_references(
    passages: Mapping[str, object],
    junctions: Mapping[str, object],
    devices: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    valid: list[tuple[str, Mapping[str, object]]] = []
    for identifier in sorted(passages):
        declaration = passages[identifier]
        if not _is_mapping(declaration):
            continue
        junction = declaration.get("junction")
        if _is_identifier(junction) and junction not in junctions:
            diagnostics.append(
                Diagnostic(
                    "E200",
                    f"junction-passages.{identifier}.junction",
                    "junction reference does not resolve",
                    source,
                )
            )
            continue
        if _is_identifier(junction) and _is_mapping(junctions.get(junction)):
            ports = junctions[junction].get("ports", [])
            for field in ("from", "to"):
                port = declaration.get(field)
                if _is_identifier(port) and port not in ports:
                    diagnostics.append(
                        Diagnostic(
                            "E207",
                            f"junction-passages.{identifier}.{field}",
                            "port does not belong to the junction",
                            source,
                        )
                    )
        requirements = declaration.get("requirements", {})
        if _is_mapping(requirements):
            for device, position in requirements.items():
                path = f"junction-passages.{identifier}.requirements.{device}"
                if _is_identifier(device) and device not in devices:
                    diagnostics.append(
                        Diagnostic(
                            "E200",
                            path,
                            "control device reference does not resolve",
                            source,
                        )
                    )
                elif (
                    _is_identifier(device)
                    and _is_mapping(devices.get(device))
                    and position not in devices[device].get("positions", [])
                ):
                    diagnostics.append(
                        Diagnostic(
                            "E202",
                            path,
                            "control device position is not declared",
                            source,
                        )
                    )
        if (
            _is_identifier(junction)
            and _is_identifier(declaration.get("from"))
            and _is_identifier(declaration.get("to"))
        ):
            valid.append((identifier, declaration))
    for left_index, (left_id, left) in enumerate(valid):
        for right_id, right in valid[left_index + 1 :]:
            if (
                left["junction"] != right["junction"]
                or left["from"] != right["from"]
                or left["to"] == right["to"]
            ):
                continue
            left_requirements = left.get("requirements", {})
            right_requirements = right.get("requirements", {})
            if (
                _is_mapping(left_requirements)
                and _is_mapping(right_requirements)
                and not any(
                    left_requirements[key] != right_requirements[key]
                    for key in set(left_requirements) & set(right_requirements)
                )
            ):
                diagnostics.append(
                    Diagnostic(
                        "E300",
                        f"junction-passages.{left_id}",
                        f"passage is not mutually exclusive with '{right_id}'",
                        source,
                    )
                )


def _build_topology(data: Mapping[str, object]) -> Topology:
    sections = {
        TrackSectionId(identifier): TrackSection(
            TrackSectionId(identifier),
            tuple(PortId(port) for port in declaration["ports"]),
            tuple(
                TrackSectionMovement(PortId(movement["from"]), PortId(movement["to"]))
                for movement in declaration["movements"]
            ),
            tuple(PortId(port) for port in declaration.get("terminal-ports", [])),
        )
        for identifier, declaration in _collection(data, "track-sections").items()
        if _is_mapping(declaration)
    }
    junctions = {
        JunctionId(identifier): Junction(
            JunctionId(identifier),
            tuple(PortId(port) for port in declaration["ports"]),
            tuple(PortId(port) for port in declaration.get("terminal-ports", [])),
        )
        for identifier, declaration in _collection(data, "junctions").items()
        if _is_mapping(declaration)
    }
    devices = {
        ControlDeviceId(identifier): ControlDevice(
            ControlDeviceId(identifier),
            tuple(DevicePositionId(position) for position in declaration["positions"]),
        )
        for identifier, declaration in _collection(data, "control-devices").items()
        if _is_mapping(declaration)
    }
    connections = {
        ConnectionId(identifier): Connection(
            ConnectionId(identifier),
            tuple(_to_port_reference(port) for port in declaration["ports"]),
            tuple(
                ConnectionMovement(
                    _to_port_reference(movement["from"]),
                    _to_port_reference(movement["to"]),
                )
                for movement in declaration["movements"]
            ),
        )
        for identifier, declaration in _collection(data, "connections").items()
        if _is_mapping(declaration)
    }
    passages = {
        JunctionPassageId(identifier): JunctionPassage(
            JunctionPassageId(identifier),
            JunctionId(declaration["junction"]),
            PortId(declaration["from"]),
            PortId(declaration["to"]),
            tuple(
                DeviceRequirement(ControlDeviceId(device), DevicePositionId(position))
                for device, position in declaration.get("requirements", {}).items()
            ),
        )
        for identifier, declaration in _collection(data, "junction-passages").items()
        if _is_mapping(declaration)
    }
    return Topology(
        MappingProxyType(sections),
        MappingProxyType(junctions),
        MappingProxyType(devices),
        MappingProxyType(connections),
        MappingProxyType(passages),
    )


def _to_port_reference(value: str) -> PortReference:
    kind, owner, port = _parse_port_reference(value) or ("", "", "")
    if kind == "track-section":
        return TrackSectionPort(TrackSectionId(owner), PortId(port))
    return JunctionPort(JunctionId(owner), PortId(port))
