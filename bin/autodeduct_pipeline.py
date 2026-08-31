#!/usr/bin/env python3
"""Run the AutoDeduct V1 Saida/TriCera/ISP/Eva/WP pipeline.

The runner deliberately keeps generated files in a separate output directory.
The input C files are read-only from the runner's point of view.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


VERSION = "1.0.0"
SAIDA_OUTPUT = "inferred.c"
ISP_OUTPUT = "out.c"
MISSING_CONTRACT_OUTPUT = "missing-helper-contracts.json"
IGNORED_SOURCE_DIRECTORIES = frozenset({
    ".git",
    ".hg",
    ".svn",
    "build",
    "_build",
    "dist",
    "node_modules",
})
SUPPORTED_SOURCE_SUFFIXES = frozenset({".c"})
GENERATED_OUTPUT_NAMES = frozenset({
    SAIDA_OUTPUT,
    ISP_OUTPUT,
    MISSING_CONTRACT_OUTPUT,
    "contracts.json",
    "report.json",
    "parse.stdout.log",
    "parse.stderr.log",
    "saida_tricera.stdout.log",
    "saida_tricera.stderr.log",
    "isp_eva.stdout.log",
    "isp_eva.stderr.log",
    "contract_check.stdout.log",
    "contract_check.stderr.log",
    "wp.stdout.log",
    "wp.stderr.log",
})
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


class PipelineError(Exception):
    """A user-facing error with a stable stage name."""

    # Store the failing stage so the CLI can report actionable errors consistently.
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass
class StageResult:
    name: str
    description: str
    command: list[str] = field(default_factory=list)
    status: str = "not-run"
    returncode: int | None = None
    duration_seconds: float = 0.0
    stdout_file: str | None = None
    stderr_file: str | None = None
    artifact: str | None = None
    error: str | None = None


@dataclass
class ContractReport:
    entry_point: str
    missing_contracts: list[str]
    source: str
    report_file: str


@dataclass
class PipelineReport:
    version: str
    status: str
    input_files: list[str]
    output_directory: str
    stages: list[StageResult] = field(default_factory=list)
    contract_report: ContractReport | None = None
    errors: list[dict[str, str]] = field(default_factory=list)


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


# Write generated content into the separate output directory without touching inputs.
def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")


# Turn recurring compiler diagnostics into stable, actionable input messages.
def failure_diagnostic(*, returncode: int, stdout: str, stderr: str) -> str:
    streams = [line.strip() for stream in (stderr, stdout) for line in stream.splitlines()]
    combined = "\n".join(streams)

    entry_point = re.search(
        r"['\"](?P<name>[A-Za-z_]\w*)['\"] is not a defined function",
        combined,
        re.IGNORECASE,
    )
    if entry_point:
        name = entry_point.group("name")
        return (
            f"entry point '{name}' was not found as a function definition in the "
            "input C sources; check --entry-point and ensure the function is defined"
        )

    forward_declaration = re.search(
        r"implicit declaration of function\s+['\"](?P<name>[A-Za-z_]\w*)['\"]",
        combined,
        re.IGNORECASE,
    )
    if forward_declaration:
        name = forward_declaration.group("name")
        return (
            f"function '{name}' is called without a visible declaration; add a "
            "prototype in the source or an included header before running AutoDeduct"
        )

    missing_header = re.search(
        r"(?:fatal error|error):\s*['\"]?(?P<header>[^'\"\s:]+\.h)['\"]?\s*: "
        r"No such file or directory",
        combined,
        re.IGNORECASE,
    )
    if missing_header:
        header = missing_header.group("header")
        return (
            f"required header '{header}' was not found; add its directory with "
            "--include"
        )

    if re.search(r"unterminated (?:comment|string literal)", combined, re.IGNORECASE):
        return (
            "input contains an unterminated C or ACSL comment/string; check the "
            "source delimiters"
        )

    diagnostic = next(
        (
            line
            for line in streams
            if re.search(r"fatal error|user error|error:|aborted", line, re.IGNORECASE)
        ),
        streams[-1] if streams else "no diagnostic was written by the command",
    )
    return f"command exited with status {returncode}: {diagnostic}"


# Execute one external analysis stage and capture its logs, timing, artifacts, and failures.
def run_stage(
    *,
    name: str,
    description: str,
    command: Sequence[str],
    cwd: Path,
    output_dir: Path,
    timeout: float,
    artifact: Path | None = None,
) -> StageResult:
    result = StageResult(
        name=name,
        description=description,
        command=list(command),
        artifact=str(artifact) if artifact else None,
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        result.status = "error"
        result.error = f"executable not found: {error.filename}"
        result.returncode = 127
        completed = None
    except OSError as error:
        result.status = "error"
        result.error = (
            "could not start command: "
            f"{error.strerror or error}"
        )
        result.returncode = error.errno or 1
        completed = None
    except subprocess.TimeoutExpired as error:
        result.status = "timeout"
        result.error = f"stage exceeded timeout of {timeout:g} seconds"
        result.returncode = 124
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        write_text(output_dir / f"{name}.stdout.log", stdout)
        write_text(output_dir / f"{name}.stderr.log", stderr)
        result.stdout_file = str(output_dir / f"{name}.stdout.log")
        result.stderr_file = str(output_dir / f"{name}.stderr.log")
        result.duration_seconds = time.monotonic() - started
        return result

    if completed is not None:
        write_text(output_dir / f"{name}.stdout.log", completed.stdout)
        write_text(output_dir / f"{name}.stderr.log", completed.stderr)
        result.returncode = completed.returncode
        result.status = "passed" if completed.returncode == 0 else "failed"
        if completed.returncode != 0:
            result.error = failure_diagnostic(
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        result.stdout_file = str(output_dir / f"{name}.stdout.log")
        result.stderr_file = str(output_dir / f"{name}.stderr.log")
    result.duration_seconds = time.monotonic() - started
    if artifact and artifact.exists():
        result.artifact = str(artifact)
    return result


# Convert CLI options and source locations into Frama-C arguments for every stage.
def command_options(
    args: argparse.Namespace, inputs: Iterable[Path] = ()
) -> list[str]:
    options = ["-main", args.entry_point]
    include_paths: list[Path] = []
    for include in args.include:
        include_paths.append(Path(include).expanduser().resolve())
    include_paths.extend(path.parent for path in inputs)
    seen: set[Path] = set()
    for include_path in include_paths:
        if include_path not in seen:
            options.append(
                f"-cpp-extra-args=-I{shlex.quote(str(include_path))}"
            )
            seen.add(include_path)
    options.extend(args.frama_c_option)
    return options


# Validate source translation units before starting the external verification tools.
def source_paths(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        path = Path(value).expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
                raise PipelineError(
                    "input",
                    f"unsupported source file type: {value}; provide a .c file "
                    "or a directory containing C source files",
                )
            candidates = [path]
        elif path.is_dir():
            candidates = []

            def discovery_error(error: OSError) -> None:
                raise PipelineError(
                    "input",
                    f"could not read source directory {error.filename}: "
                    f"{error.strerror or error}",
                )

            for current_root, directories, filenames in os.walk(
                path, onerror=discovery_error
            ):
                directories[:] = sorted(
                    directory
                    for directory in directories
                    if directory not in IGNORED_SOURCE_DIRECTORIES
                    and not directory.startswith("autodeduct-output")
                )
                root = Path(current_root)
                for filename in sorted(filenames):
                    candidate = root / filename
                    if (
                        candidate.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
                        and candidate.is_file()
                    ):
                        candidates.append(candidate)
            if not candidates:
                raise PipelineError(
                    "input",
                    f"directory contains no C source files: {value}",
                )
        else:
            raise PipelineError("input", f"source file does not exist: {value}")
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                paths.append(resolved)
                seen.add(resolved)
    return paths


# Keep generated artifacts outside every source tree so the runner cannot overwrite inputs.
def validate_output_directory(
    inputs: Sequence[Path],
    output_dir: Path,
    source_roots: Iterable[Path] = (),
) -> None:
    output = output_dir.resolve()
    if output.exists() and not output.is_dir():
        raise PipelineError(
            "output",
            f"output path is not a directory: {output}",
        )
    for source in inputs:
        source = source.resolve()
        if (
            output == source.parent
            or output in source.parents
            or source in output.parents
        ):
            raise PipelineError(
                "output",
                f"output directory {output} overlaps the input source {source}; "
                "choose a separate output directory",
            )
    for source_root in source_roots:
        source_root = source_root.resolve()
        if (
            output == source_root
            or source_root in output.parents
            or output in source_root.parents
        ):
            raise PipelineError(
                "output",
                f"output directory {output} overlaps the input source tree "
                f"{source_root}; choose a separate output directory",
            )


# Remove an old success report after the requested output location has been
# proven separate from the requested inputs. Other artifacts are cleaned only
# after full source validation.
def invalidate_stale_report(output_dir: Path) -> None:
    output = output_dir.resolve()
    if not output.exists():
        return
    if not output.is_dir():
        raise PipelineError("output", f"output path is not a directory: {output}")
    report = output / "report.json"
    if report.is_symlink() or report.is_file():
        try:
            report.unlink()
        except OSError as error:
            raise PipelineError(
                "output",
                f"could not invalidate stale report {report}: {error}",
            ) from error
    elif report.exists():
        raise PipelineError(
            "output",
            f"generated report path is not a regular file: {report}; "
            "choose another output directory",
        )


# Remove only known AutoDeduct artifacts so a failed stage cannot reuse a previous run.
def prepare_output_directory(output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = [output_dir / name for name in GENERATED_OUTPUT_NAMES]
        for artifact in artifacts:
            if artifact.exists() and not (
                artifact.is_symlink() or artifact.is_file()
            ):
                raise PipelineError(
                    "output",
                    f"generated artifact path is not a regular file: {artifact}; "
                    "choose another output directory",
                )
        for artifact in artifacts:
            if artifact.is_symlink() or artifact.is_file():
                artifact.unlink()
    except PipelineError:
        raise
    except OSError as error:
        raise PipelineError(
            "output",
            f"could not prepare output directory {output_dir}: {error}",
        ) from error


# Convert the typed pipeline result into JSON-serializable data for automation.
def report_dict(report: PipelineReport) -> dict:
    return asdict(report)


# Persist report.json so every run leaves a machine-readable result beside its logs.
def persist_report(report: PipelineReport) -> None:
    """Always leave the machine-readable report beside the stage logs."""

    output_dir = Path(report.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "report.json", json.dumps(report_dict(report), indent=2) + "\n")


# Read ISP's authoritative missing-contract report instead of maintaining a second call graph.
def missing_contract_names(path: Path) -> list[str]:
    """Read ISP's missing-helper report and fail clearly if it is unusable."""

    if not path.is_file():
        raise PipelineError(
            "contract-check",
            f"ISP did not produce the required report: {path.name}",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PipelineError(
            "contract-check",
            f"could not read ISP report {path.name}: {error}",
        ) from error
    except json.JSONDecodeError as error:
        raise PipelineError(
            "contract-check",
            f"ISP report {path.name} is not valid JSON: {error.msg}",
        ) from error
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = None
        for key in (
            "missing_contracts",
            "missing_helpers",
            "missing_helper_contracts",
            "missing",
        ):
            if key in value:
                items = value[key]
                break
        if items is None:
            raise PipelineError(
                "contract-check",
                f"ISP report {path.name} has no missing-helper-contracts field",
            )
    else:
        raise PipelineError(
            "contract-check",
            f"ISP report {path.name} must contain an object or list",
        )

    if not isinstance(items, list):
        raise PipelineError(
            "contract-check",
            f"ISP report {path.name} missing-helper field must be a list",
        )

    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str) and item.strip():
            name = item.strip()
            if name not in seen:
                names.append(name)
                seen.add(name)
            continue
        if isinstance(item, dict):
            name = item.get("function") or item.get("name")
            if isinstance(name, str) and name.strip():
                name = name.strip()
                if name not in seen:
                    names.append(name)
                    seen.add(name)
                continue
        raise PipelineError(
            "contract-check",
            f"ISP report {path.name} contains a malformed missing-helper entry; "
            "each entry must be a non-empty function name or an object with a "
            "non-empty 'function' or 'name' field",
        )
    return names


