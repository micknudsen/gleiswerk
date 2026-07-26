"""Command-line interface for Gleiswerk."""

from argparse import ArgumentParser
from collections.abc import Sequence
from importlib.metadata import version

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Gleiswerk command-line interface."""
    build_parser().parse_args(argv)
    return 0
