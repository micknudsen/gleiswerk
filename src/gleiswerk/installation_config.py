# pyright: reportPrivateUsage=false, reportMissingModuleSource=false
"""Strict loading and validation for revision-matched Installation Bindings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import cast

import yaml

from gleiswerk.topology import (
    ControlDeviceBinding,
    ControlDeviceId,
    InstallationBinding,
    OccupancyZoneId,
    Topology,
)
from gleiswerk.topology_config import (
    Diagnostic,
    TopologyConfigurationError,
    _is_mapping,
    _reject_yaml_anchors_and_aliases,
    _StrictYamlLoader,
)

_TOP_LEVEL_FIELDS = {"topology-revision", "control-devices", "occupancy-zones"}


def load_installation_binding(path: Path, topology: Topology) -> InstallationBinding:
    """Load a complete Installation Binding for exactly one topology revision."""
    source = Path(path)
    if source.suffix != ".yaml":
        raise TopologyConfigurationError(
            (Diagnostic("E001", None, "expected a file with a .yaml suffix", source),)
        )
    try:
        text = source.read_text(encoding="utf-8")
        _reject_yaml_anchors_and_aliases(text)
        data = yaml.load(text, Loader=_StrictYamlLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise TopologyConfigurationError(
            (Diagnostic("E005", None, f"invalid YAML: {error}", source),)
        ) from error
    diagnostics = validate_installation_binding_data(data, topology, source=source)
    if diagnostics:
        raise TopologyConfigurationError(diagnostics)
    assert _is_mapping(data)
    return _build_binding(data)


def validate_installation_binding_data(
    data: object, topology: Topology, *, source: Path | None = None
) -> tuple[Diagnostic, ...]:
    """Return deterministic binding diagnostics without changing controller state."""
    if not _is_mapping(data):
        return (Diagnostic("E100", None, "expected a YAML mapping", source),)
    diagnostics: list[Diagnostic] = []
    for field in sorted(set(data) - _TOP_LEVEL_FIELDS):
        diagnostics.append(Diagnostic("E104", field, "unknown top-level field", source))
    revision = data.get("topology-revision")
    if not isinstance(revision, str):
        diagnostics.append(
            Diagnostic("E101", "topology-revision", "field is required", source)
        )
    elif revision != topology.revision:
        diagnostics.append(
            Diagnostic(
                "E209", "topology-revision", "topology revision does not match", source
            )
        )
    devices = _collection(data, "control-devices", diagnostics, source)
    occupancy = _collection(data, "occupancy-zones", diagnostics, source)
    _validate_device_bindings(devices, topology, diagnostics, source)
    _validate_occupancy_bindings(occupancy, topology, diagnostics, source)
    _validate_channel_uniqueness(devices, occupancy, diagnostics, source)
    return tuple(diagnostics)


def _collection(
    data: Mapping[str, object],
    name: str,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> Mapping[str, object]:
    value = data.get(name)
    if not _is_mapping(value):
        diagnostics.append(Diagnostic("E102", name, "expected a mapping", source))
        return {}
    return value


def _validate_device_bindings(
    bindings: Mapping[str, object],
    topology: Topology,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    expected = set(topology.control_devices)
    for identifier in sorted(bindings):
        path = f"control-devices.{identifier}"
        declaration = bindings[identifier]
        if identifier not in expected:
            diagnostics.append(
                Diagnostic(
                    "E200", path, "control device reference does not resolve", source
                )
            )
            continue
        if not _is_mapping(declaration):
            diagnostics.append(Diagnostic("E102", path, "expected a mapping", source))
            continue
        for field in sorted(set(declaration) - {"command-channel", "feedback-channel"}):
            diagnostics.append(
                Diagnostic(
                    "E106", f"{path}.{field}", "unknown declaration field", source
                )
            )
        command, feedback = (
            declaration.get("command-channel"),
            declaration.get("feedback-channel"),
        )
        for field, value in (("command-channel", command),):
            field_path = f"{path}.{field}"
            if not isinstance(value, str) or not value:
                diagnostics.append(
                    Diagnostic(
                        "E101", field_path, "nonempty string is required", source
                    )
                )
        if "feedback-channel" in declaration and (
            not isinstance(feedback, str) or not feedback
        ):
            diagnostics.append(
                Diagnostic(
                    "E101",
                    f"{path}.feedback-channel",
                    "nonempty string is required when declared",
                    source,
                )
            )
        if isinstance(command, str) and command and command == feedback:
            diagnostics.append(
                Diagnostic(
                    "E210",
                    f"{path}.feedback-channel",
                    "command and feedback channels must be independent",
                    source,
                )
            )
    for identifier in sorted(expected - set(bindings)):
        diagnostics.append(
            Diagnostic(
                "E111", f"control-devices.{identifier}", "binding is required", source
            )
        )


def _validate_occupancy_bindings(
    bindings: Mapping[str, object],
    topology: Topology,
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    expected = set(topology.occupancy_zones)
    for identifier in sorted(bindings):
        path = f"occupancy-zones.{identifier}"
        declaration = bindings[identifier]
        if identifier not in expected:
            diagnostics.append(
                Diagnostic(
                    "E200", path, "occupancy zone reference does not resolve", source
                )
            )
        elif not isinstance(declaration, str) or not declaration:
            diagnostics.append(
                Diagnostic(
                    "E101", path, "nonempty feedback channel is required", source
                )
            )
    for identifier in sorted(expected - set(bindings)):
        diagnostics.append(
            Diagnostic(
                "E111", f"occupancy-zones.{identifier}", "binding is required", source
            )
        )


def _validate_channel_uniqueness(
    devices: Mapping[str, object],
    occupancy: Mapping[str, object],
    diagnostics: list[Diagnostic],
    source: Path | None,
) -> None:
    channels: dict[str, str] = {}
    for collection, bindings in (
        ("control-devices", devices),
        ("occupancy-zones", occupancy),
    ):
        for identifier in sorted(bindings):
            declaration = bindings[identifier]
            values = (
                (
                    ("command-channel", declaration.get("command-channel")),
                    ("feedback-channel", declaration.get("feedback-channel")),
                )
                if _is_mapping(declaration)
                else (("feedback-channel", declaration),)
            )
            for field, channel in values:
                if not isinstance(channel, str) or not channel:
                    continue
                path = (
                    f"{collection}.{identifier}.{field}"
                    if collection == "control-devices"
                    else f"{collection}.{identifier}"
                )
                if channel in channels:
                    diagnostics.append(
                        Diagnostic(
                            "E211",
                            path,
                            f"channel is already bound at {channels[channel]}",
                            source,
                        )
                    )
                else:
                    channels[channel] = path


def _build_binding(data: Mapping[str, object]) -> InstallationBinding:
    devices = cast(Mapping[str, Mapping[str, str]], data["control-devices"])
    occupancy = cast(Mapping[str, str], data["occupancy-zones"])
    return InstallationBinding(
        cast(str, data["topology-revision"]),
        MappingProxyType(
            {
                ControlDeviceId(key): ControlDeviceBinding(
                    value["command-channel"], value.get("feedback-channel")
                )
                for key, value in devices.items()
            }
        ),
        MappingProxyType(
            {OccupancyZoneId(key): value for key, value in occupancy.items()}
        ),
    )