# Read only the captured tool output used for bounded diagnostic
# classification. AutoDeduct deliberately does not scan C source text to
# guess which unsupported language feature a project contains.
def stage_log_text(stage: StageResult, tool_name: str) -> tuple[str | None, str | None]:
    log_files = [path for path in (stage.stderr_file, stage.stdout_file) if path]
    if not log_files:
        return "", None
    try:
        return (
            "\n".join(
                Path(path).read_text(encoding="utf-8", errors="replace")
                for path in log_files
            ),
            None,
        )
    except OSError as error:
        return None, f"could not inspect {tool_name} logs: {error}"


# Remove common Frama-C/plugin severity prefixes before matching complete
# diagnostic phrases. Anchoring matches to the remaining line avoids treating
# explanatory prose such as "completed without a syntax error" as a failure.
def diagnostic_payload(line: str) -> str:
    payload = line.strip()
    prefix = re.compile(
        r"^(?:\[[^\]\r\n]+\]|user\s+error|fatal\s+error|warning|error)\s*:?\s*",
        re.IGNORECASE,
    )
    for _ in range(8):
        updated = prefix.sub("", payload, count=1)
        if updated == payload:
            break
        payload = updated
    return payload.casefold()


# Detect TriCera backend errors that Saida may otherwise hide behind a successful exit code.
def tricera_diagnostic(stage: StageResult) -> str | None:
    """Reject explicit backend failures hidden behind Saida exit status zero."""

    text, inspection_error = stage_log_text(stage, "Saida/TriCera")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        payload = diagnostic_payload(line)
        unsupported_type = re.match(
            r"^(?:tricera\s*:?\s*)?type\s+(?P<type>.+?)\s+not\s+supported\b",
            payload,
        )
        if unsupported_type:
            type_name = unsupported_type.group("type")
            return (
                f"TriCera reported that type '{type_name}' is not supported; "
                "AutoDeduct V1 will not continue with a fallback type "
                "approximation"
            )
        if re.match(r"^(?:tricera\s*:?\s*)?syntax\s+error\b", payload):
            return (
                "TriCera reported a syntax error in its inference input; no "
                "sound functional contract was produced. Inspect the "
                "Saida/TriCera logs for the unsupported C or ACSL construct"
            )
        if re.match(r"^(?:tricera\s*:?\s*)?not\s+solvable\b", payload) or re.match(
            r"^[\w.$]*exception\s*:\s*not\s+solvable\b", payload
        ):
            return (
                "TriCera reported that the inference problem is not solvable; "
                "no sound functional contract was produced. Inspect the "
                "Saida/TriCera logs and provide the affected contract manually"
            )
    return None


