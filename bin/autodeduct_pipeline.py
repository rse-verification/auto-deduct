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
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


VERSION = "1.0.0"
SAIDA_OUTPUT = "inferred.c"
ISP_OUTPUT = "out.c"
MISSING_CONTRACT_OUTPUT = "missing-helper-contracts.json"
IGNORED_CALL_NAMES = {
    "if",
    "for",
    "while",
    "switch",
    "sizeof",
    "_Alignof",
    "_Generic",
    "_Static_assert",
}


class PipelineError(Exception):
    """A user-facing error with a stable stage name."""

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
    functions: list[str]
    reachable_functions: list[str]
    missing_contracts: list[str]
    call_graph: dict[str, list[str]]


@dataclass
class PipelineReport:
    version: str
    status: str
    input_files: list[str]
    output_directory: str
    stages: list[StageResult] = field(default_factory=list)
    contract_report: ContractReport | None = None
    errors: list[dict[str, str]] = field(default_factory=list)


@dataclass
class FunctionInfo:
    name: str
    start: int
    body_start: int
    body_end: int
    has_contract: bool


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
        metavar="SOURCE.c",
        help="one or more C source files; they are never modified",
    )
    return result


def strip_comments_and_literals(source: str) -> str:
    """Replace comments and literals with spaces while preserving newlines."""

    pattern = re.compile(
        r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/)',
        re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        return "".join("\n" if char == "\n" else " " for char in value)

    return pattern.sub(replace, source)


def matching_brace(source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def has_contract_before(source: str, function_start: int) -> bool:
    """Return whether an ACSL block directly precedes the function."""

    acsl = list(re.finditer(r"/\*@.*?\*/", source, re.DOTALL))
    if not acsl:
        return False
    candidates = [match for match in acsl if match.end() <= function_start]
    if not candidates:
        return False
    candidate = candidates[-1]
    between = source[candidate.end() : function_start]
    between = re.sub(r"//[^\n]*|/\*(?!@).*?\*/", "", between, flags=re.DOTALL)
    between = re.sub(r"^\s*#.*?$", "", between, flags=re.MULTILINE)
    return not between.strip()


def find_functions(source: str) -> dict[str, FunctionInfo]:
    """Find ordinary C function definitions and their directly preceding ACSL."""

    clean = strip_comments_and_literals(source)
    definition = re.compile(
        r"(?P<signature>(?:[A-Za-z_]\w*|\*)[\w\s\*]*?\b"
        r"(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\))\s*\{",
        re.MULTILINE,
    )
    functions: dict[str, FunctionInfo] = {}
    for match in definition.finditer(clean):
        name = match.group("name")
        if name in IGNORED_CALL_NAMES or name in functions:
            continue
        body_start = clean.find("{", match.start(), match.end())
        body_end = matching_brace(clean, body_start)
        if body_end < 0:
            continue
        functions[name] = FunctionInfo(
            name=name,
            start=match.start(),
            body_start=body_start,
            body_end=body_end,
            has_contract=has_contract_before(source, match.start()),
        )
    return functions


def build_call_graph(source: str, functions: dict[str, FunctionInfo]) -> dict[str, list[str]]:
    clean = strip_comments_and_literals(source)
    known = set(functions)
    graph: dict[str, list[str]] = {}
    call = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    for function in functions.values():
        body = clean[function.body_start + 1 : function.body_end]
        calls: list[str] = []
        for match in call.finditer(body):
            name = match.group(1)
            if name in known and name != function.name and name not in calls:
                calls.append(name)
        graph[function.name] = calls
    return graph


def contract_report(source: str, entry_point: str) -> ContractReport:
    functions = find_functions(source)
    graph = build_call_graph(source, functions)
    if entry_point not in functions:
        raise PipelineError(
            "contract-check",
            f"entry point '{entry_point}' was not found in the generated C source",
        )
    reachable: list[str] = []
    pending = deque([entry_point])
    while pending:
        current = pending.popleft()
        if current in reachable:
            continue
        reachable.append(current)
        pending.extend(graph.get(current, []))
    missing = [name for name in reachable if not functions[name].has_contract]
    return ContractReport(
        entry_point=entry_point,
        functions=sorted(functions),
        reachable_functions=reachable,
        missing_contracts=missing,
        call_graph=graph,
    )


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")


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
            diagnostic = next(
                (line.strip() for line in reversed(completed.stderr.splitlines()) if line.strip()),
                "no diagnostic was written to stderr",
            )
            result.error = f"command exited with status {completed.returncode}: {diagnostic}"
        result.stdout_file = str(output_dir / f"{name}.stdout.log")
        result.stderr_file = str(output_dir / f"{name}.stderr.log")
    result.duration_seconds = time.monotonic() - started
    if artifact and artifact.exists():
        result.artifact = str(artifact)
    return result


def command_options(args: argparse.Namespace) -> list[str]:
    options = ["-main", args.entry_point]
    for include in args.include:
        options.extend(["-I", str(Path(include).expanduser().resolve())])
    options.extend(args.frama_c_option)
    return options


def source_paths(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise PipelineError("input", f"source file does not exist: {value}")
        paths.append(path)
    return paths


def report_dict(report: PipelineReport) -> dict:
    return asdict(report)


def persist_report(report: PipelineReport) -> None:
    """Always leave the machine-readable report beside the stage logs."""

    output_dir = Path(report.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "report.json", json.dumps(report_dict(report), indent=2) + "\n")


def missing_contract_names(path: Path) -> list[str] | None:
    """Read the ISP JSON report while tolerating its small format variations."""

    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, dict):
        return None
    for key in (
        "missing_contracts",
        "missing_helpers",
        "missing_helper_contracts",
        "missing",
    ):
        items = value.get(key)
        if isinstance(items, list):
            names: list[str] = []
            for item in items:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("function") or item.get("name")
                    if name is not None:
                        names.append(str(name))
            return names
    return None


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


def run_pipeline(args: argparse.Namespace) -> PipelineReport:
    inputs = source_paths(args.sources)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
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

    options = command_options(args)
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

    try:
        contracts = contract_report(inferred.read_text(encoding="utf-8", errors="replace"), args.entry_point)
        report.contract_report = contracts
        write_text(output_dir / "contracts.json", json.dumps(asdict(contracts), indent=2) + "\n")
        contract_stage = StageResult(
            name="contract_check",
            description="Check contracts on functions reachable from the entry point",
            status="warning" if contracts.missing_contracts else "passed",
            artifact=str(output_dir / "contracts.json"),
            error=(
                "missing contracts: " + ", ".join(contracts.missing_contracts)
                if contracts.missing_contracts
                else None
            ),
        )
        report.stages.append(contract_stage)
    except PipelineError as error:
        report.errors.append({"stage": error.stage, "message": error.message})
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

    plugin_missing = missing_contract_names(output_dir / MISSING_CONTRACT_OUTPUT)
    if plugin_missing is not None and report.contract_report is not None:
        report.contract_report.missing_contracts = plugin_missing
        write_text(
            output_dir / "contracts.json",
            json.dumps(asdict(report.contract_report), indent=2) + "\n",
        )

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
