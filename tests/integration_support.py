"""Shared assertions for Docker-based AutoDeduct integration regressions."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
RUN_INTEGRATION = os.environ.get("AUTODEDUCT_RUN_INTEGRATION") == "1"
IMAGE = os.environ.get("AUTODEDUCT_IMAGE", "auto-deduct:latest")
TIMEOUT_SECONDS = int(os.environ.get("AUTODEDUCT_INTEGRATION_TIMEOUT", "1800"))
INTEGRATION_SKIP_REASON = (
    "set AUTODEDUCT_RUN_INTEGRATION=1 after building an AutoDeduct Docker image"
)


@dataclass
class PipelineRun:
    """The CLI result and its machine-readable report for one source input."""

    returncode: int
    report: dict
    output: str


class DockerPipelineTestCase(unittest.TestCase):
    """Run one public source through the real image and inspect its report."""

    def run_autodeduct(
        self,
        source: str,
        entry_point: str,
        frama_c_options: Sequence[str] = (),
    ) -> PipelineRun:
        """Run the CLI on a read-only source mount and return its result."""
        self.assertIsNotNone(
            shutil.which("docker"), "Docker is required for the integration test"
        )
        source_path = (ROOT / source).resolve()
        self.assertTrue(source_path.exists(), f"missing integration source: {source}")
        relative_source = source_path.relative_to(ROOT)

        with tempfile.TemporaryDirectory(prefix="autodeduct-integration-") as temp:
            output = Path(temp)
            # The image runs as its unprivileged dev user, so its mounted output
            # directory must be writable regardless of the host test-user id.
            output.chmod(0o777)
            command = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{ROOT}:/work:ro",
                "-v",
                f"{output}:/output",
                "-w",
                "/work",
                IMAGE,
                "autodeduct",
                "--entry-point",
                entry_point,
            ]
            command.extend(
                f"--frama-c-option={option}" for option in frama_c_options
            )
            command.extend(
                ["--output-dir", "/output", f"/work/{relative_source}"]
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
            output_text = "\n".join(
                part for part in (result.stdout, result.stderr) if part
            )

            report_file = output / "report.json"
            self.assertTrue(report_file.is_file(), output_text)
            report = json.loads(report_file.read_text(encoding="utf-8"))
            return PipelineRun(result.returncode, report, output_text)

    def assert_complete_verification(self, run: PipelineRun) -> None:
        """Require every mandatory stage to finish with no missing contracts."""
        self.assertEqual(run.returncode, 0, run.output)
        report = run.report
        self.assertEqual(report["status"], "passed", report)
        stages = {stage["name"]: stage for stage in report["stages"]}
        self.assertTrue(
            {"parse", "saida_tricera", "isp_eva", "contract_check", "wp"}
            <= stages.keys(),
            report,
        )
        self.assertEqual(stages["parse"]["status"], "passed")
        self.assertIn(stages["saida_tricera"]["status"], {"passed", "warning"})
        self.assertIn(stages["isp_eva"]["status"], {"passed", "warning"})
        self.assertEqual(stages["contract_check"]["status"], "passed")
        self.assertEqual(stages["wp"]["status"], "passed")
        self.assertEqual(report["contract_report"]["missing_contracts"], [])

    def assert_verified_with_warning(
        self, run: PipelineRun, stage_name: str, warning_code: str
    ) -> None:
        """Require a visible warning while the final proof still succeeds."""
        self.assert_complete_verification(run)
        stages = {stage["name"]: stage for stage in run.report["stages"]}
        stage = stages[stage_name]
        self.assertEqual(stage["status"], "warning")
        self.assertIn(warning_code, stage["error"] or "")

    def assert_expected_failure(
        self, run: PipelineRun, stage_name: str, diagnostic: str
    ) -> None:
        """Require a safe pipeline failure with a stable first-stage reason."""
        self.assertEqual(run.returncode, 1, run.output)
        self.assertEqual(run.report["status"], "failed", run.report)
        errors = [
            error["message"]
            for error in run.report["errors"]
            if error.get("stage") == stage_name
        ]
        self.assertTrue(errors, run.report)
        self.assertTrue(
            any(diagnostic in message for message in errors),
            {"expected": diagnostic, "errors": errors},
        )
