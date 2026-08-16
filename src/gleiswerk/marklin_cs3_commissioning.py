"""Firmware-pinned, read-only CS3+ commissioning capture adapter.

This module is an infrastructure boundary.  It deliberately translates the
CS3 WebApp's undocumented JSON into the typed capture consumed by the safety
core; no CS3 protocol names leave this module.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from types import MappingProxyType
from typing import cast
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from gleiswerk.commissioning import CommissioningSnapshot
from gleiswerk.evidence import OccupancyState
from gleiswerk.topology import ControlDevicePositionEvidence, InstallationBinding

_SUPPORTED_MODEL = "60216"
_ACQUISITION_METHOD = "marklin-cs3-webapp-json"
_ACQUISITION_VERSION = "1"
_PATHS = ("devs", "mags", "mags/state")


class Cs3CommissioningError(ValueError):
    """The CS3+ capture is incomplete, unsupported, or unsafe to use."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


@dataclass(frozen=True, slots=True)
class MarklinCs3CommissioningAdapter:
    """Read a characterized CS3+ WebApp interface without controlling it."""

    endpoint: str
    expected_firmware_version: str
    timeout_seconds: float = 5.0
    fetcher: Callable[[str], object] | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise Cs3CommissioningError("CS3 endpoint must be a plain http origin")
        if not self.expected_firmware_version:
            raise Cs3CommissioningError("expected firmware version must be nonempty")
        if self.timeout_seconds <= 0:
            raise Cs3CommissioningError("CS3 timeout must be positive")

    def acquire(
        self,
        topology_revision: str,
        binding: InstallationBinding,
        *,
        captured_at: datetime | None = None,
    ) -> CommissioningSnapshot:
        """Return one complete capture or fail closed without sending commands."""
        when = captured_at or datetime.now(UTC)
        if when.tzinfo is None or when.utcoffset() is None:
            raise Cs3CommissioningError("capture time must be timezone-aware")
        responses = {path: self._get(path) for path in _PATHS}
        firmware = _firmware(responses["devs"])
        if firmware != self.expected_firmware_version:
            raise Cs3CommissioningError(
                f"unsupported CS3 firmware {firmware!r}; expected "
                f"{self.expected_firmware_version!r}"
            )
        command_addresses = _command_addresses(responses["mags"])
        contacts = _contacts(responses["mags"])
        states = _states(responses["mags/state"])
        command_channels = self.read_configured_command_channels(
            binding, command_addresses
        )
        feedback_channels, occupancy_states = _feedback_capture(
            binding, contacts, states
        )
        source = _canonical_json({"devs": responses["devs"], "mags": responses["mags"]})
        return CommissioningSnapshot(
            topology_revision,
            when.astimezone(UTC),
            firmware,
            command_channels,
            feedback_channels,
            occupancy_states,
            model="marklin-cs3-plus-60216",
            endpoint=self.endpoint,
            acquisition_method=_ACQUISITION_METHOD,
            acquisition_version=_ACQUISITION_VERSION,
            configuration_snapshot_hash=f"sha256:{sha256(source).hexdigest()}",
        )

    def read_configured_command_channels(
        self, binding: InstallationBinding, command_addresses: frozenset[int]
    ) -> Mapping[str, str]:
        """Match required logical command channels to configured CS3 addresses."""
        captured: dict[str, str] = {}
        for device_id, device in binding.control_devices.items():
            address = _dcc_address(device.command_channel)
            if address not in command_addresses:
                raise Cs3CommissioningError(
                    f"configured command channel is missing: {device.command_channel!r}"
                )
            captured[str(device_id)] = device.command_channel
        return MappingProxyType(captured)

    def command_and_confirm_acceptance(self, *args: object, **kwargs: object) -> None:
        """Remain intentionally unavailable until a separately characterized issue."""
        raise NotImplementedError("live CS3 command acceptance is not implemented")

    def _get(self, path: str) -> object:
        if self.fetcher is not None:
            try:
                return self.fetcher(path)
            except (KeyError, OSError, TimeoutError) as error:
                raise Cs3CommissioningError(
                    f"unable to read CS3 {path}: {error}"
                ) from error
        request = Request(f"{self.endpoint}/app/api/{path}", method="GET")
        try:
            with build_opener(_RejectRedirects()).open(
                request, timeout=self.timeout_seconds
            ) as response:
                if response.status != 200:
                    raise Cs3CommissioningError(
                        f"CS3 {path} returned HTTP {response.status}"
                    )
                return json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, URLError) as error:
            raise Cs3CommissioningError(
                f"unable to read CS3 {path}: {error}"
            ) from error


def _firmware(value: object) -> str:
    devices = _list_of_mappings(value, "devs")
    system = next(
        (
            item
            for item in devices
            if item.get("typ") == "65504" and isinstance(item.get("csDeviceInfo"), str)
        ),
        None,
    )
    controller = next(
        (item for item in devices if item.get("artikelnr") == _SUPPORTED_MODEL), None
    )
    if system is None or controller is None:
        raise Cs3CommissioningError("expected one CS3+ 60216 system device")
    decoded = _decode_cs_text(cast(str, system["csDeviceInfo"]))
    fields = dict(part.split("=", 1) for part in decoded.split(";") if "=" in part)
    firmware = fields.get("softwareVersion")
    if not firmware:
        raise Cs3CommissioningError("CS3 system data has no software version")
    return firmware


