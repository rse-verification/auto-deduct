"""Pipeline orchestration: run the V1 stage sequence and the CLI entry point."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .cli import VERSION, parser, validate_forwarded_options
from .diagnostics import (
    isp_limit_diagnostic,
    isp_partial_diagnostic,
    saida_partial_diagnostic,
    tricera_diagnostic,
    tricera_preprocessing_warning,
    wp_diagnostic,
)
from .report import (
    ContractReport,
    PipelineReport,
    missing_contract_names,
    persist_report,
    print_human_report,
    report_dict,
)
from .stages import (
    ISP_OUTPUT,
    MISSING_CONTRACT_OUTPUT,
    SAIDA_OUTPUT,
    SUPPORTED_SOURCE_SUFFIXES,
    PipelineError,
    StageResult,
    command_options,
    invalidate_stale_report,
    prepare_output_directory,
    run_stage,
    source_paths,
    validate_output_directory,
    write_text,
)


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


__all__ = ["run_pipeline", "main"]
