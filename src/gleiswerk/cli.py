"""Command-line interface for Gleiswerk."""

import sys
from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from re import sub
from typing import cast

import yaml

from gleiswerk.route_compatibility import (
    CompatibilityAnalysisResult,
    IncompatibleControlDeviceRequirement,
    OverlappingExclusiveClaim,
    analyze_route_plans,
)
from gleiswerk.route_compiler import RouteCompilationError, compile_routes
from gleiswerk.route_reservations import (
    AcquireDenialReason,
    AcquireReservationRequest,
    IncompatibleReservation,
    IncompatibleReservationDeviceConstraint,
    InvalidReservationPlan,
    OverlappingReservationClaim,
    ReleaseReservationRequest,
    Reservation,
    ReservationId,
    ReservationManager,
    ReservationOwner,
    TopologyRevisionMismatch,
)
from gleiswerk.topology import (
    ClaimResource,
    JunctionResource,
    ProtectionZoneResource,
    RouteDefinitionId,
    RoutePlan,
    TrackSectionResource,
)
from gleiswerk.topology_config import TopologyConfigurationError, load_topology

_DISTRIBUTION_NAME = "gleiswerk"
_PRODUCT_NAME = "Gleiswerk"


class _ReportYamlDumper(yaml.SafeDumper):
    """Render scalar sequences compactly in human-facing reports."""


def _represent_report_list(
    dumper: yaml.SafeDumper, data: list[object]
) -> yaml.nodes.SequenceNode:
    """Keep report collections readable while compacting scalar references."""
    scalar_types = (str, int, float, bool, type(None))
    return dumper.represent_sequence(
        "tag:yaml.org,2002:seq",
        data,
        flow_style=all(isinstance(item, scalar_types) for item in data),
    )


_ReportYamlDumper.add_representer(list, _represent_report_list)


def _dump_report(document: Mapping[str, object]) -> str:
    """Serialize a CLI report using its stable presentation convention."""
    serialized = yaml.dump(document, Dumper=_ReportYamlDumper, sort_keys=False)
    return sub(
        r"(\[|, )'([a-z][a-z0-9-]*:[a-z][a-z0-9-]*)'(?=,|\])",
        r"\1\2",
        serialized,
    )