# Preserve TriCera preprocessing fallbacks as visible warnings when Saida still
# writes an inferred source file. ISP, the reachable-contract check, and WP then
# determine whether the resulting proof is complete for the selected input.
def tricera_preprocessing_warning(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "Saida/TriCera")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        payload = diagnostic_payload(line)
        if payload.startswith("rosetta error:") or payload.startswith(
            "tricera preprocessor (tri-pp) returned an empty file"
        ):
            return (
                "TriCera preprocessing reported a fallback; continuing because "
                "Saida produced inferred.c. Review the Saida/TriCera logs and "
                "treat the run as successful only if ISP, contract checking, and "
                "WP also complete"
            )
    return None


# Surface Saida's explicit partial-frame warning while still allowing the
# mandatory downstream WP stage to establish the complete result.
def saida_partial_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "Saida")
    if inspection_error:
        return inspection_error
    assert text is not None
    text = text.casefold()
    if "saida-w001" in text:
        return (
            "Saida preserved a function-level assigns clause without checking "
            "its frame condition; the final WP stage must prove it"
        )
    return None


# Convert ISP's native unsupported-pointer diagnostic into a stable V1
# boundary message. The native code is authoritative; no source regex is used.
def isp_limit_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "ISP")
    if inspection_error:
        return inspection_error
    assert text is not None
    for line in text.splitlines():
        match = re.search(r"\bISP-E005\b(?P<detail>[^\r\n]*)", line, re.IGNORECASE)
        if match:
            detail = match.group("detail").lstrip(" ]:-")
            native_detail = f": {detail}" if detail else ""
            return (
                "ISP rejected an unsupported lvalue, pointer, or array-index "
                f"expression (ISP-E005{native_detail}). Simplify the access "
                "or provide and review the required ACSL validity, separation, "
                "frame, and value annotations manually; WP was not run"
            )
    return None


