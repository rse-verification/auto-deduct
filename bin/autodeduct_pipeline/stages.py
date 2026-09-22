"""Stage execution and source/output path validation.

Stages are the external analysis processes (Frama-C, Saida/TriCera, ISP/Eva,
WP) that the pipeline runs as subprocesses. This module keeps generated files
in a separate output directory; input C files are always read-only from the
runner's point of view.
"""

from __future__ import annotations

import argparse
import os
import signal
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .diagnostics import failure_diagnostic

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


# Write generated content into the separate output directory without touching inputs.
def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()


def _run_command(
    *, command: Sequence[str], cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            error.cmd,
            error.timeout,
            output=stdout,
            stderr=stderr,
        ) from error
    except BaseException:
        _terminate_process_tree(process)
        process.communicate()
        raise
    return subprocess.CompletedProcess(
        list(command), process.returncode, stdout, stderr
    )


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
        completed = _run_command(
            command=command,
            cwd=cwd,
            timeout=timeout,
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


__all__ = [
    "SAIDA_OUTPUT",
    "ISP_OUTPUT",
    "MISSING_CONTRACT_OUTPUT",
    "IGNORED_SOURCE_DIRECTORIES",
    "SUPPORTED_SOURCE_SUFFIXES",
    "GENERATED_OUTPUT_NAMES",
    "PipelineError",
    "StageResult",
    "write_text",
    "run_stage",
    "command_options",
    "source_paths",
    "validate_output_directory",
    "invalidate_stale_report",
    "prepare_output_directory",
]
