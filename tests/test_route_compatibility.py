# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUntypedFunctionDecorator=false
"""Tests for static RoutePlan compatibility analysis."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from gleiswerk.route_compatibility import (
    IncompatibleControlDeviceRequirement,
    OverlappingExclusiveClaim,
    analyze_route_plans,
)
from gleiswerk.route_compiler import compile_route
from gleiswerk.topology_config import load_topology

FIXTURES = Path(__file__).parent / "fixtures" / "schema_v3"


def _plans(fixture: str, *route_ids: str):
    topology = load_topology(FIXTURES / fixture)
    return tuple(compile_route(topology, route_id) for route_id in route_ids)


def test_disjoint_plans_are_explicitly_compatible() -> None:
    plans = _plans("valid-station.yaml", "west-to-east-via-platform-1", "depot-only")

    result = analyze_route_plans(reversed(plans))

    assert result.topology_revision == plans[0].topology_revision
    assert result.pairs[0].route_pair == ("depot-only", "west-to-east-via-platform-1")
    assert result.pairs[0].compatible is True
    assert result.pairs[0].conflicts == ()


def test_incompatible_device_requirements_include_positions_and_provenance() -> None:
    result = analyze_route_plans(
        _plans("valid-station.yaml", "west-to-platform-2", "west-to-platform-1")
    )

    conflict = result.pairs[0].conflicts[0]
    assert isinstance(conflict, IncompatibleControlDeviceRequirement)
    assert conflict.control_device == "west-throat-turnout"
    assert dict(conflict.required_positions) == {
        "west-to-platform-1": "normal",
        "west-to-platform-2": "reverse",
    }
    assert dict(conflict.provenance) == {
        "west-to-platform-1": ("junction-passage:west-to-platform-1",),
        "west-to-platform-2": ("junction-passage:west-to-platform-2",),
    }


def test_equal_device_requirements_do_not_cancel_physical_conflicts() -> None:
    result = analyze_route_plans(
        _plans(
            "valid-station.yaml", "west-to-platform-1", "west-to-east-via-platform-1"
        )
    )

    assert [
        conflict.resource.id
        for conflict in result.pairs[0].conflicts
        if isinstance(conflict, OverlappingExclusiveClaim)
    ] == [
        "west-throat",
        "platform-1",
        "west-entry",
    ]


def test_shared_protection_claims_include_rule_provenance() -> None:
    result = analyze_route_plans(
        _plans("valid-protection.yaml", "west-to-east", "north-to-south")
    )

    conflict = result.pairs[0].conflicts[1]
    assert isinstance(conflict, OverlappingExclusiveClaim)
    assert conflict.resource.id == "crossing-fouling"
    assert dict(conflict.provenance) == {
        "north-to-south": ("protection-rule:north-south-fouling",),
        "west-to-east": ("protection-rule:east-west-fouling",),
    }


def test_reverse_routes_conflict_on_the_same_physical_claims() -> None:
    result = analyze_route_plans(
        _plans(
            "valid-station.yaml",
            "east-to-west-via-platform-1",
            "west-to-east-via-platform-1",
        )
    )

    assert all(
        isinstance(conflict, OverlappingExclusiveClaim)
        for conflict in result.pairs[0].conflicts
    )
    assert len(result.pairs[0].conflicts) == 5


def test_pairs_and_conflicts_are_sorted_independently_of_input_order() -> None:
    plans = _plans(
        "valid-station.yaml",
        "west-to-platform-1",
        "depot-only",
        "west-to-east-via-platform-1",
    )

    result = analyze_route_plans(reversed(plans))

    assert [pair.route_pair for pair in result.pairs] == [
        ("depot-only", "west-to-east-via-platform-1"),
        ("depot-only", "west-to-platform-1"),
        ("west-to-east-via-platform-1", "west-to-platform-1"),
    ]
    assert [conflict.kind for conflict in result.pairs[-1].conflicts] == [
        "overlapping-exclusive-claim",
        "overlapping-exclusive-claim",
        "overlapping-exclusive-claim",
    ]


def test_invalid_plan_collections_are_rejected() -> None:
    first, _second = _plans("valid-station.yaml", "depot-only", "west-to-platform-1")

    with pytest.raises(ValueError, match="unique route definition IDs"):
        analyze_route_plans((first, first))
    with pytest.raises(ValueError, match="at least two"):
        analyze_route_plans((first,))
    with pytest.raises(ValueError, match="one topology revision"):
        analyze_route_plans((first, _plans("valid-protection.yaml", "west-to-east")[0]))


def test_result_mappings_are_immutable() -> None:
    result = analyze_route_plans(
        _plans("valid-station.yaml", "west-to-platform-2", "west-to-platform-1")
    )
    conflict = result.pairs[0].conflicts[0]

    assert isinstance(conflict, IncompatibleControlDeviceRequirement)
    with pytest.raises(TypeError):
        cast(dict[str, str], conflict.required_positions)["other-route"] = "normal"