# ISP documents every ISP-Wxxx diagnostic as evidence that its generated
# auxiliary specification may be incomplete. Keep the diagnostic visible, then
# let contract checking and WP determine whether the selected run still proves.
def isp_partial_diagnostic(stage: StageResult) -> str | None:
    text, inspection_error = stage_log_text(stage, "ISP")
    if inspection_error:
        return inspection_error
    assert text is not None
    codes = sorted(set(re.findall(r"\bISP-W\d{3}\b", text, re.IGNORECASE)))
    if codes:
        return (
            "ISP reported partial auxiliary inference ("
            + ", ".join(code.upper() for code in codes)
            + "); review the input and generated annotations"
        )
    return None


# Recognize explicit WP evidence for missing or insufficient loop annotations.
# This runs only after WP has left goals unresolved, so successful loop goals
# elsewhere in the same log cannot misclassify an unrelated failure.
def wp_loop_diagnostic(text: str) -> bool:
    missing_annotation = re.compile(
        r"^(?:missing|no)\s+loop\s+(?:invariant|assigns|variant)\b"
        r"|^loop\s+(?:invariant|assigns|variant)\b[^\r\n]*\bmissing\b",
        re.IGNORECASE,
    )
    unresolved_loop_goal = re.compile(
        r"\[(?:timeout|unknown|failed|invalid)\][^\r\n]*"
        r"loop_(?:invariant|assigns|variant)(?:_[A-Za-z0-9]+)*\b",
        re.IGNORECASE,
    )
    return any(
        missing_annotation.search(diagnostic_payload(line))
        or unresolved_loop_goal.search(line)
        for line in text.splitlines()
    )


