"""Run AcTa once and import its verification report."""

import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .report import CBMCReport
from .runtime import (docker_run_options, in_container, resolve_image,
                      run_container_stage, validate_mount_path)
from .stages import PipelineError, command_options

HARNESS_OUTPUT = "acta-harness.c"
CBMC_OUTPUT = "cbmc.json"
REPORT_OUTPUT = "acta-report.json"


def protect_acta_runtime(args, output_dir):
    """Resolve local tools and protect them before any output cleanup."""
    if args.mode != "acta" or args.acta_runtime != "local":
        return
    args.acta_frama_c = args.acta_frama_c or "frama-c"
    for option in ("acta_frama_c", "cbmc", "acta_plugin"):
        value = getattr(args, option)
        if not value:
            continue
        path = Path(value).expanduser()
        executable = str(path) if option == "acta_plugin" else shutil.which(str(path))
        if executable:
            path = Path(executable).resolve()
            if output_dir == path or output_dir in path.parents:
                raise PipelineError("input", "AcTa and CBMC runtime files must be outside the output directory")
            setattr(args, option, str(path))


def validate_acta_options(args, output_dir):
    if args.mode != "acta":
        if args.cbmc_option:
            raise PipelineError("input", "--cbmc-option requires acta mode")
        return
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", args.entry_point):
        raise PipelineError("input", "AcTa's entry point must be a C function identifier")
    if args.wp_option or args.wp_rte:
        raise PipelineError("input", "WP options are not used in acta mode; use --cbmc-option for CBMC checks")
    if args.acta_runtime == "docker":
        if in_container():
            raise PipelineError("input", "launch --acta-runtime docker on the host; use --acta-runtime local inside the image")
        if os.name != "posix":
            raise PipelineError("input", "Docker AcTa mode requires POSIX host paths; use WSL on Windows")
        if shutil.which("docker") is None:
            raise PipelineError("input", "--acta-runtime docker requires Docker on the host PATH")
        if not args.acta_docker_image or args.acta_docker_image.startswith("-"):
            raise PipelineError("input", "--acta-docker-image must name a verifier image")
        if args.acta_plugin:
            raise PipelineError("input", "--acta-plugin is for local execution; install AcTa in the selected Docker image")
        for path in [output_dir, *(Path(value).expanduser().resolve() for value in args.include)]:
            validate_mount_path(path)
        return
    if args.acta_plugin and not Path(args.acta_plugin).is_file():
        raise PipelineError("input", f"AcTa plugin not found: {args.acta_plugin}")


def acta_command(args, source, output_dir, image_id, command):
    if args.acta_runtime == "local":
        return command, None
    name = f"autodeduct-acta-{uuid.uuid4().hex}"
    wrapped = docker_run_options(args.acta_docker_platform, name)
    roots = {source.parent, *(Path(value).expanduser().resolve() for value in args.include)}
    for root in sorted(roots, key=str):
        validate_mount_path(root)
        if not root.is_dir():
            raise PipelineError("input", f"include/source directory does not exist: {root}")
        wrapped += ["--mount", f"type=bind,source={root},target={root},readonly"]
    return [*wrapped, "--mount", f"type=bind,source={output_dir},target={output_dir}",
            "--workdir", str(output_dir), image_id, *command], name


def import_acta_report(path, args):
    result = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(result, dict) or type(result.get("schema_version")) is not int
            or result["schema_version"] != 1
            or result.get("entry_point") != args.entry_point
            or result.get("harness_function") != f"acta_harness_{args.entry_point}"
            or type(result.get("unwind")) is not int or result["unwind"] != args.cbmc_unwind):
        raise ValueError("missing, unsupported or mismatched AcTa report")
    if result.get("status") == "error":
        raise ValueError(result.get("error") or "AcTa verification failed")
    total, proved, failed = (result.get(key) for key in ("properties", "proved", "failed_properties"))
    if (result.get("status") not in ("passed", "failed")
            or type(total) is not int or type(proved) is not int or not 0 <= proved <= total
            or total == 0 or not isinstance(failed, list)
            or any(not isinstance(name, str) for name in failed)
            or len(failed) != total - proved
            or type(result.get("cbmc_exit_code")) is not int):
        raise ValueError("malformed AcTa verification summary")
    return result, CBMCReport(
        entry_point=result["entry_point"], harness_function=result["harness_function"],
        unwind=result["unwind"], properties=total, proved=proved,
        failed_properties=failed, report_file=str(path),
    )


def run_acta_workflow(args, source, output_dir, report):
    docker = args.acta_runtime == "docker"
    frontend = args.acta_frama_c or "frama-c"
    if not docker and shutil.which(frontend) is None:
        report.errors.append({"stage": "environment", "message": f"required AcTa executable not found: {frontend}"})
        return report
    image_id = None
    if docker:
        image_id = resolve_image(args.acta_docker_image, name="acta_image", report=report,
                                 output_dir=output_dir, timeout=args.timeout)
        if image_id is None:
            return report
    result_file = output_dir / REPORT_OUTPUT
    includes = sorted({source.parent, *(Path(value).expanduser().resolve() for value in args.include)}, key=str)
    command = [
        frontend, *(["-load-module", args.acta_plugin] if args.acta_plugin else []),
        *command_options(args, [source]), "-acta", "-acta-run-cbmc",
        "-acta-out", str(output_dir / HARNESS_OUTPUT), "-acta-report", str(result_file),
        "-acta-cbmc-path", args.cbmc, "-acta-cbmc-out", str(output_dir / CBMC_OUTPUT),
        "-acta-cbmc-unwind", str(args.cbmc_unwind), "-acta-cbmc-args",
        json.dumps([*args.cbmc_option, *(word for path in includes for word in ("-I", str(path)))]),
        str(source),
    ]
    command, container_name = acta_command(args, source, output_dir, image_id, command)
    stage = run_container_stage(
        name="acta_verify", description="Run AcTa verification and import its report",
        command=command, container_name=container_name, report=report,
        cwd=output_dir, output_dir=output_dir, timeout=args.timeout, artifact=result_file,
    )
    report.stages.append(stage)
    if stage.status not in {"passed", "failed"}:
        report.errors.append({"stage": stage.name, "message": stage.error or "AcTa failed"})
        return report
    try:
        if not result_file.is_file():
            raise ValueError("AcTa did not produce acta-report.json; install the report-enabled AcTa revision")
        result, report.cbmc_report = import_acta_report(result_file, args)
        if (stage.returncode != 0 or result["status"] != "passed"
                or result["cbmc_exit_code"] != 0 or report.cbmc_report.failed_properties):
            raise ValueError(result.get("error") or "AcTa reported a verification failure")
    except (ValueError, OSError) as error:
        stage.status = "failed"
        stage.error = str(error)
        report.errors.append({"stage": stage.name, "message": stage.error})
        return report
    if not report.errors:
        report.status = "passed"
    return report
