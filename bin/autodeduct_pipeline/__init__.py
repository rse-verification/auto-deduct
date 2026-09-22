#!/usr/bin/env python3
"""Run the AutoDeduct V1 Saida/TriCera/ISP/Eva/WP pipeline.

The runner deliberately keeps generated files in a separate output directory.
The input C files are read-only from the runner's point of view.

The implementation is split by concern:

- `cli`: argument parsing and CLI-owned option validation.
- `stages`: stage execution and source/output path validation.
- `diagnostics`: classification of tool stdout/stderr into stable messages.
- `report`: report data models, serialization, and human-readable summaries.
- `pipeline`: stage orchestration and the CLI entry point.

This module re-exports their public names so existing callers and tests can
keep using `autodeduct_pipeline.<name>`.
"""

from __future__ import annotations

# Re-imported so `autodeduct_pipeline.<stdlib-module>` keeps working for
# callers (including tests) that patch or inspect these shared modules.
import argparse
import os
import shutil
import subprocess

from .cli import (
    PIPELINE_OWNED_OPTIONS,
    VERSION,
    parser,
    positive_timeout,
    validate_forwarded_options,
)
from .diagnostics import (
    diagnostic_payload,
    failure_diagnostic,
    isp_limit_diagnostic,
    isp_partial_diagnostic,
    saida_partial_diagnostic,
    stage_log_text,
    tricera_diagnostic,
    tricera_preprocessing_warning,
    wp_diagnostic,
    wp_loop_diagnostic,
)
from .pipeline import main, run_pipeline
from .report import (
    ContractReport,
    PipelineReport,
    missing_contract_names,
    persist_report,
    print_human_report,
    report_dict,
)
from .stages import (
    GENERATED_OUTPUT_NAMES,
    IGNORED_SOURCE_DIRECTORIES,
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

__all__ = [
    "argparse",
    "os",
    "shutil",
    "subprocess",
    "PIPELINE_OWNED_OPTIONS",
    "VERSION",
    "parser",
    "positive_timeout",
    "validate_forwarded_options",
    "diagnostic_payload",
    "failure_diagnostic",
    "isp_limit_diagnostic",
    "isp_partial_diagnostic",
    "saida_partial_diagnostic",
    "stage_log_text",
    "tricera_diagnostic",
    "tricera_preprocessing_warning",
    "wp_diagnostic",
    "wp_loop_diagnostic",
    "main",
    "run_pipeline",
    "ContractReport",
    "PipelineReport",
    "missing_contract_names",
    "persist_report",
    "print_human_report",
    "report_dict",
    "GENERATED_OUTPUT_NAMES",
    "IGNORED_SOURCE_DIRECTORIES",
    "ISP_OUTPUT",
    "MISSING_CONTRACT_OUTPUT",
    "SAIDA_OUTPUT",
    "SUPPORTED_SOURCE_SUFFIXES",
    "PipelineError",
    "StageResult",
    "command_options",
    "invalidate_stale_report",
    "prepare_output_directory",
    "run_stage",
    "source_paths",
    "validate_output_directory",
    "write_text",
]

if __name__ == "__main__":
    raise SystemExit(main())
