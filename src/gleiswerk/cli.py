"""Command-line interface for Gleiswerk."""

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

import yaml

from gleiswerk.route_compatibility import (
    CompatibilityAnalysisResult,
    IncompatibleControlDeviceRequirement,
    OverlappingExclusiveClaim,
    analyze_route_plans,
)
from gleiswerk.route_compiler import RouteCompilationError, compile_routes
from gleiswerk.topology import (
    ClaimResource,
    JunctionResource,
    ProtectionZoneResource,
    TrackSectionResource,
)
from gleiswerk.topology_config import TopologyConfigurationError, load_topology

_DISTRIBUTION_NAME = "gleiswerk"
_PRODUCT_NAME = "Gleiswerk"


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Gleiswerk command-line interface."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "layout" and arguments.layout_command == "validate":
        return _validate_layout(arguments.file)
    if arguments.command == "layout" and arguments.layout_command == "compatibility":
        return _report_layout_compatibility(arguments.file)
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

    print(yaml.safe_dump(_compatibility_document(analysis), sort_keys=False), end="")
    return 0


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
