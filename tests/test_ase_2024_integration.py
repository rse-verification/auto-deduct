"""Opt-in end-to-end regression test for the shipped public ASE 2024 example."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_INTEGRATION = os.environ.get("AUTODEDUCT_RUN_INTEGRATION") == "1"
IMAGE = os.environ.get("AUTODEDUCT_IMAGE", "auto-deduct:latest")
TIMEOUT_SECONDS = int(os.environ.get("AUTODEDUCT_INTEGRATION_TIMEOUT", "1800"))


@unittest.skipUnless(
    RUN_INTEGRATION,
    "set AUTODEDUCT_RUN_INTEGRATION=1 after building an AutoDeduct Docker image",
)
class Ase2024IntegrationTests(unittest.TestCase):
    """Exercise the full shipped pipeline instead of mocked stage orchestration."""

    def test_public_ase_2024_example_proves_end_to_end(self):
        """Require the public example to produce a complete verified report."""
        self.assertIsNotNone(
            shutil.which("docker"), "Docker is required for the integration test"
        )

        with tempfile.TemporaryDirectory(prefix="autodeduct-ase-2024-") as temp:
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
                "main",
                "--output-dir",
                "/output",
                "/work/examples/ase-2024",
            ]
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
            self.assertEqual(result.returncode, 0, output_text)

            report_file = output / "report.json"
            self.assertTrue(report_file.is_file(), output_text)
            report = json.loads(report_file.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed", report)

            stages = {stage["name"]: stage for stage in report["stages"]}
            self.assertEqual(stages["parse"]["status"], "passed")
            self.assertIn(stages["saida_tricera"]["status"], {"passed", "warning"})
            self.assertIn(stages["isp_eva"]["status"], {"passed", "warning"})
            self.assertEqual(stages["contract_check"]["status"], "passed")
            self.assertEqual(stages["wp"]["status"], "passed")
            self.assertEqual(report["contract_report"]["missing_contracts"], [])
