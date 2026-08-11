"""Tests for the public RoutePlan reservation contract values."""
# pyright: reportMissingImports=false, reportUnknownMemberType=false

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from gleiswerk.route_compiler import compile_route
from gleiswerk.route_reservations import (
    AcquireReservationResult,
    IncompatibleReservation,
    IncompatibleReservationDeviceConstraint,
    OverlappingReservationClaim,
    ReleaseReservationResult,
    Reservation,
    ReservationId,
    ReservationInspection,
    ReservationNotFound,
    ReservationOwner,
    TopologyRevisionMismatch,
)
from gleiswerk.topology import (
    ControlDeviceId,
    DevicePositionId,
    JunctionId,
    JunctionResource,
    RouteDefinitionId,
    TrackSectionId,
    TrackSectionResource,
)
from gleiswerk.topology_config import load_topology

FIXTURES = Path(__file__).parent / "fixtures" / "schema_v3"


def _reservation(route_id: str, reservation_id: str = "reservation-a") -> Reservation:
    topology = load_topology(FIXTURES / "valid-station.yaml")
    plan = compile_route(topology, RouteDefinitionId(route_id))
    return Reservation(
        ReservationId(reservation_id),
        ReservationOwner("dispatcher"),
        plan.route_id,
        plan.topology_revision,
        plan.claims,
        plan.requirements,
        {
            resource: tuple(item.source for item in sources)
            for resource, sources in plan.claim_provenance.items()
        },
        {
            device_id: tuple(item.source for item in sources)
            for device_id, sources in plan.requirement_provenance.items()
        },
    )


def test_reservation_copies_provenance_and_canonicalizes_its_public_values() -> None:
    reservation = _reservation("west-to-platform-1")

    assert [claim.id for claim in reservation.claims] == [
        "west-throat",
        "platform-1",
        "west-entry",
    ]
    assert tuple(reservation.claim_provenance) == reservation.claims
    assert tuple(reservation.requirement_provenance) == tuple(
        requirement.device_id for requirement in reservation.requirements
    )
    with pytest.raises(TypeError):
        cast(dict[object, tuple[str, ...]], reservation.claim_provenance)[
            TrackSectionResource(TrackSectionId("other"))
        ] = ("source",)


def test_incompatible_denial_orders_claim_and_device_conflicts_deterministically() -> (
    None
):
    denial = IncompatibleReservation(
        claim_conflicts=(
            OverlappingReservationClaim(
                TrackSectionResource(TrackSectionId("platform-1")),
                ("track-section:platform-1",),
                ReservationId("reservation-b"),
                ("track-section:platform-1",),
            ),
            OverlappingReservationClaim(
                JunctionResource(JunctionId("west-throat")),
                ("junction-passage:west-to-platform-1",),
                ReservationId("reservation-a"),
                ("junction-passage:west-to-platform-2",),
            ),
        ),
        device_constraint_conflicts=(
            IncompatibleReservationDeviceConstraint(
                ControlDeviceId("west-throat-turnout"),
                DevicePositionId("normal"),
                ("junction-passage:west-to-platform-1",),
                ReservationId("reservation-b"),
                DevicePositionId("reverse"),
                ("junction-passage:west-to-platform-2",),
            ),
        ),
    )

    assert [conflict.resource.id for conflict in denial.claim_conflicts] == [
        "west-throat",
        "platform-1",
    ]
    assert denial.device_constraint_conflicts[0].held_position == "reverse"


def test_acquire_revision_mismatch_carries_both_revision_identities() -> None:
    result = AcquireReservationResult(
        "revision-mismatch",
        denial_reason=TopologyRevisionMismatch("sha256:active", "sha256:plan"),
    )

    assert result.reservation is None
    assert isinstance(result.denial_reason, TopologyRevisionMismatch)
    assert result.denial_reason.kind == "revision-mismatch"
    assert result.denial_reason.active_topology_revision == "sha256:active"
    assert result.denial_reason.plan_topology_revision == "sha256:plan"


def test_success_and_invalid_release_outcomes_are_explicit() -> None:
    reservation = _reservation("west-to-platform-1")
    acquired = AcquireReservationResult("acquired", reservation=reservation)
    not_found = ReleaseReservationResult(
        "not-found", denial_reason=ReservationNotFound()
    )

    assert acquired.reservation is reservation
    assert acquired.denial_reason is None
    assert not_found.reservation_id is None
    assert isinstance(not_found.denial_reason, ReservationNotFound)


def test_inspection_orders_held_reservations_by_opaque_id() -> None:
    inspection = ReservationInspection(
        "sha256:active",
        (
            _reservation("west-to-platform-1", "reservation-z"),
            _reservation("depot-only"),
        ),
    )

    assert [reservation.id for reservation in inspection.reservations] == [
        "reservation-a",
        "reservation-z",
    ]