# Check that WP emitted a complete proved-goal summary before accepting verification.
def wp_diagnostic(stage: StageResult) -> str | None:
    """Require WP to print a complete proved-goal summary."""

    if not stage.stdout_file:
        return "WP did not produce a stdout log"
    try:
        stdout = Path(stage.stdout_file).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError as error:
        return f"could not inspect WP output: {error}"
    combined, inspection_error = stage_log_text(stage, "WP")
    if inspection_error:
        return inspection_error
    assert combined is not None
    matches = re.findall(r"Proved goals:\s*(\d+)\s*/\s*(\d+)", stdout)
    if not matches:
        return "WP did not produce a proved-goals summary"
    proved, total = (int(value) for value in matches[-1])
    if total == 0:
        return "WP generated no proof goals"
    if proved != total:
        if wp_loop_diagnostic(combined):
            return (
                f"WP proved {proved} of {total} goals; loop proof obligations "
                "remain unresolved or WP reported missing loop annotations. "
                "AutoDeduct V1 does not infer loop invariants: add and review "
                "loop invariant and loop assigns clauses, plus a loop variant "
                "when termination must be proved"
            )
        unresolved = re.findall(
            r"\[(?P<status>Timeout|Unknown|Failed|Invalid)\]\s+(?P<goal>[^\n]+)",
            stdout,
            re.IGNORECASE,
        )
        if unresolved:
            details = "; ".join(
                f"{status}: {goal.strip()}" for status, goal in unresolved
            )
            return f"WP proved {proved} of {total} goals; unresolved: {details}"
        return f"WP proved {proved} of {total} goals"
    return None


