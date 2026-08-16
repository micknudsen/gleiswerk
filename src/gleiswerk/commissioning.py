"""Read-only, fail-closed verification of a captured hardware commissioning run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import cast

import yaml

from gleiswerk.evidence import OccupancyState
from gleiswerk.topology import (
    ControlDevicePositionEvidence,
    InstallationBinding,
    OccupancyZoneId,
    Topology,
)


class CommissioningConfigurationError(ValueError):
    """A supplied commissioning capture or expectation is unsafe to use."""


@dataclass(frozen=True, slots=True)
class CommissioningSnapshot:
    """A firmware-pinned, read-only CS3+ configuration and S88 capture."""

    topology_revision: str
    captured_at: datetime
    firmware_version: str
    command_channels: Mapping[str, str]
    feedback_channels: Mapping[str, str]
    occupancy_states: Mapping[str, OccupancyState]
    model: str = "unknown"
    endpoint: str = "unknown"
    acquisition_method: str = "unknown"
    acquisition_version: str = "unknown"
    configuration_snapshot_hash: str = "unknown"

    def __post_init__(self) -> None:
        if not self.topology_revision or not self.firmware_version:
            raise CommissioningConfigurationError(
                "capture topology revision and firmware version must be nonempty"
            )
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise CommissioningConfigurationError("capture time must be timezone-aware")
        if not all(
            value
            for value in (
                self.model,
                self.endpoint,
                self.acquisition_method,
                self.acquisition_version,
                self.configuration_snapshot_hash,
            )
        ):
            raise CommissioningConfigurationError(
                "capture provenance fields must be nonempty"
            )
        object.__setattr__(
            self, "command_channels", MappingProxyType(dict(self.command_channels))
        )
        object.__setattr__(
            self, "feedback_channels", MappingProxyType(dict(self.feedback_channels))
        )
        object.__setattr__(
            self, "occupancy_states", MappingProxyType(dict(self.occupancy_states))
        )


@dataclass(frozen=True, slots=True)
class CommissioningExpectations:
    """Operator-provided occupancy states required during a supervised test."""

    occupancy_states: Mapping[OccupancyZoneId, OccupancyState]

    def __post_init__(self) -> None:
        if not self.occupancy_states:
            raise CommissioningConfigurationError(
                "at least one occupancy expectation is required"
            )
        object.__setattr__(
            self, "occupancy_states", MappingProxyType(dict(self.occupancy_states))
        )


@dataclass(frozen=True, slots=True, order=True)
class CommissioningFailure:
    """One deterministic reason a commissioning capture cannot be accepted."""

    kind: str
    target: str
    detail: str


@dataclass(frozen=True, slots=True)
class CommissioningResult:
    """An immutable, explainable result that never controls hardware."""

    topology_revision: str
    firmware_version: str
    captured_at: datetime
    failures: tuple[CommissioningFailure, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "failures", tuple(sorted(self.failures)))

    @property
    def is_usable(self) -> bool:
        """Whether this supervised capture passed every declared check."""
        return not self.failures


def verify_commissioning(
    topology: Topology,
    binding: InstallationBinding,
    snapshot: CommissioningSnapshot,
    expectations: CommissioningExpectations,
    *,
    evaluated_at: datetime,
    maximum_age: timedelta,
) -> CommissioningResult:
    """Compare one live capture with a revision-matched installation binding.

    The caller owns collection of the firmware-specific capture.  This core
    service only compares typed logical channels and observed S88 states.
    """
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("commissioning evaluation time must be timezone-aware")
    if maximum_age < timedelta():
        raise ValueError("commissioning maximum age must not be negative")

    failures: list[CommissioningFailure] = []
    if binding.topology_revision != topology.revision:
        failures.append(
            CommissioningFailure(
                "revision-mismatch", "installation-binding", topology.revision
            )
        )
    if snapshot.topology_revision != topology.revision:
        failures.append(
            CommissioningFailure(
                "revision-mismatch", "hardware-capture", snapshot.topology_revision
            )
        )
    if snapshot.captured_at < evaluated_at - maximum_age:
        failures.append(
            CommissioningFailure(
                "stale-capture", "hardware-capture", snapshot.captured_at.isoformat()
            )
        )

    for device_id, device in sorted(binding.control_devices.items()):
        actual = snapshot.command_channels.get(str(device_id))
        if actual != device.command_channel:
            failures.append(
                CommissioningFailure(
                    "command-channel-mismatch",
                    str(device_id),
                    f"expected {device.command_channel!r}, captured {actual!r}",
                )
            )
        if device.position_evidence is ControlDevicePositionEvidence.SENSOR:
            actual_feedback = snapshot.feedback_channels.get(str(device_id))
            if actual_feedback != device.feedback_channel:
                failures.append(
                    CommissioningFailure(
                        "feedback-channel-mismatch",
                        str(device_id),
                        f"expected {device.feedback_channel!r}, captured {actual_feedback!r}",
                    )
                )

    for zone_id, expected in sorted(expectations.occupancy_states.items()):
        channel = binding.occupancy_feedback.get(zone_id)
        if channel is None:
            failures.append(
                CommissioningFailure(
                    "unknown-occupancy-zone",
                    str(zone_id),
                    "not in installation binding",
                )
            )
            continue
        actual_channel = snapshot.feedback_channels.get(str(zone_id))
        if actual_channel != channel:
            failures.append(
                CommissioningFailure(
                    "feedback-channel-mismatch",
                    str(zone_id),
                    f"expected {channel!r}, captured {actual_channel!r}",
                )
            )
            continue
        actual_state = snapshot.occupancy_states.get(channel)
        if actual_state is None:
            failures.append(
                CommissioningFailure("missing-occupancy-state", str(zone_id), channel)
            )
        elif actual_state is not expected:
            failures.append(
                CommissioningFailure(
                    "occupancy-state-mismatch",
                    str(zone_id),
                    f"expected {expected.value}, captured {actual_state.value}",
                )
            )
    return CommissioningResult(
        topology.revision,
        snapshot.firmware_version,
        snapshot.captured_at,
        tuple(failures),
    )


def load_commissioning_snapshot(path: Path) -> CommissioningSnapshot:
    """Load a complete, read-only controller capture from YAML."""
    data = _load_mapping(path, "hardware capture")
    _exact_keys(
        data,
        {
            "topology-revision",
            "captured-at",
            "firmware-version",
            "command-channels",
            "feedback-channels",
            "occupancy-states",
            "model",
            "endpoint",
            "acquisition-method",
            "acquisition-version",
            "configuration-snapshot-hash",
        },
        "hardware capture",
    )
    return CommissioningSnapshot(
        _string(data, "topology-revision", "hardware capture"),
        _datetime(data, "captured-at", "hardware capture"),
        _string(data, "firmware-version", "hardware capture"),
        _string_mapping(data, "command-channels", "hardware capture"),
        _string_mapping(data, "feedback-channels", "hardware capture"),
        {
            channel: _occupancy(value, f"occupancy-states.{channel}")
            for channel, value in _string_mapping(
                data, "occupancy-states", "hardware capture"
            ).items()
        },
        _string(data, "model", "hardware capture"),
        _string(data, "endpoint", "hardware capture"),
        _string(data, "acquisition-method", "hardware capture"),
        _string(data, "acquisition-version", "hardware capture"),
        _string(data, "configuration-snapshot-hash", "hardware capture"),
    )


def load_commissioning_expectations(path: Path) -> CommissioningExpectations:
    """Load the states an operator expects while conducting an S88 smoke test."""
    data = _load_mapping(path, "commissioning expectations")
    _exact_keys(data, {"occupancy-zones"}, "commissioning expectations")
    return CommissioningExpectations(
        {
            OccupancyZoneId(zone): _occupancy(value, f"occupancy-zones.{zone}")
            for zone, value in _string_mapping(
                data, "occupancy-zones", "commissioning expectations"
            ).items()
        }
    )


def _load_mapping(path: Path, description: str) -> Mapping[str, object]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise CommissioningConfigurationError(
            f"invalid {description}: {error}"
        ) from error
    if not isinstance(data, dict):
        raise CommissioningConfigurationError(f"{description} must be a YAML mapping")
    mapping = cast(Mapping[object, object], data)
    if not all(isinstance(key, str) for key in mapping):
        raise CommissioningConfigurationError(f"{description} must be a YAML mapping")
    return {cast(str, key): value for key, value in mapping.items()}


def _exact_keys(
    data: Mapping[str, object], expected: set[str], description: str
) -> None:
    if set(data) != expected:
        raise CommissioningConfigurationError(
            f"{description} must contain exactly: {', '.join(sorted(expected))}"
        )


def _string(data: Mapping[str, object], field: str, description: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise CommissioningConfigurationError(
            f"{description}.{field} must be a nonempty string"
        )
    return value


def _datetime(data: Mapping[str, object], field: str, description: str) -> datetime:
    value = _string(data, field, description)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CommissioningConfigurationError(
            f"{description}.{field} must be ISO-8601"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CommissioningConfigurationError(
            f"{description}.{field} must include a timezone"
        )
    return parsed.astimezone(UTC)


def _string_mapping(
    data: Mapping[str, object], field: str, description: str
) -> Mapping[str, str]:
    value = data.get(field)
    if not isinstance(value, dict):
        raise CommissioningConfigurationError(
            f"{description}.{field} must be a nonempty string mapping"
        )
    mapping = cast(Mapping[object, object], value)
    if not mapping or not all(
        isinstance(key, str) and isinstance(item, str) and item
        for key, item in mapping.items()
    ):
        raise CommissioningConfigurationError(
            f"{description}.{field} must be a nonempty string mapping"
        )
    return {cast(str, key): cast(str, item) for key, item in mapping.items()}


def _occupancy(value: str, path: str) -> OccupancyState:
    try:
        return OccupancyState(value)
    except ValueError as error:
        raise CommissioningConfigurationError(
            f"{path} must be clear or occupied"
        ) from error
