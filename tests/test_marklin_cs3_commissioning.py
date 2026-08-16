# pyright: reportMissingImports=false, reportUnknownMemberType=false
"""Characterization tests for the read-only CS3+ commissioning adapter."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gleiswerk.marklin_cs3_commissioning import (
    Cs3CommissioningError,
    MarklinCs3CommissioningAdapter,
)
from gleiswerk.topology import (
    ControlDeviceBinding,
    ControlDeviceId,
    ControlDevicePositionEvidence,
    InstallationBinding,
    OccupancyZoneId,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cs3_webapp_2_6_1.json"
NOW = datetime(2026, 8, 16, 12, tzinfo=UTC)


def binding() -> InstallationBinding:
    return InstallationBinding(
        "sha256:test",
        {
            ControlDeviceId("turnout"): ControlDeviceBinding(
                "dcc-accessory-12", ControlDevicePositionEvidence.UNKNOWN
            )
        },
        {OccupancyZoneId("detector"): "s88-1-1-1"},
    )


def adapter(
    responses: dict[str, object] | None = None,
) -> MarklinCs3CommissioningAdapter:
    capture = responses or json.loads(FIXTURE.read_text(encoding="utf-8"))
    return MarklinCs3CommissioningAdapter(
        "http://192.0.2.17",
        "2.6.1 (Build 3)",
        fetcher=capture.__getitem__,
    )


def test_acquires_complete_firmware_pinned_capture() -> None:
    snapshot = adapter().acquire("sha256:test", binding(), captured_at=NOW)

    assert snapshot.model == "marklin-cs3-plus-60216"
    assert snapshot.endpoint == "http://192.0.2.17"
    assert snapshot.command_channels == {"turnout": "dcc-accessory-12"}
    assert snapshot.feedback_channels == {"detector": "s88-1-1-1"}
    assert snapshot.occupancy_states["s88-1-1-1"].value == "clear"
    assert snapshot.configuration_snapshot_hash.startswith("sha256:")


def test_fails_closed_for_missing_system_device() -> None:
    responses = json.loads(FIXTURE.read_text(encoding="utf-8"))
    responses["devs"].pop()

    with pytest.raises(Cs3CommissioningError, match="expected one CS3"):
        adapter(responses).acquire("sha256:test", binding(), captured_at=NOW)


def test_fails_closed_for_ambiguous_command_address() -> None:
    responses = json.loads(FIXTURE.read_text(encoding="utf-8"))
    responses["mags"].append(dict(responses["mags"][0]))

    with pytest.raises(Cs3CommissioningError, match="ambiguous"):
        adapter(responses).acquire("sha256:test", binding(), captured_at=NOW)


def test_fails_closed_for_missing_s88_state() -> None:
    responses = json.loads(FIXTURE.read_text(encoding="utf-8"))
    responses["mags/state"].pop(0)

    with pytest.raises(Cs3CommissioningError, match="missing current S88 state"):
        adapter(responses).acquire("sha256:test", binding(), captured_at=NOW)


def test_fails_closed_for_disconnect() -> None:
    def disconnected_fetcher(path: str) -> object:
        raise OSError(f"network unreachable while requesting {path}")

    disconnected = MarklinCs3CommissioningAdapter(
        "http://192.0.2.17",
        "2.6.1 (Build 3)",
        fetcher=disconnected_fetcher,
    )

    with pytest.raises(Cs3CommissioningError, match="network unreachable"):
        disconnected.acquire("sha256:test", binding(), captured_at=NOW)


def test_rejects_unknown_firmware_without_constructing_capture() -> None:
    with pytest.raises(Cs3CommissioningError, match="unsupported CS3 firmware"):
        MarklinCs3CommissioningAdapter(
            "http://192.0.2.17",
            "2.6.0",
            fetcher=json.loads(FIXTURE.read_text()).__getitem__,
        ).acquire("sha256:test", binding(), captured_at=NOW)


def test_live_command_operation_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="not implemented"):
        adapter().command_and_confirm_acceptance()