# Print a compact human-readable summary for interactive CLI use.
def print_human_report(report: PipelineReport) -> None:
    print(f"AutoDeduct {report.version}: {report.status.upper()}")
    print(f"Results: {report.output_directory}")
    for stage in report.stages:
        detail = stage.error or stage.description
        print(f"[{stage.status.upper():7}] {stage.name}: {detail}")
    if report.contract_report:
        missing = report.contract_report.missing_contracts
        if missing:
            print("Missing contracts on reachable functions: " + ", ".join(missing))
        else:
            print("Missing contracts on reachable functions: none")
    for error in report.errors:
        print(f"ERROR [{error['stage']}]: {error['message']}", file=sys.stderr)


# Run the Saida/TriCera, ISP/Eva, contract-check, and WP stages in V1 order.
def run_pipeline(args: argparse.Namespace) -> PipelineReport:
    validate_forwarded_options(args)
    output_dir = Path(args.output_dir).expanduser().resolve()
    requested_files = []
    input_roots = []
    for value in args.sources:
        source = Path(value).expanduser().resolve()
        if source.is_dir():
            input_roots.append(source)
        elif source.is_file() or source.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES:
            requested_files.append(source)
        else:
            # A missing path without a supported source suffix is most likely
            # an intended project directory. Treat it conservatively as a
            # source root before invalidating any stale report.
            input_roots.append(source)
    validate_output_directory(requested_files, output_dir, input_roots)
    invalidate_stale_report(output_dir)
    inputs = source_paths(args.sources)
    if len(inputs) != 1:
        raise PipelineError(
            "input",
            "AutoDeduct V1 supports exactly one C translation unit because "
            "Saida source merging is not yet file-aware; provide one .c file "
            "and its headers",
        )
    validate_output_directory(inputs, output_dir, input_roots)
    prepare_output_directory(output_dir)
    report = PipelineReport(
        version=VERSION,
        status="failed",
        input_files=[str(path) for path in inputs],
        output_directory=str(output_dir),
    )

    missing_tools = [tool for tool in ("frama-c", "tri") if shutil.which(tool) is None]
    if missing_tools:
        report.errors.append(
            {
                "stage": "environment",
                "message": "required executable(s) not available on PATH: "
                + ", ".join(missing_tools),
            }
        )
        return report

    options = command_options(args, inputs)
    files = [str(path) for path in inputs]
    parse = run_stage(
        name="parse",
        description="Parse the input C project with Frama-C",
        command=["frama-c", *options, *files],
        cwd=output_dir,
        output_dir=output_dir,
        timeout=args.timeout,
    )
    report.stages.append(parse)
    if parse.status != "passed":
        report.errors.append({"stage": parse.name, "message": parse.error or "parse failed"})
        return report

    saida = run_stage(
        name="saida_tricera",
        description="Infer functional contracts with Saida and its TriCera backend",
        command=[
            "frama-c",
            *options,
            "-saida",
            "-saida-tricera-path",
            "tri",
            f"-saida-out={output_dir / SAIDA_OUTPUT}",
            *files,
        ],
        cwd=output_dir,
        output_dir=output_dir,
        timeout=args.timeout,
        artifact=output_dir / SAIDA_OUTPUT,
    )
    report.stages.append(saida)
    inferred = output_dir / SAIDA_OUTPUT
    tri_failure = (
        tricera_diagnostic(saida)
        if saida.status in {"passed", "failed"}
        else None
    )
    if tri_failure:
        saida.status = "failed"
        saida.error = tri_failure
    elif saida.status == "passed":
        warnings = [
            warning
            for warning in (
                tricera_preprocessing_warning(saida),
                saida_partial_diagnostic(saida),
            )
            if warning
        ]
        if warnings:
            saida.status = "warning"
            saida.error = "\n".join(warnings)
    if saida.status not in {"passed", "warning"} or not inferred.is_file():
        message = saida.error or f"Saida did not produce {SAIDA_OUTPUT}"
        report.errors.append({"stage": saida.name, "message": message})
        return report

    isp = run_stage(
        name="isp_eva",
        description="Infer auxiliary annotations with ISP using Eva abstract states",
        command=[
            "frama-c",
            *options,
            "-isp-entry-point",
            args.entry_point,
            "-isp",
            "-isp-missing-helper-contracts",
            "-isp-missing-helper-contracts-json",
            str(output_dir / MISSING_CONTRACT_OUTPUT),
            str(inferred),
            "-isp-print-file",
            ISP_OUTPUT,
        ],
        cwd=output_dir,
        output_dir=output_dir,
        timeout=args.timeout,
        artifact=output_dir / ISP_OUTPUT,
    )
    report.stages.append(isp)
    verified_source = output_dir / ISP_OUTPUT
    isp_limit = (
        isp_limit_diagnostic(isp)
        if isp.status in {"passed", "failed"}
        else None
    )
    if isp_limit:
        isp.status = "failed"
        isp.error = isp_limit
    elif isp.status == "passed":
        partial_warning = isp_partial_diagnostic(isp)
        if partial_warning:
            isp.status = "warning"
            isp.error = partial_warning
    if isp.status not in {"passed", "warning"} or not verified_source.is_file():
        message = isp.error or f"ISP did not produce {ISP_OUTPUT}"
        report.errors.append({"stage": isp.name, "message": message})
        return report

    try:
        plugin_missing = missing_contract_names(output_dir / MISSING_CONTRACT_OUTPUT)
    except PipelineError as error:
        report.errors.append({"stage": error.stage, "message": error.message})
        return report

    report.contract_report = ContractReport(
        entry_point=args.entry_point,
        missing_contracts=plugin_missing,
        source="ISP",
        report_file=str(output_dir / MISSING_CONTRACT_OUTPUT),
    )
    write_text(
        output_dir / "contracts.json",
        json.dumps(asdict(report.contract_report), indent=2) + "\n",
    )
    contract_stage = StageResult(
        name="contract_check",
        description="Use ISP's reachable-function contract report",
        status="warning" if plugin_missing else "passed",
        artifact=str(output_dir / "contracts.json"),
        error=(
            "missing contracts: " + ", ".join(plugin_missing)
            if plugin_missing
            else None
        )
    )
    report.stages.append(contract_stage)

    wp_options = [*options, *args.wp_option]
    if args.wp_rte:
        wp_options.append("-wp-rte")
    wp = run_stage(
        name="wp",
        description="Check the generated contract and auxiliary annotations with WP",
        command=["frama-c", *wp_options, "-wp", str(verified_source)],
        cwd=output_dir,
        output_dir=output_dir,
        timeout=args.timeout,
    )
    report.stages.append(wp)
    if wp.status == "passed":
        wp_error = wp_diagnostic(wp)
        if wp_error:
            wp.status = "failed"
            wp.error = wp_error
    if wp.status != "passed":
        report.errors.append({"stage": wp.name, "message": wp.error or "WP failed"})
        return report

    if report.contract_report and report.contract_report.missing_contracts:
        report.errors.append(
            {
                "stage": "contract-check",
                "message": "reachable functions are missing contracts",
            }
        )
        return report
    report.status = "passed"
    return report


# Parse arguments, convert failures into reports, and return a CI-friendly exit code.
def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = run_pipeline(args)
    except PipelineError as error:
        report = PipelineReport(
            version=VERSION,
            status="failed",
            input_files=list(args.sources),
            output_directory=str(Path(args.output_dir).expanduser().resolve()),
            errors=[{"stage": error.stage, "message": error.message}],
        )
    except OSError as error:
        report = PipelineReport(
            version=VERSION,
            status="failed",
            input_files=list(args.sources),
            output_directory=str(Path(args.output_dir).expanduser().resolve()),
            errors=[{"stage": "runner", "message": str(error)}],
        )

    try:
        if not any(error["stage"] in {"input", "output"} for error in report.errors):
            persist_report(report)
    except OSError as error:
        report.errors.append({"stage": "report", "message": str(error)})
        report.status = "failed"
    output = json.dumps(report_dict(report), indent=2) if args.json else None
    if output is not None:
        print(output)
    else:
        print_human_report(report)
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
