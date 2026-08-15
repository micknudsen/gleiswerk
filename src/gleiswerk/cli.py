"""Command-line interface for Gleiswerk."""

import sys
from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from re import sub
from typing import cast

import yaml

from gleiswerk.evidence import (
    DevicePositionEvidence,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyState,
)
from gleiswerk.evidence_validation import EvidenceValidationResult, validate_evidence
from gleiswerk.movement_authority import (
    MovementAuthority,
    MovementAuthorityEvaluator,
    MovementAuthorityFailure,
    MovementAuthorityId,
    MovementAuthorityRequest,
)
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
    ControlDeviceId,
    DevicePositionId,
    JunctionResource,
    OccupancyZoneId,
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
        "reservations",
        help="Evaluate an in-memory reservation and authority workflow.",
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
        workflow = _load_reservation_operations(Path(operations_file), plans)
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
    clock = _WorkflowClock()
    evaluator = MovementAuthorityEvaluator(
        topology.revision,
        timedelta(seconds=workflow.authority_maximum_validity_seconds),
        clock,
    )
    occupancy_evidence: dict[OccupancyZoneId, OccupancyEvidence] = {}
    device_evidence: dict[ControlDeviceId, DevicePositionEvidence] = {}
    results: list[dict[str, object]] = []
    for operation in workflow.operations:
        if operation["operation"] == "observe-occupancy":
            zone = OccupancyZoneId(cast(str, operation["zone"]))
            status = EvidenceSourceStatus(cast(str, operation["status"]))
            state_value = operation.get("state")
            occupancy_evidence[zone] = OccupancyEvidence(
                zone,
                topology.revision,
                EvidenceSourceId(cast(str, operation["source"])),
                status,
                clock.datetime,
                OccupancyState(cast(str, state_value))
                if state_value is not None
                else None,
            )
            item = dict(operation)
            item.update(success=True, outcome="observed", **{"at-seconds": clock()})
            results.append(item)
            continue

        if operation["operation"] == "observe-device-position":
            device = ControlDeviceId(cast(str, operation["device"]))
            status = EvidenceSourceStatus(cast(str, operation["status"]))
            position = operation.get("position")
            device_evidence[device] = DevicePositionEvidence(
                device,
                topology.revision,
                EvidenceSourceId(cast(str, operation["source"])),
                status,
                clock.datetime,
                DevicePositionId(cast(str, position)) if position is not None else None,
            )
            item = dict(operation)
            item.update(success=True, outcome="observed", **{"at-seconds": clock()})
            results.append(item)
            continue

        if operation["operation"] == "advance-time":
            seconds = cast(int, operation["seconds"])
            clock.advance(seconds)
            results.append(
                {
                    "operation": "advance-time",
                    "seconds": seconds,
                    "success": True,
                    "outcome": "advanced",
                    "at-seconds": clock(),
                }
            )
            continue

        if operation["operation"] == "reevaluate-authority":
            authority_id = MovementAuthorityId(cast(str, operation["authority"]))
            route = cast(str, operation["route"])
            evidence = validate_evidence(
                topology,
                plans[RouteDefinitionId(route)],
                EvidenceFreshnessBasis(
                    clock.datetime,
                    timedelta(seconds=workflow.evidence_maximum_age_seconds),
                ),
                occupancy_evidence.values(),
                device_evidence.values(),
            )
            result = evaluator.reevaluate(authority_id, manager.inspect(), evidence)
            item = {
                "operation": "reevaluate-authority",
                "authority": authority_id,
                "route": route,
                "success": result.outcome == "live",
                "outcome": result.outcome,
                "evidence": _evidence_validation_document(evidence),
            }
            if result.authority is not None and result.authority.revocation is not None:
                item["revocation"] = _authority_failure_document(
                    result.authority.revocation
                )
            if result.denial_reason is not None:
                item["denial"] = {"kind": result.denial_reason.kind}
            results.append(item)
            continue

        owner = ReservationOwner(cast(str, operation["owner"]))
        if operation["operation"] == "acquire":
            route = cast(str, operation["route"])
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

        if operation["operation"] == "evaluate-authority":
            reservation_id = ReservationId(cast(str, operation["reservation"]))
            route = cast(str, operation["route"])
            valid_for_seconds = cast(int, operation["valid-for-seconds"])
            evidence = validate_evidence(
                topology,
                plans[RouteDefinitionId(route)],
                EvidenceFreshnessBasis(
                    clock.datetime,
                    timedelta(seconds=workflow.evidence_maximum_age_seconds),
                ),
                occupancy_evidence.values(),
                device_evidence.values(),
            )
            result = evaluator.evaluate(
                MovementAuthorityRequest(
                    owner,
                    reservation_id,
                    evidence,
                    timedelta(seconds=valid_for_seconds),
                ),
                manager.inspect(),
            )
            item = {
                "operation": "evaluate-authority",
                "owner": owner,
                "reservation": reservation_id,
                "route": route,
                "valid-for-seconds": valid_for_seconds,
                "success": result.outcome == "granted",
                "outcome": result.outcome,
                "evidence": _evidence_validation_document(evidence),
            }
            if result.authority is not None:
                item["authority"] = result.authority.id
            if result.denial_reason is not None:
                item["denial"] = _authority_failure_document(result.denial_reason)
            results.append(item)
            continue

        reservation_id = ReservationId(cast(str, operation["reservation"]))
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
    report: dict[str, object] = {
        "topology-revision": inspection.topology_revision,
        "operations": results,
        "held-reservations": [
            _reservation_document(reservation)
            for reservation in inspection.reservations
        ],
    }
    if workflow.includes_authorities:
        report["authorities"] = [
            _authority_document(authority)
            for authority in evaluator.inspect().authorities
        ]
    print(_dump_report(report), end="")
    return 0


