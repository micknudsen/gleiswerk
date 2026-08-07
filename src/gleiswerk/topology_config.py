# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportMissingModuleSource=false, reportOperatorIssue=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Strict schema-version 3 core-topology loading and validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
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
    JunctionResource,
    OccupancyCoverage,
    OccupancyExtent,
    OccupancyZone,
    OccupancyZoneId,
    PortId,
    PortReference,
    ProtectionRule,
    ProtectionZone,
    ProtectionZoneId,
    Topology,
    TrackSection,
    TrackSectionId,
    TrackSectionMovement,
    TrackSectionPort,
    TrackSectionResource,
)

_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_TOP_LEVEL_FIELDS = {
    "schema-version",
    "track-sections",
    "junctions",
    "control-devices",
    "connections",
    "junction-passages",
    "occupancy-zones",
    "protection-zones",
    "protection-rules",
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
    return _build_topology(data, f"sha256:{sha256(text.encode('utf-8')).hexdigest()}")


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
    occupancy_zones = _collection(data, "occupancy-zones")
    protection_zones = _collection(data, "protection-zones")
    protection_rules = _collection(data, "protection-rules")
    _validate_sections(sections, diagnostics, source)
    _validate_junctions(junctions, diagnostics, source)
    _validate_devices(devices, diagnostics, source)
    _validate_connections(connections, diagnostics, source)
    _validate_passages(passages, diagnostics, source)
    _validate_occupancy_zones(occupancy_zones, diagnostics, source)
    _validate_protection_zones(protection_zones, diagnostics, source)
    _validate_protection_rules(protection_rules, diagnostics, source)
    _validate_local_port_references(sections, diagnostics, source, "track-sections")
    _validate_local_port_references(junctions, diagnostics, source, "junctions")
    _validate_references(
        sections,
        junctions,
        devices,
        connections,
        passages,
        occupancy_zones,
        protection_zones,
        protection_rules,
        diagnostics,
        source,
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


def _validate_occupancy_zones(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"occupancy-zones.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid occupancy zone ID", source)
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(declaration, {"coverage"}, path, diagnostics, source)
        coverage = declaration.get("coverage")
        if not _is_list(coverage):
            diagnostics.append(
                Diagnostic("E102", f"{path}.coverage", "expected an array", source)
            )
            continue
        if not coverage:
            diagnostics.append(
                Diagnostic(
                    "E111", f"{path}.coverage", "expected at least one value", source
                )
            )
        for index, item in enumerate(coverage):
            item_path = f"{path}.coverage[{index}]"
            if not _is_mapping(item):
                diagnostics.append(
                    Diagnostic("E102", item_path, "expected a mapping", source)
                )
                continue
            _unknown_fields(
                item, {"resource", "extent"}, item_path, diagnostics, source
            )
            if "resource" not in item:
                diagnostics.append(
                    Diagnostic(
                        "E101", f"{item_path}.resource", "field is required", source
                    )
                )
            elif _parse_physical_resource_reference(item["resource"]) is None:
                diagnostics.append(
                    Diagnostic(
                        "E110",
                        f"{item_path}.resource",
                        "invalid physical resource reference",
                        source,
                    )
                )
            if "extent" not in item:
                diagnostics.append(
                    Diagnostic(
                        "E101", f"{item_path}.extent", "field is required", source
                    )
                )
            elif item["extent"] not in {"complete", "partial"}:
                diagnostics.append(
                    Diagnostic(
                        "E114",
                        f"{item_path}.extent",
                        "expected 'complete' or 'partial'",
                        source,
                    )
                )


def _validate_protection_zones(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"protection-zones.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid protection zone ID", source)
            )
        elif not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
        elif declaration:
            _unknown_fields(declaration, set(), path, diagnostics, source)


def _validate_protection_rules(
    items: Mapping[str, object], diagnostics: list[Diagnostic], source: Path | None
) -> None:
    for identifier in sorted(items):
        path = f"protection-rules.{identifier}"
        declaration = items[identifier]
        if not _is_identifier(identifier):
            diagnostics.append(
                Diagnostic("E110", path, "invalid protection rule ID", source)
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        _unknown_fields(
            declaration,
            {"trigger", "claims", "requirements"},
            path,
            diagnostics,
            source,
        )
        trigger = declaration.get("trigger")
        if not _is_mapping(trigger):
            diagnostics.append(
                Diagnostic("E102", f"{path}.trigger", "expected a mapping", source)
            )
        elif trigger.get("kind") not in {
            "track-section",
            "connection",
            "junction-passage",
        }:
            diagnostics.append(
                Diagnostic(
                    "E114",
                    f"{path}.trigger.kind",
                    "unsupported protection trigger kind",
                    source,
                )
            )
        claims = declaration.get("claims", [])
        requirements = declaration.get("requirements", {})
        if not _is_list(claims):
            diagnostics.append(
                Diagnostic("E102", f"{path}.claims", "expected an array", source)
            )
        else:
            for index, claim in enumerate(claims):
                if _parse_protection_zone_reference(claim) is None:
                    diagnostics.append(
                        Diagnostic(
                            "E110",
                            f"{path}.claims[{index}]",
                            "invalid protection zone reference",
                            source,
                        )
                    )
        if not _is_mapping(requirements):
            diagnostics.append(
                Diagnostic("E102", f"{path}.requirements", "expected a mapping", source)
            )
        else:
            for device, position in sorted(requirements.items()):
                if not _is_identifier(device) or not _is_identifier(position):
                    diagnostics.append(
                        Diagnostic(
                            "E110",
                            f"{path}.requirements.{device}",
                            "expected identifier references",
                            source,
                        )
                    )
        if not claims and not requirements:
            diagnostics.append(
                Diagnostic("E301", path, "protection rule has no contribution", source)
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


def _parse_physical_resource_reference(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 2 or parts[0] not in {"track-section", "junction"}:
        return None
    if not _is_identifier(parts[1]):
        return None
    return parts[0], parts[1]


def _parse_protection_zone_reference(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 2 or parts[0] != "protection-zone" or not _is_identifier(parts[1]):
        return None
    return parts[1]


def _validate_references(
    sections: Mapping[str, object],
    junctions: Mapping[str, object],
    devices: Mapping[str, object],
    connections: Mapping[str, object],
    passages: Mapping[str, object],
    occupancy_zones: Mapping[str, object],
    protection_zones: Mapping[str, object],
    protection_rules: Mapping[str, object],
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
    _validate_occupancy_references(
        occupancy_zones, sections, junctions, diagnostics, source
    )
    _validate_protection_rule_references(
        protection_rules,
        sections,
        connections,
        passages,
        devices,
        protection_zones,
        diagnostics,
        source,
    )


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


def _validate_occupancy_references(
    zones: Mapping[str, object],
    sections: Mapping[str, object],
    junctions: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    for zone_id in sorted(zones):
        declaration = zones[zone_id]
        if not _is_mapping(declaration) or not _is_list(declaration.get("coverage")):
            continue
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(declaration["coverage"]):
            if not _is_mapping(item):
                continue
            reference = _parse_physical_resource_reference(item.get("resource"))
            path = f"occupancy-zones.{zone_id}.coverage[{index}].resource"
            if reference is None:
                continue
            collection = sections if reference[0] == "track-section" else junctions
            if reference[1] not in collection:
                diagnostics.append(
                    Diagnostic(
                        "E200", path, "resource reference does not resolve", source
                    )
                )
            elif reference in seen:
                diagnostics.append(
                    Diagnostic(
                        "E208",
                        path,
                        "occupancy coverage repeats one resource in a zone",
                        source,
                    )
                )
            seen.add(reference)


def _validate_protection_rule_references(
    rules: Mapping[str, object],
    sections: Mapping[str, object],
    connections: Mapping[str, object],
    passages: Mapping[str, object],
    devices: Mapping[str, object],
    protection_zones: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    for rule_id in sorted(rules):
        declaration = rules[rule_id]
        if not _is_mapping(declaration):
            continue
        base_path = f"protection-rules.{rule_id}"
        claims = declaration.get("claims", [])
        if _is_list(claims):
            seen_claims: set[str] = set()
            for index, claim in enumerate(claims):
                claim_id = _parse_protection_zone_reference(claim)
                path = f"{base_path}.claims[{index}]"
                if claim_id is None:
                    continue
                if claim_id not in protection_zones:
                    diagnostics.append(
                        Diagnostic(
                            "E200",
                            path,
                            "protection zone reference does not resolve",
                            source,
                        )
                    )
                elif claim_id in seen_claims:
                    diagnostics.append(
                        Diagnostic("E112", path, "duplicate value", source)
                    )
                seen_claims.add(claim_id)
        requirements = declaration.get("requirements", {})
        if _is_mapping(requirements):
            for device, position in requirements.items():
                path = f"{base_path}.requirements.{device}"
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
        trigger = declaration.get("trigger")
        if not _is_mapping(trigger):
            continue
        kind = trigger.get("kind")
        target_id = trigger.get("id")
        if kind == "track-section":
            _validate_rule_movement_trigger(
                base_path, trigger, sections, diagnostics, source
            )
        elif kind == "connection":
            _validate_rule_movement_trigger(
                base_path, trigger, connections, diagnostics, source
            )
        elif kind == "junction-passage" and (
            _is_identifier(target_id) and target_id not in passages
        ):
            diagnostics.append(
                Diagnostic(
                    "E200",
                    f"{base_path}.trigger.id",
                    "junction passage reference does not resolve",
                    source,
                )
            )


def _validate_rule_movement_trigger(
    base_path: str,
    trigger: Mapping[str, object],
    collection: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    target_id = trigger.get("id")
    if not _is_identifier(target_id) or target_id not in collection:
        diagnostics.append(
            Diagnostic(
                "E200",
                f"{base_path}.trigger.id",
                "trigger reference does not resolve",
                source,
            )
        )
        return
    declaration = collection[target_id]
    if not _is_mapping(declaration):
        return
    movement = {"from": trigger.get("from"), "to": trigger.get("to")}
    if movement not in declaration.get("movements", []):
        diagnostics.append(
            Diagnostic(
                "E200",
                f"{base_path}.trigger",
                "trigger movement does not resolve",
                source,
            )
        )


def _build_topology(data: Mapping[str, object], revision: str) -> Topology:
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
    occupancy_zones = {
        OccupancyZoneId(identifier): OccupancyZone(
            OccupancyZoneId(identifier),
            tuple(
                OccupancyCoverage(
                    _to_physical_resource(item["resource"]),
                    OccupancyExtent(item["extent"]),
                )
                for item in declaration["coverage"]
            ),
        )
        for identifier, declaration in _collection(data, "occupancy-zones").items()
        if _is_mapping(declaration)
    }
    protection_zones = {
        ProtectionZoneId(identifier): ProtectionZone(ProtectionZoneId(identifier))
        for identifier, declaration in _collection(data, "protection-zones").items()
        if _is_mapping(declaration)
    }
    protection_rules = {
        identifier: ProtectionRule(
            identifier,
            MappingProxyType(cast(dict[str, str], declaration["trigger"])),
            tuple(
                ProtectionZoneId(_parse_protection_zone_reference(claim) or "")
                for claim in declaration.get("claims", [])
            ),
            tuple(
                DeviceRequirement(ControlDeviceId(device), DevicePositionId(position))
                for device, position in declaration.get("requirements", {}).items()
            ),
        )
        for identifier, declaration in _collection(data, "protection-rules").items()
        if _is_mapping(declaration)
    }
    return Topology(
        MappingProxyType(sections),
        MappingProxyType(junctions),
        MappingProxyType(devices),
        MappingProxyType(connections),
        MappingProxyType(passages),
        MappingProxyType(occupancy_zones),
        MappingProxyType(protection_zones),
        MappingProxyType(protection_rules),
        revision,
    )


def _to_port_reference(value: str) -> PortReference:
    kind, owner, port = _parse_port_reference(value) or ("", "", "")
    if kind == "track-section":
        return TrackSectionPort(TrackSectionId(owner), PortId(port))
    return JunctionPort(JunctionId(owner), PortId(port))


def _to_physical_resource(value: str) -> TrackSectionResource | JunctionResource:
    kind, identifier = _parse_physical_resource_reference(value) or ("", "")
    if kind == "track-section":
        return TrackSectionResource(TrackSectionId(identifier))
    return JunctionResource(JunctionId(identifier))
