"""Command-line interface for Gleiswerk."""

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Gleiswerk command-line interface."""
    arguments = build_parser().parse_args(argv)
    if arguments.command == "layout" and arguments.layout_command == "validate":
        return _validate_layout(arguments.file)
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
