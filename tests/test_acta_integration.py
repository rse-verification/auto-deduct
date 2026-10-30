"""Real AcTa/CBMC checks locally and through the host Docker launcher."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from autodeduct_pipeline import parser, run_pipeline


@contextmanager
def temporary_workspace():
    directory = tempfile.mkdtemp(prefix="acta integration ")
    try:
        yield directory
    finally:
        # Docker Desktop can briefly retain a bind mount after --rm exits.
        for attempt in range(30):
            try:
                shutil.rmtree(directory)
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.1)


class ActaIntegrationCases:
    def exercise(self, code, expected, *, unwind=10, generation_failure=False):
        with temporary_workspace() as directory:
            root = Path(directory).resolve()
            source = root / "input with spaces.c"
            source.write_text(code)
            headers = root / "header directory"
            headers.mkdir()
            (headers / "limit.h").write_text("#define LIMIT 8\n")
            args = parser().parse_args([
                "--mode", "acta", "--acta-runtime", self.runtime,
                "--acta-docker-image", os.environ.get("AUTODEDUCT_IMAGE", "auto-deduct:latest"),
                "--acta-docker-platform", os.environ.get("AUTODEDUCT_PLATFORM", "linux/amd64"),
                "--cbmc-unwind", str(unwind), "--timeout", "120",
                "--entry-point", "compute", "--include", str(headers),
                "--output-dir", str(root / "output with spaces"), str(source),
            ])
            # A host's plugin path is not meaningful inside the verifier image.
            if self.runtime == "docker":
                args.acta_plugin = None
                args.acta_frama_c = None
            report = run_pipeline(args)
            self.assertEqual(report.status, expected, report)
            self.assertEqual(source.read_text(), code)
            if generation_failure:
                self.assertIsNone(report.cbmc_report, report)
            else:
                self.assertIsNotNone(report.cbmc_report, report)
                if expected == "passed":
                    self.assertGreater(report.cbmc_report.proved, 0)
                    self.assertEqual(report.cbmc_report.proved, report.cbmc_report.properties)
                else:
                    self.assertTrue(report.cbmc_report.failed_properties)
            return report

    def test_valid_contract_and_counterexample(self):
        for expected_offset in (1, 2):
            with self.subTest(expected_offset=expected_offset):
                self.exercise(
                    '#include "limit.h"\n'
                    "static int helper(int x) { return x + 1; }\n"
                    f"/*@ requires 0 <= x <= LIMIT; ensures \\result == x + {expected_offset}; */\n"
                    "int compute(int x) { return helper(x); }\n",
                    "passed" if expected_offset == 1 else "failed",
                )

    def test_insufficient_unwinding_is_not_a_success(self):
        code = ("/*@ requires 0 <= n <= 8; ensures \\result == n; */\n"
                "int compute(int n) { int i = 0; while (i < n) ++i; return i; }\n")
        report = self.exercise(code, "failed", unwind=3)
        self.assertTrue(any("unwind" in name for name in report.cbmc_report.failed_properties))
        self.exercise(code, "passed", unwind=12)

    def test_missing_and_unsupported_contracts_stop_generation(self):
        self.exercise("int compute(int x) { return x; }\n", "failed", generation_failure=True)
        self.exercise("/*@ predicate positive(integer x) = x > 0; */\n"
                      "/*@ requires positive(x); ensures \\result == x; */\n"
                      "int compute(int x) { return x; }\n", "failed", generation_failure=True)


@unittest.skipUnless(os.environ.get("AUTODEDUCT_RUN_ACTA_LOCAL") == "1",
                     "set AUTODEDUCT_RUN_ACTA_LOCAL=1 with AcTa and CBMC installed")
class ActaLocalIntegration(ActaIntegrationCases, unittest.TestCase):
    runtime = "local"


@unittest.skipUnless(os.environ.get("AUTODEDUCT_RUN_ACTA_DOCKER") == "1",
                     "set AUTODEDUCT_RUN_ACTA_DOCKER=1 with a prepared verifier image")
class ActaDockerIntegration(ActaIntegrationCases, unittest.TestCase):
    runtime = "docker"


if __name__ == "__main__":
    unittest.main()