def build_parser() -> ArgumentParser:
    """Create the Gleiswerk command-line parser."""
    parser = ArgumentParser(
        prog=_DISTRIBUTION_NAME,
        description="Local-first model railway control and automation.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{_PRODUCT_NAME} {version(_DISTRIBUTION_NAME)}",
    )
    commands = parser.add_subparsers(dest="command")
    layout = commands.add_parser("layout", help="Manage layout configuration.")
    layout_commands = layout.add_subparsers(dest="layout_command")
    validate = layout_commands.add_parser(
        "validate", help="Validate a layout configuration file."
    )
    validate.add_argument("file", metavar="FILE", help="Path to a layout YAML file.")
    compatibility = layout_commands.add_parser(
        "compatibility", help="Report compatibility for every pair of routes."
    )
    compatibility.add_argument(
        "file", metavar="FILE", help="Path to a layout YAML file."
    )
    reservations = layout_commands.add_parser(
        "reservations", help="Evaluate an in-memory reservation operation sequence."
    )
    reservations.add_argument(
        "file", metavar="LAYOUT", help="Path to a layout YAML file."
    )
    reservations.add_argument(
        "operations",
        metavar="OPERATIONS",
        help="Path to a reservation operations YAML file.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Gleiswerk command-line interface."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "layout" and arguments.layout_command == "validate":
        return _validate_layout(arguments.file)
    if arguments.command == "layout" and arguments.layout_command == "compatibility":
        return _report_layout_compatibility(arguments.file)
    if arguments.command == "layout" and arguments.layout_command == "reservations":
        return _evaluate_reservation_operations(arguments.file, arguments.operations)
    return 0


def _validate_layout(file: str) -> int:
    """Validate a layout file and report the result for command-line users."""
    try:
        load_topology(Path(file))
    except TopologyConfigurationError as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Layout is valid: {file}")
    return 0


def _report_layout_compatibility(file: str) -> int:
    """Compile a layout's routes and emit their static compatibility result."""
    try:
        topology = load_topology(Path(file))
        analysis = analyze_route_plans(compile_routes(topology).values())
    except TopologyConfigurationError as error:
        print(error, file=sys.stderr)
        return 1
    except RouteCompilationError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1

    print(_dump_report(_compatibility_document(analysis)), end="")
    return 0


def _evaluate_reservation_operations(layout_file: str, operations_file: str) -> int:
    """Evaluate a bounded, fresh in-memory reservation operation sequence."""
    try:
        topology = load_topology(Path(layout_file))
        plans = compile_routes(topology)
        operations = _load_reservation_operations(Path(operations_file), plans)
    except TopologyConfigurationError as error:
        print(error, file=sys.stderr)
        return 1
    except RouteCompilationError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    except ReservationOperationsError as error:
        print(f"ERROR {operations_file}: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"ERROR {operations_file}: {error}", file=sys.stderr)
        return 1

    manager = ReservationManager(topology)
    results: list[dict[str, object]] = []
    for operation in operations:
        owner = ReservationOwner(operation["owner"])
        if operation["operation"] == "acquire":
            route = operation["route"]
            result = manager.acquire(
                AcquireReservationRequest(owner, plans[RouteDefinitionId(route)])
            )
            item: dict[str, object] = {
                "operation": "acquire",
                "owner": owner,
                "route": route,
                "success": result.outcome == "acquired",
                "outcome": result.outcome,
            }
            if result.reservation is not None:
                item["reservation"] = result.reservation.id
            if result.denial_reason is not None:
                item["denial"] = _acquire_denial_document(result.denial_reason)
            results.append(item)
            continue

        reservation_id = ReservationId(operation["reservation"])
        result = manager.release(ReleaseReservationRequest(owner, reservation_id))
        item = {
            "operation": "release",
            "owner": owner,
            "reservation": reservation_id,
            "success": result.outcome == "released",
            "outcome": result.outcome,
        }
        if result.denial_reason is not None:
            item["denial"] = {"kind": result.denial_reason.kind}
        results.append(item)

    inspection = manager.inspect()
    print(
        _dump_report(
            {
                "topology-revision": inspection.topology_revision,
                "operations": results,
                "held-reservations": [
                    _reservation_document(reservation)
                    for reservation in inspection.reservations
                ],
            },
        ),
        end="",
    )
    return 0


class ReservationOperationsError(ValueError):
    """A reservation operation document is not within the bounded CLI schema."""


def _load_reservation_operations(
    file: Path, plans: Mapping[RouteDefinitionId, RoutePlan]
) -> tuple[dict[str, str], ...]:
    """Load the intentionally small, explicit reservation operation schema."""
    try:
        document: object = yaml.safe_load(file.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ReservationOperationsError(f"invalid YAML: {error}") from error
    if not isinstance(document, Mapping):
        raise ReservationOperationsError(
            "expected exactly one top-level 'operations' list"
        )
    mapping = cast(Mapping[object, object], document)
    if set(mapping) != {"operations"}:
        raise ReservationOperationsError(
            "expected exactly one top-level 'operations' list"
        )
    raw_operations = mapping["operations"]
    if not isinstance(raw_operations, list):
        raise ReservationOperationsError("operations must be a list")

    operations: list[dict[str, str]] = []
    for index, raw_operation in enumerate(cast(list[object], raw_operations)):
        location = f"operations[{index}]"
        if not isinstance(raw_operation, Mapping):
            raise ReservationOperationsError(f"{location} must be a mapping")
        operation_mapping = cast(Mapping[object, object], raw_operation)
        operation = operation_mapping.get("operation")
        if operation == "acquire":
            required_keys = {"operation", "owner", "route"}
            route = operation_mapping.get("route")
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} acquire requires exactly operation, owner, and route"
                )
            if not isinstance(route, str) or RouteDefinitionId(route) not in plans:
                raise ReservationOperationsError(
                    f"{location}.route names no compiled route"
                )
            value = {"operation": "acquire", "route": route}
        elif operation == "release":
            required_keys = {"operation", "owner", "reservation"}
            reservation = operation_mapping.get("reservation")
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} release requires exactly operation, owner, and reservation"
                )
            if not isinstance(reservation, str):
                raise ReservationOperationsError(
                    f"{location}.reservation must be a string"
                )
            value = {"operation": "release", "reservation": reservation}
        else:
            raise ReservationOperationsError(
                f"{location}.operation must be 'acquire' or 'release'"
            )
        owner = operation_mapping.get("owner")
        if not isinstance(owner, str) or not owner:
            raise ReservationOperationsError(
                f"{location}.owner must be a nonempty string"
            )
        value["owner"] = owner
        operations.append(value)
    return tuple(operations)


