"""Command-line interface: argument parsing and CLI-owned validation."""

from __future__ import annotations

import argparse
import math

from .stages import PipelineError

VERSION = "1.0.0"

PIPELINE_OWNED_OPTIONS = frozenset({
    "-main",
    "-then",
    "-then-last",
    "-then-on",
    "-wp",
    "-no-wp",
    "-saida",
    "-no-saida",
    "-isp",
    "-no-isp",
})


# Reject non-positive timeouts at argument parsing instead of starting a stage
# that is guaranteed to time out immediately.
def positive_timeout(value: str) -> float:
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a finite number greater than zero"
        )
    return timeout


# Prevent forwarded options from changing the pipeline topology or the
# entry-point recorded in the report.
def validate_forwarded_options(args: argparse.Namespace) -> None:
    for cli_name, values in (
        ("--frama-c-option", args.frama_c_option),
        ("--wp-option", args.wp_option),
    ):
        for value in values:
            option = value.strip().split(maxsplit=1)[0].split("=", 1)[0]
            if (
                option in PIPELINE_OWNED_OPTIONS
                or option.startswith("-saida-")
                or option.startswith("-isp-")
            ):
                raise PipelineError(
                    "input",
                    f"{cli_name} cannot override pipeline-owned option "
                    f"{option}; use AutoDeduct's dedicated CLI option instead",
                )


# Define the V1 command-line interface and its supported analysis options.
def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="autodeduct",
        description=(
            "Run Saida/TriCera contract inference, ISP/Eva auxiliary "
            "inference, and WP verification."
        ),
    )
    result.add_argument("--version", action="version", version=f"AutoDeduct {VERSION}")
    result.add_argument("--json", action="store_true", help="print the final report as JSON")
    result.add_argument(
        "--output-dir",
        default="autodeduct-output",
        help="directory for generated C files, logs, and the report (default: %(default)s)",
    )
    result.add_argument(
        "--entry-point",
        default="main",
        help="contracted entry function to analyse (default: %(default)s)",
    )
    result.add_argument(
        "--timeout",
        type=positive_timeout,
        default=300.0,
        help=(
            "finite positive maximum seconds for each Frama-C stage "
            "(default: %(default)s)"
        ),
    )
    result.add_argument(
        "--frama-c-option",
        action="append",
        default=[],
        metavar="OPTION",
        help="extra Frama-C option; repeat this option when needed",
    )
    result.add_argument(
        "--wp-option",
        action="append",
        default=[],
        metavar="OPTION",
        help="extra WP option; repeat this option when needed",
    )
    result.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="DIRECTORY",
        help="additional C include directory; may be repeated",
    )
    result.add_argument(
        "--wp-rte",
        action="store_true",
        help="also generate WP runtime-error goals",
    )
    result.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE_OR_DIRECTORY",
        help=(
            "one C source file or project directory containing exactly one "
            "C translation unit; inputs are never modified"
        ),
    )
    return result
