"""Command-line interface for Gleiswerk."""

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from importlib.metadata import version
from itertools import combinations
from pathlib import Path

from gleiswerk.layout_config import LayoutConfigurationError, load_layout
from gleiswerk.route_compatibility import (
    RouteConflict,
    RouteConflictKind,
    compare_routes,
)

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
    validate.add_argument("file", metavar="FILE", help="Path to a layout TOML file.")
    conflicts = layout_commands.add_parser(
        "conflicts", help="Analyze route conflicts in a layout configuration file."
    )
    conflicts.add_argument("file", metavar="FILE", help="Path to a layout TOML file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Gleiswerk command-line interface."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "layout" and arguments.layout_command == "validate":
        return _validate_layout(arguments.file)
    if arguments.command == "layout" and arguments.layout_command == "conflicts":
        return _analyze_route_conflicts(arguments.file)
    return 0


def _validate_layout(file: str) -> int:
    """Validate a layout file and report the result for command-line users."""
    try:
        load_layout(Path(file))
    except LayoutConfigurationError as error:
        print(error, file=sys.stderr)
        return 1

    print(f"Layout is valid: {file}")
    return 0


def _analyze_route_conflicts(file: str) -> int:
    """Report every declared route conflict in a validated layout file."""
    try:
        layout = load_layout(Path(file))
    except LayoutConfigurationError as error:
        print(error, file=sys.stderr)
        return 1

    conflicts = tuple(
        conflict
        for first, second in combinations(layout.routes, 2)
        for conflict in compare_routes(first, second).conflicts
    )
    if not conflicts:
        print(f"No route conflicts: {file}")
        return 0

    print(f"Route conflicts: {file}")
    for conflict in conflicts:
        print(_format_route_conflict(conflict))
    return 2


def _format_route_conflict(conflict: RouteConflict) -> str:
    """Format one stable core conflict explanation for command-line users."""
    first_route, second_route = conflict.routes
    prefix = f"{first_route}, {second_route}:"
    if conflict.kind is RouteConflictKind.SHARED_BLOCK:
        assert conflict.block is not None
        return f"{prefix} shared block {conflict.block}"

    assert conflict.turnout is not None
    assert conflict.required_positions is not None
    first_position, second_position = conflict.required_positions
    return (
        f"{prefix} incompatible turnout {conflict.turnout} "
        f"({first_position}, {second_position})"
    )
