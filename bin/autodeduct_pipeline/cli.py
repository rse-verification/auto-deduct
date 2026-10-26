"""Command-line interface: argument parsing and CLI-owned validation."""

from __future__ import annotations

import argparse
import math
import os

from .stages import PipelineError

VERSION = "2.0.0-rc.1"

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
    "-acta",
    "-no-acta",
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


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be an integer greater than zero")
    return number


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
                or option.startswith("-acta-")
            ):
                raise PipelineError(
                    "input",
                    f"{cli_name} cannot override pipeline-owned option "
                    f"{option}; use AutoDeduct's dedicated CLI option instead",
                )


# Define the command-line interface and its supported analysis options.
def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="autodeduct",
        usage="%(prog)s [llm|deductive|acta] [options] SOURCE_OR_DIRECTORY",
        description=(
            "Use 'deductive' for Saida/TriCera/ISP/Eva inference and WP, "
            "or 'llm' for the LOGOS skill workflow through Codex. "
            "Use 'acta' to generate a harness from an existing entry contract and check it with CBMC."
        ),
    )
    result.add_argument("--version", action="version", version=f"AutoDeduct {VERSION}")
    result.add_argument("--json", action="store_true", help="print the final report as JSON")
    result.add_argument(
        "--mode", choices=("deductive", "llm", "acta"), default="deductive",
        help="alternative to the llm/deductive/acta command; default: deductive",
    )
    result.add_argument(
        "--llm-skill", default=os.environ.get("AUTODEDUCT_LLM_SKILL"),
        metavar="SKILL_MD", help="local runtime skill (or AUTODEDUCT_LLM_SKILL); Docker extracts its skill from the image",
    )
    result.add_argument(
        "--llm-runner", default=os.environ.get("AUTODEDUCT_LLM_RUNNER", "codex exec"),
        metavar="COMMAND", help="Codex exec command (or AUTODEDUCT_LLM_RUNNER; default: codex exec)",
    )
    result.add_argument(
        "--llm-runtime", choices=("local", "docker"), default="local",
        help="run the LOGOS wrapper locally or in Docker; Codex always runs on the host (default: local)",
    )
    result.add_argument(
        "--llm-docker-image", default="auto-deduct:latest", metavar="IMAGE",
        help="existing local LOGOS verifier image name:tag or ID for --llm-runtime docker; no automatic build or pull (default: %(default)s)",
    )
    result.add_argument(
        "--llm-docker-platform", default="linux/amd64", metavar="PLATFORM",
        help="verifier image platform (default: %(default)s)",
    )
    result.add_argument(
        "--acta-runtime", choices=("local", "docker"), default="local",
        help="run AcTa and CBMC locally or in Docker (default: local)",
    )
    result.add_argument(
        "--acta-docker-image", default="auto-deduct:acta", metavar="IMAGE",
        help="existing local AcTa/CBMC image for --acta-runtime docker; never built or pulled automatically (default: %(default)s)",
    )
    result.add_argument(
        "--acta-docker-platform", default="linux/amd64", metavar="PLATFORM",
        help="AcTa/CBMC image platform (default: %(default)s)",
    )
    result.add_argument(
        "--acta-frama-c", default=os.environ.get("AUTODEDUCT_ACTA_FRAMA_C"), metavar="EXECUTABLE",
        help="AcTa's Frama-C executable (or AUTODEDUCT_ACTA_FRAMA_C); defaults to frama-c locally, acta-frama-c in Docker",
    )
    result.add_argument(
        "--acta-plugin", default=os.environ.get("AUTODEDUCT_ACTA_PLUGIN"), metavar="CMXS",
        help="local AcTa plugin to load explicitly; unnecessary when installed in Frama-C",
    )
    result.add_argument(
        "--cbmc", default=os.environ.get("AUTODEDUCT_CBMC", "cbmc"), metavar="EXECUTABLE",
        help="CBMC executable (or AUTODEDUCT_CBMC; default: cbmc)",
    )
    result.add_argument(
        "--cbmc-unwind", type=positive_integer, default=10, metavar="N",
        help="CBMC loop unwinding bound; unwinding assertions stay enabled (default: %(default)s)",
    )
    result.add_argument(
        "--cbmc-option", action="append", default=[], metavar="OPTION",
        help="CBMC argument passed to AcTa; repeat for separate arguments (see docs/ACTA.md)",
    )
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
            "finite positive maximum seconds for each external stage "
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
