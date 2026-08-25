#!/usr/bin/env python3
"""Run the AutoDeduct V1 Saida/TriCera/ISP/Eva/WP pipeline.

The runner deliberately keeps generated files in a separate output directory.
The input C files are read-only from the runner's point of view.
"""

from __future__ import annotations

import argparse
import json
import re
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
        type=float,
        default=300.0,
        help="maximum seconds for each Frama-C stage (default: %(default)s)",
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
        help="C source file(s) or project directory; inputs are never modified",
    )
    return result


# Write generated content into the separate output directory without touching inputs.
def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")


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
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        result.status = "error"
        result.error = f"executable not found: {error.filename}"
        result.returncode = 127
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
            lines = [
                line.strip()
                for stream in (completed.stderr, completed.stdout)
                for line in stream.splitlines()
                if line.strip()
            ]
            diagnostic = next(
                (
                    line
                    for line in lines
                    if re.search(r"fatal error|user error|error:|aborted", line, re.IGNORECASE)
                ),
                lines[-1] if lines else "no diagnostic was written by the command",
            )
            result.error = f"command exited with status {completed.returncode}: {diagnostic}"
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
            options.append(f"-cpp-extra-args=-I{include_path}")
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
            candidates = [path]
        elif path.is_dir():
            candidates = [
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file()
                and candidate.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
                if not any(
                    part in IGNORED_SOURCE_DIRECTORIES
                    or part.startswith("autodeduct-output")
                    for part in candidate.relative_to(path).parts[:-1]
                )
            ]
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
    roots = {path.resolve().parent for path in inputs}
    roots.update(path.resolve() for path in source_roots)
    for source_root in roots:
        if output == source_root or source_root in output.parents:
            raise PipelineError(
                "output",
                f"output directory {output} is inside the input source tree "
                f"{source_root}; choose a separate output directory",
            )


# Remove only known AutoDeduct artifacts so a failed stage cannot reuse a previous run.
def prepare_output_directory(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_OUTPUT_NAMES:
        artifact = output_dir / name
        if artifact.is_symlink() or artifact.is_file():
            artifact.unlink()
        elif artifact.exists():
            raise PipelineError(
                "output",
                f"generated artifact path is not a regular file: {artifact}; "
                "choose another output directory",
            )


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
    for item in items:
        if isinstance(item, str) and item.strip():
            names.append(item)
            continue
        if isinstance(item, dict):
            name = item.get("function") or item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name)
                continue
        raise PipelineError(
            "contract-check",
            f"ISP report {path.name} contains a malformed missing-helper entry; "
            "each entry must be a non-empty function name or an object with a "
            "non-empty 'function' or 'name' field",
        )
    return names


# Detect TriCera fallback warnings that Saida may otherwise hide behind a successful exit code.
def tricera_diagnostic(stage: StageResult) -> str | None:
    """Detect the fallback that Saida otherwise reports only as a warning."""

    if not stage.stderr_file:
        return None
    text = Path(stage.stderr_file).read_text(encoding="utf-8", errors="replace")
    markers = (
        "rosetta error:",
        "TriCera preprocessor (tri-pp) returned an empty file",
    )
    if any(marker in text for marker in markers):
        return "TriCera preprocessing failed; Saida reported a fallback"
    return None


# Check that WP emitted a complete proved-goal summary before accepting verification.
def wp_diagnostic(stage: StageResult) -> str | None:
    """Require WP to print a complete proved-goal summary."""

    if not stage.stdout_file:
        return "WP did not produce a stdout log"
    text = Path(stage.stdout_file).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"Proved goals:\s*(\d+)\s*/\s*(\d+)", text)
    if not match:
        return "WP did not produce a proved-goals summary"
    proved, total = (int(value) for value in match.groups())
    if proved != total:
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
    inputs = source_paths(args.sources)
    output_dir = Path(args.output_dir).expanduser().resolve()
    input_roots = []
    for value in args.sources:
        source = Path(value).expanduser().resolve()
        input_roots.append(source if source.is_dir() else source.parent)
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
    tri_warning = tricera_diagnostic(saida) if saida.status == "passed" else None
    if tri_warning:
        saida.status = "failed"
        saida.error = tri_warning
    if saida.status != "passed" or not inferred.is_file():
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
    if isp.status != "passed" or not verified_source.is_file():
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
        if not any(error["stage"] == "output" for error in report.errors):
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