def _command_addresses(value: object) -> frozenset[int]:
    commands = [
        item
        for item in _list_of_mappings(value, "mags")
        if item.get("prot") == "dcc" and item.get("typ") != "decoder_m"
    ]
    addresses: list[int] = []
    for command in commands:
        address = command.get("address")
        if type(address) is not int or address < 1:
            raise Cs3CommissioningError(
                "CS3 accessory mapping has unsupported address shape"
            )
        addresses.append(address)
    if not addresses:
        raise Cs3CommissioningError(
            "CS3 accessory mapping has unsupported address shape"
        )
    duplicates = sorted(
        address for address, count in Counter(addresses).items() if count != 1
    )
    if duplicates:
        raise Cs3CommissioningError(f"CS3 accessory mapping is ambiguous: {duplicates}")
    return frozenset(addresses)


def _contacts(value: object) -> Mapping[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    for item in _list_of_mappings(value, "mags"):
        if item.get("typ") != "s88kontaktgleis":
            continue
        bus, contact = item.get("s88kennung"), item.get("s88kontakt")
        if type(bus) is not int or type(contact) is not int or bus < 1 or contact < 1:
            raise Cs3CommissioningError("CS3 S88 mapping has unsupported address shape")
        identifier = item.get("id")
        if type(identifier) is not int or (bus, contact) in result:
            raise Cs3CommissioningError("CS3 S88 mapping is incomplete or ambiguous")
        result[(bus, contact)] = identifier
    if not result:
        raise Cs3CommissioningError("CS3 has no configured S88 contacts")
    return MappingProxyType(result)


def _states(value: object) -> Mapping[int, OccupancyState]:
    result: dict[int, OccupancyState] = {}
    if not isinstance(value, list):
        raise Cs3CommissioningError("CS3 S88 state must be a list")
    entries = cast(list[object], value)
    for entry in entries:
        if not isinstance(entry, list):
            raise Cs3CommissioningError("CS3 S88 state entry is malformed")
        pair = cast(list[object], entry)
        if len(pair) != 2:
            raise Cs3CommissioningError("CS3 S88 state entry is malformed")
        identifier, state = pair
        if isinstance(identifier, str) and identifier.isdigit():
            identifier = int(identifier)
        if type(identifier) is not int or not isinstance(state, dict):
            raise Cs3CommissioningError("CS3 S88 state entry is malformed")
        state_mapping = cast(Mapping[str, object], state)
        raw = state_mapping.get("state")
        if raw not in ("0", "1"):
            continue
        result[identifier] = (
            OccupancyState.OCCUPIED if raw == "1" else OccupancyState.CLEAR
        )
    return MappingProxyType(result)


def _feedback_capture(
    binding: InstallationBinding,
    contacts: Mapping[tuple[int, int], int],
    states: Mapping[int, OccupancyState],
) -> tuple[Mapping[str, str], Mapping[str, OccupancyState]]:
    feedback: dict[str, str] = {}
    occupancy: dict[str, OccupancyState] = {}
    channels: dict[str, str] = {
        str(zone): channel for zone, channel in binding.occupancy_feedback.items()
    }
    for device_id, device in binding.control_devices.items():
        if (
            device.position_evidence is ControlDevicePositionEvidence.SENSOR
            and device.feedback_channel is not None
        ):
            channels[str(device_id)] = device.feedback_channel
    for target, channel in channels.items():
        bus, contact = _s88_address(channel)
        identifier = contacts.get((bus, contact))
        if identifier is None or identifier not in states:
            raise Cs3CommissioningError(f"missing current S88 state for {channel!r}")
        feedback[target] = channel
        occupancy[channel] = states[identifier]
    return MappingProxyType(feedback), MappingProxyType(occupancy)


def _dcc_address(channel: str) -> int:
    prefix = "dcc-accessory-"
    if not channel.startswith(prefix) or not channel[len(prefix) :].isdigit():
        raise Cs3CommissioningError(
            f"unsupported CS3 command channel {channel!r}; expected dcc-accessory-N"
        )
    address = int(channel[len(prefix) :])
    if address < 1:
        raise Cs3CommissioningError("CS3 accessory address must be positive")
    return address


def _s88_address(channel: str) -> tuple[int, int]:
    parts = channel.split("-")
    if (
        len(parts) != 4
        or parts[0] != "s88"
        or not all(part.isdigit() for part in parts[1:])
    ):
        raise Cs3CommissioningError(
            f"unsupported CS3 feedback channel {channel!r}; expected s88-B-M-C"
        )
    bus, module, contact = (int(part) for part in parts[1:])
    if bus < 1 or module < 1 or not 1 <= contact <= 16:
        raise Cs3CommissioningError("CS3 S88 channel is out of range")
    return bus, (module - 1) * 16 + contact


def _decode_cs_text(value: str) -> str:
    return re.sub(
        r"#([0-9A-Fa-f]{2})", lambda match: chr(int(match.group(1), 16)), value
    )


def _list_of_mappings(value: object, name: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list):
        raise Cs3CommissioningError(f"CS3 {name} response is malformed")
    entries = cast(list[object], value)
    if not all(isinstance(item, dict) for item in entries):
        raise Cs3CommissioningError(f"CS3 {name} response is malformed")
    return [cast(Mapping[str, object], item) for item in entries]


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