class ReservationOperationsError(ValueError):
    """A reservation operation document is not within the bounded CLI schema."""


@dataclass(frozen=True, slots=True)
class _WorkflowDocument:
    operations: tuple[dict[str, str | int], ...]
    evidence_maximum_age_seconds: int = 30
    authority_maximum_validity_seconds: int = 60
    includes_authorities: bool = False


class _WorkflowClock:
    """One deterministic clock shared by evidence and authority evaluation."""

    def __init__(self) -> None:
        self._seconds = 0.0

    def __call__(self) -> float:
        return self._seconds

    def advance(self, seconds: int) -> None:
        self._seconds += seconds

    @property
    def datetime(self) -> datetime:
        return datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=self._seconds)


def _load_reservation_operations(
    file: Path, plans: Mapping[RouteDefinitionId, RoutePlan]
) -> _WorkflowDocument:
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
    if set(mapping) not in ({"operations"}, {"settings", "operations"}):
        raise ReservationOperationsError(
            "expected top-level 'operations' and optional 'settings' mappings"
        )
    evidence_maximum_age_seconds = 30
    authority_maximum_validity_seconds = 60
    has_settings = "settings" in mapping
    includes_authorities = False
    if has_settings:
        settings = mapping["settings"]
        if not isinstance(settings, Mapping):
            raise ReservationOperationsError("settings must be a mapping")
        settings_mapping = cast(Mapping[object, object], settings)
        required_settings = {
            "evidence-maximum-age-seconds",
            "authority-maximum-validity-seconds",
        }
        if set(settings_mapping) != required_settings:
            raise ReservationOperationsError(
                "settings require exactly evidence-maximum-age-seconds and "
                "authority-maximum-validity-seconds"
            )
        evidence_maximum_age_seconds = _positive_seconds(
            settings_mapping["evidence-maximum-age-seconds"],
            "settings.evidence-maximum-age-seconds",
        )
        authority_maximum_validity_seconds = _positive_seconds(
            settings_mapping["authority-maximum-validity-seconds"],
            "settings.authority-maximum-validity-seconds",
        )
    raw_operations = mapping["operations"]
    if not isinstance(raw_operations, list):
        raise ReservationOperationsError("operations must be a list")

    operations: list[dict[str, str | int]] = []
    for index, raw_operation in enumerate(cast(list[object], raw_operations)):
        location = f"operations[{index}]"
        if not isinstance(raw_operation, Mapping):
            raise ReservationOperationsError(f"{location} must be a mapping")
        operation_mapping = cast(Mapping[object, object], raw_operation)
        operation = operation_mapping.get("operation")
        value: dict[str, str | int]
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
        elif operation == "observe-occupancy":
            status = _evidence_status(operation_mapping, location)
            required_keys = {"operation", "zone", "source", "status"}
            if status is EvidenceSourceStatus.AVAILABLE:
                required_keys.add("state")
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} observe-occupancy fields do not match its status"
                )
            zone = _nonempty_string(operation_mapping.get("zone"), f"{location}.zone")
            source = _nonempty_string(
                operation_mapping.get("source"), f"{location}.source"
            )
            value = {
                "operation": "observe-occupancy",
                "zone": zone,
                "source": source,
                "status": status.value,
            }
            if status is EvidenceSourceStatus.AVAILABLE:
                state = operation_mapping.get("state")
                if state not in {"clear", "occupied"}:
                    raise ReservationOperationsError(
                        f"{location}.state must be 'clear' or 'occupied'"
                    )
                value["state"] = cast(str, state)
            operations.append(value)
            includes_authorities = True
            continue
        elif operation == "observe-device-position":
            status = _evidence_status(operation_mapping, location)
            required_keys = {"operation", "device", "source", "status"}
            if status is EvidenceSourceStatus.AVAILABLE:
                required_keys.add("position")
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} observe-device-position fields do not match its status"
                )
            device = _nonempty_string(
                operation_mapping.get("device"), f"{location}.device"
            )
            source = _nonempty_string(
                operation_mapping.get("source"), f"{location}.source"
            )
            value = {
                "operation": "observe-device-position",
                "device": device,
                "source": source,
                "status": status.value,
            }
            if status is EvidenceSourceStatus.AVAILABLE:
                value["position"] = _nonempty_string(
                    operation_mapping.get("position"), f"{location}.position"
                )
            operations.append(value)
            includes_authorities = True
            continue
        elif operation == "evaluate-authority":
            required_keys = {
                "operation",
                "owner",
                "reservation",
                "route",
                "valid-for-seconds",
            }
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} evaluate-authority requires exactly operation, "
                    "owner, reservation, route, and valid-for-seconds"
                )
            reservation = _nonempty_string(
                operation_mapping.get("reservation"), f"{location}.reservation"
            )
            route = operation_mapping.get("route")
            if not isinstance(route, str) or RouteDefinitionId(route) not in plans:
                raise ReservationOperationsError(
                    f"{location}.route names no compiled route"
                )
            value = {
                "operation": "evaluate-authority",
                "reservation": reservation,
                "route": route,
                "valid-for-seconds": _positive_seconds(
                    operation_mapping.get("valid-for-seconds"),
                    f"{location}.valid-for-seconds",
                ),
            }
            includes_authorities = True
        elif operation == "advance-time":
            required_keys = {"operation", "seconds"}
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} advance-time requires exactly operation and seconds"
                )
            operations.append(
                {
                    "operation": "advance-time",
                    "seconds": _positive_seconds(
                        operation_mapping.get("seconds"), f"{location}.seconds"
                    ),
                }
            )
            includes_authorities = True
            continue
        elif operation == "reevaluate-authority":
            required_keys = {"operation", "authority", "route"}
            if set(operation_mapping) != required_keys:
                raise ReservationOperationsError(
                    f"{location} reevaluate-authority requires exactly operation, "
                    "authority, and route"
                )
            authority = _nonempty_string(
                operation_mapping.get("authority"), f"{location}.authority"
            )
            route = operation_mapping.get("route")
            if not isinstance(route, str) or RouteDefinitionId(route) not in plans:
                raise ReservationOperationsError(
                    f"{location}.route names no compiled route"
                )
            operations.append(
                {
                    "operation": "reevaluate-authority",
                    "authority": authority,
                    "route": route,
                }
            )
            includes_authorities = True
            continue
        else:
            raise ReservationOperationsError(f"{location}.operation is not supported")
        owner = operation_mapping.get("owner")
        if not isinstance(owner, str) or not owner:
            raise ReservationOperationsError(
                f"{location}.owner must be a nonempty string"
            )
        value["owner"] = owner
        operations.append(value)
    if includes_authorities and not has_settings:
        raise ReservationOperationsError(
            "authority workflows require explicit top-level settings"
        )
    return _WorkflowDocument(
        tuple(operations),
        evidence_maximum_age_seconds,
        authority_maximum_validity_seconds,
        includes_authorities,
    )


