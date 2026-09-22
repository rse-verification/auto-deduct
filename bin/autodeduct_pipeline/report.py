"""Report data models, serialization, and human-readable summaries."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .stages import PipelineError, StageResult, write_text


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
    schema_version: int = 1


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
            "contract_check",
            f"ISP did not produce the required report: {path.name}",
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PipelineError(
            "contract_check",
            f"could not read ISP report {path.name}: {error}",
        ) from error
    except json.JSONDecodeError as error:
        raise PipelineError(
            "contract_check",
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
                "contract_check",
                f"ISP report {path.name} has no missing-helper-contracts field",
            )
    else:
        raise PipelineError(
            "contract_check",
            f"ISP report {path.name} must contain an object or list",
        )

    if not isinstance(items, list):
        raise PipelineError(
            "contract_check",
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
            "contract_check",
            f"ISP report {path.name} contains a malformed missing-helper entry; "
            "each entry must be a non-empty function name or an object with a "
            "non-empty 'function' or 'name' field",
        )
    return names


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


__all__ = [
    "ContractReport",
    "PipelineReport",
    "report_dict",
    "persist_report",
    "missing_contract_names",
    "print_human_report",
]
