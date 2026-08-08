# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false
"""Tests for deterministic, resource-complete route planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from gleiswerk.route_compiler import RouteCompilationError, compile_route
from gleiswerk.topology import (
    ConnectionPathElement,
    JunctionPassagePathElement,
    JunctionResource,
    ProtectionZoneResource,
    TrackSectionPathElement,
    TrackSectionResource,
)
from gleiswerk.topology_config import load_topology

FIXTURES = Path(__file__).parent / "fixtures" / "schema_v3"


def test_direct_connection_compiles_every_section_without_a_junction_claim() -> None:
    plan = compile_route(
        load_topology(FIXTURES / "valid-direct.yaml"), "direct-arrival"
    )

    assert plan.path == (
        TrackSectionPathElement("approach", "west", "east"),
        ConnectionPathElement(
            "approach-to-platform",
            plan.path[1].from_port,
            plan.path[1].to_port,
        ),
        TrackSectionPathElement("platform", "west", "east"),
    )
    assert plan.claims == (
        TrackSectionResource("approach"),
        TrackSectionResource("platform"),
    )


def test_route_inside_one_section_claims_that_section() -> None:
    plan = compile_route(
        load_topology(FIXTURES / "valid-direct.yaml"), "within-platform"
    )

    assert plan.path == (TrackSectionPathElement("platform", "west", "east"),)
    assert plan.claims == (TrackSectionResource("platform"),)


def test_station_route_and_reverse_have_complete_directed_paths_and_shared_claims() -> (
    None
):
    topology = load_topology(FIXTURES / "valid-station.yaml")
    forward = compile_route(topology, "west-to-east-via-platform-1")
    reverse = compile_route(topology, "east-to-west-via-platform-1")

    assert len(forward.path) == len(reverse.path) == 9
    assert isinstance(forward.path[2], JunctionPassagePathElement)
    assert isinstance(reverse.path[2], JunctionPassagePathElement)
    assert forward.path[0] == TrackSectionPathElement("west-entry", "west", "east")
    assert reverse.path[0] == TrackSectionPathElement("east-exit", "east", "west")
    assert forward.claims == reverse.claims
    assert set(forward.claims) == {
        TrackSectionResource("west-entry"),
        TrackSectionResource("platform-1"),
        TrackSectionResource("east-exit"),
        JunctionResource("west-throat"),
        JunctionResource("east-throat"),
    }
    assert [requirement.device_id for requirement in forward.requirements] == [
        "east-throat-turnout",
        "west-throat-turnout",
    ]


def test_protection_rules_add_non_path_claims_requirements_and_provenance() -> None:
    plan = compile_route(
        load_topology(FIXTURES / "valid-protection.yaml"), "west-to-east"
    )

    assert {
        ProtectionZoneResource("crossing-fouling"),
        ProtectionZoneResource("east-overlap"),
        ProtectionZoneResource("siding-flank"),
    } <= set(plan.claims)
    assert plan.requirements[0].device_id == "siding-trap"
    assert {
        source.source
        for source in plan.claim_provenance[ProtectionZoneResource("east-overlap")]
    } == {"protection-rule:east-boundary-overlap"}


@pytest.mark.parametrize(
    ("fixture", "route", "code"),
    [
        ("invalid-ambiguous-route.yaml", "ambiguous", "E401"),
        ("invalid-repeated-resource.yaml", "loop", "E402"),
        ("invalid-contradictory-requirements.yaml", "to-main", "E404"),
    ],
)
def test_compilation_rejects_ambiguous_repeated_and_contradictory_routes(
    fixture: str, route: str, code: str
) -> None:
    with pytest.raises(RouteCompilationError) as error:
        compile_route(load_topology(FIXTURES / fixture), route)

    assert error.value.code == code
    assert error.value.path == f"route-definitions.{route}"
