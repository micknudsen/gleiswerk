"""Tests for the public RoutePlan reservation contract values."""
# pyright: reportMissingImports=false, reportUnknownMemberType=false

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from gleiswerk.route_compiler import compile_route
from gleiswerk.route_reservations import (
    AcquireReservationRequest,
    AcquireReservationResult,
    IncompatibleReservation,
    IncompatibleReservationDeviceConstraint,
    OverlappingReservationClaim,
    ReleaseReservationRequest,
    ReleaseReservationResult,
    Reservation,
    ReservationId,
    ReservationInspection,
    ReservationManager,
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


def test_manager_acquires_and_releases_a_plan_as_one_atomic_reservation() -> None:
    plan = compile_route(
        load_topology(FIXTURES / "valid-station.yaml"),
        RouteDefinitionId("west-to-platform-1"),
    )
    manager = ReservationManager(plan.topology_revision)
    acquired = manager.acquire(
        AcquireReservationRequest(ReservationOwner("dispatcher"), plan)
    )

    assert acquired.outcome == "acquired"
    assert acquired.reservation is not None
    assert manager.inspect().reservations == (acquired.reservation,)

    released = manager.release(
        ReleaseReservationRequest(
            ReservationOwner("dispatcher"), acquired.reservation.id
        )
    )

    assert released.outcome == "released"
    assert released.reservation_id == acquired.reservation.id
    assert manager.inspect().reservations == ()


def test_manager_denies_overlapping_claims_without_changing_held_state() -> None:
    topology = load_topology(FIXTURES / "valid-station.yaml")
    held_plan = compile_route(topology, RouteDefinitionId("west-to-platform-1"))
    conflicting_plan = compile_route(
        topology, RouteDefinitionId("west-to-east-via-platform-1")
    )
    manager = ReservationManager(topology.revision)
    held = manager.acquire(
        AcquireReservationRequest(ReservationOwner("one"), held_plan)
    )

    denied = manager.acquire(
        AcquireReservationRequest(ReservationOwner("two"), conflicting_plan)
    )

    assert held.reservation is not None
    assert denied.outcome == "incompatible"
    assert isinstance(denied.denial_reason, IncompatibleReservation)
    assert [
        conflict.resource.id for conflict in denied.denial_reason.claim_conflicts
    ] == [
        "west-throat",
        "platform-1",
        "west-entry",
    ]
    assert manager.inspect().reservations == (held.reservation,)


def test_manager_allows_shared_device_values_but_denies_different_values() -> None:
    topology = load_topology(FIXTURES / "valid-station.yaml")
    manager = ReservationManager(topology.revision)
    first = compile_route(topology, RouteDefinitionId("west-to-platform-1"))
    same_value = compile_route(topology, RouteDefinitionId("depot-only"))
    different_value = compile_route(topology, RouteDefinitionId("west-to-platform-2"))

    assert (
        manager.acquire(
            AcquireReservationRequest(ReservationOwner("one"), first)
        ).outcome
        == "acquired"
    )
    assert (
        manager.acquire(
            AcquireReservationRequest(ReservationOwner("two"), same_value)
        ).outcome
        == "acquired"
    )
    denied = manager.acquire(
        AcquireReservationRequest(ReservationOwner("three"), different_value)
    )

    assert denied.outcome == "incompatible"
    assert isinstance(denied.denial_reason, IncompatibleReservation)
    assert denied.denial_reason.device_constraint_conflicts[0].control_device == (
        "west-throat-turnout"
    )


def test_manager_rejects_invalid_and_stale_plans_without_changing_state() -> None:
    topology = load_topology(FIXTURES / "valid-station.yaml")
    plan = compile_route(topology, RouteDefinitionId("depot-only"))
    manager = ReservationManager(topology.revision)
    stale = manager.acquire(
        AcquireReservationRequest(
            ReservationOwner("dispatcher"),
            plan.__class__(
                plan.route_id,
                "sha256:stale",
                plan.path,
                plan.claims,
                plan.requirements,
                plan.claim_provenance,
                plan.requirement_provenance,
            ),
        )
    )
    invalid = manager.acquire(
        AcquireReservationRequest(
            ReservationOwner("dispatcher"),
            plan.__class__(
                plan.route_id,
                plan.topology_revision,
                plan.path,
                plan.claims + (plan.claims[0],),
                plan.requirements,
                plan.claim_provenance,
                plan.requirement_provenance,
            ),
        )
    )

    assert stale.outcome == "revision-mismatch"
    assert invalid.outcome == "invalid-plan"
    assert manager.inspect().reservations == ()


def test_manager_release_is_owner_checked_and_not_found_is_idempotent() -> None:
    topology = load_topology(FIXTURES / "valid-station.yaml")
    manager = ReservationManager(topology.revision)
    acquired = manager.acquire(
        AcquireReservationRequest(
            ReservationOwner("owner"),
            compile_route(topology, RouteDefinitionId("depot-only")),
        )
    )

    assert acquired.reservation is not None
    not_owner = manager.release(
        ReleaseReservationRequest(ReservationOwner("other"), acquired.reservation.id)
    )
    released = manager.release(
        ReleaseReservationRequest(ReservationOwner("owner"), acquired.reservation.id)
    )
    not_found = manager.release(
        ReleaseReservationRequest(ReservationOwner("owner"), acquired.reservation.id)
    )

    assert not_owner.outcome == "not-owner"
    assert released.outcome == "released"
    assert not_found.outcome == "not-found"


def test_manager_rejects_acquisition_without_an_active_topology() -> None:
    plan = compile_route(
        load_topology(FIXTURES / "valid-station.yaml"), RouteDefinitionId("depot-only")
    )
    manager = ReservationManager()

    assert (
        manager.acquire(
            AcquireReservationRequest(ReservationOwner("dispatcher"), plan)
        ).outcome
        == "no-active-topology"
    )
    assert manager.activate_topology(plan.topology_revision) is True
    assert (
        manager.acquire(
            AcquireReservationRequest(ReservationOwner("dispatcher"), plan)
        ).outcome
        == "acquired"
    )
    assert manager.activate_topology("sha256:other") is False