def _positive_seconds(value: object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReservationOperationsError(f"{location} must be a positive integer")
    return value


def _nonempty_string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReservationOperationsError(f"{location} must be a nonempty string")
    return value


def _evidence_status(
    operation: Mapping[object, object], location: str
) -> EvidenceSourceStatus:
    status = operation.get("status")
    try:
        return EvidenceSourceStatus(cast(str, status))
    except ValueError as error:
        raise ReservationOperationsError(
            f"{location}.status must be 'available', 'unknown', or 'faulted'"
        ) from error


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


def _authority_document(authority: MovementAuthority) -> dict[str, object]:
    """Serialize one authority without adding any real-world movement meaning."""
    document: dict[str, object] = {
        "id": authority.id,
        "reservation": authority.reservation_id,
        "owner": authority.owner,
        "route": authority.route_id,
        "topology-revision": authority.topology_revision,
        "scope": [_claim_resource_reference(claim) for claim in authority.scope.claims],
        "issued-at-seconds": authority.issued_at,
        "expires-at-seconds": authority.expires_at,
        "status": authority.status,
    }
    if authority.revocation is not None:
        document["revocation"] = _authority_failure_document(authority.revocation)
    return document


def _authority_failure_document(
    failure: MovementAuthorityFailure,
) -> dict[str, object]:
    """Serialize the core's stable authority explanation and provenance."""
    document: dict[str, object] = {
        "kind": failure.kind.value,
        "target": failure.target,
    }
    if failure.evidence_rejection is not None:
        document["evidence-rejection"] = {
            "kind": failure.evidence_rejection.kind.value,
            "target": failure.evidence_rejection.target,
            "sources": list(failure.evidence_rejection.source_ids),
        }
    return document


def _evidence_validation_document(
    result: EvidenceValidationResult,
) -> dict[str, object]:
    """Serialize read-only evidence status with logical source provenance."""
    return {
        "topology-revision": result.topology_revision,
        "route": result.plan_route_id,
        "occupancy": [
            {
                "zone": item.zone_id,
                "source": item.source_id,
                "outcome": item.outcome.value,
            }
            for item in result.occupancy_results
        ],
        "device-positions": [
            {
                "device": item.device_id,
                "required-position": item.required_position_id,
                "source": item.source_id,
                "outcome": item.outcome.value,
            }
            for item in result.device_position_results
        ],
        "rejections": [
            {
                "kind": item.kind.value,
                "target": item.target,
                "sources": list(item.source_ids),
            }
            for item in result.rejections
        ],
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