def _reservation_document(reservation: Reservation) -> dict[str, object]:
    """Serialize a held reservation without claiming any live railway evidence."""
    return {
        "id": reservation.id,
        "owner": reservation.owner,
        "route": reservation.route_id,
        "claims": [_claim_resource_reference(claim) for claim in reservation.claims],
        "requirements": {
            str(requirement.device_id): requirement.position_id
            for requirement in reservation.requirements
        },
    }


def _acquire_denial_document(denial: AcquireDenialReason) -> dict[str, object]:
    """Serialize a reservation denial using only the public core explanation."""
    if isinstance(denial, IncompatibleReservation):
        return {
            "kind": denial.kind,
            "claim-conflicts": [
                _claim_conflict_document(conflict)
                for conflict in denial.claim_conflicts
            ],
            "device-constraint-conflicts": [
                _device_constraint_conflict_document(conflict)
                for conflict in denial.device_constraint_conflicts
            ],
        }
    if isinstance(denial, TopologyRevisionMismatch):
        return {
            "kind": denial.kind,
            "active-topology-revision": denial.active_topology_revision,
            "plan-topology-revision": denial.plan_topology_revision,
        }
    assert isinstance(denial, InvalidReservationPlan)
    return {"kind": denial.kind}


def _claim_conflict_document(
    conflict: OverlappingReservationClaim,
) -> dict[str, object]:
    return {
        "resource": _claim_resource_reference(conflict.resource),
        "requested-provenance": list(conflict.requested_provenance),
        "held-reservation": conflict.held_reservation_id,
        "held-provenance": list(conflict.held_provenance),
    }


def _device_constraint_conflict_document(
    conflict: IncompatibleReservationDeviceConstraint,
) -> dict[str, object]:
    return {
        "control-device": conflict.control_device,
        "requested-position": conflict.requested_position,
        "requested-provenance": list(conflict.requested_provenance),
        "held-reservation": conflict.held_reservation_id,
        "held-position": conflict.held_position,
        "held-provenance": list(conflict.held_provenance),
    }


def _compatibility_document(analysis: CompatibilityAnalysisResult) -> dict[str, object]:
    """Return the documented, serializable compatibility result."""
    return {
        "topology-revision": analysis.topology_revision,
        "pairs": [
            {
                "route-pair": list(pair.route_pair),
                "compatible": pair.compatible,
                "conflicts": [
                    _conflict_document(conflict) for conflict in pair.conflicts
                ],
            }
            for pair in analysis.pairs
        ],
    }


def _conflict_document(
    conflict: OverlappingExclusiveClaim | IncompatibleControlDeviceRequirement,
) -> dict[str, object]:
    """Serialize one compatibility conflict using the public contract shape."""
    provenance = {
        str(route_id): list(sources)
        for route_id, sources in conflict.provenance.items()
    }
    if isinstance(conflict, OverlappingExclusiveClaim):
        return {
            "kind": conflict.kind,
            "resource": _claim_resource_reference(conflict.resource),
            "provenance": provenance,
        }
    return {
        "kind": conflict.kind,
        "control-device": str(conflict.control_device),
        "required-positions": {
            str(route_id): position
            for route_id, position in conflict.required_positions.items()
        },
        "provenance": provenance,
    }


def _claim_resource_reference(resource: ClaimResource) -> str:
    """Format one claim resource with its stable contract prefix."""
    if isinstance(resource, TrackSectionResource):
        return f"track-section:{resource.id}"
    if isinstance(resource, JunctionResource):
        return f"junction:{resource.id}"
    assert isinstance(resource, ProtectionZoneResource)
    return f"protection-zone:{resource.id}"
