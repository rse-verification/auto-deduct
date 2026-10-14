"""Exercise real LOGOS and WP with a fixture runner (no LLM calls).

Set AUTODEDUCT_LOGOS_ROOT to a LOGOS checkout and provide Frama-C on PATH.
"""

import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
from autodeduct_pipeline import parser, run_pipeline

LOGOS = os.environ.get("AUTODEDUCT_LOGOS_ROOT")


@unittest.skipUnless(LOGOS and shutil.which("frama-c"), "set AUTODEDUCT_LOGOS_ROOT and install Frama-C for real LOGOS/WP integration")
class LogosIntegrationTest(unittest.TestCase):
    def test_real_wrapper_evidence_is_accepted_and_incomplete_proof_fails(self):
        for expected_result in (1, 2):
            with self.subTest(expected_result=expected_result), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "input with spaces.c"
                source.write_text(
                    "static inline int helper(void) { return 1; }\n"
                    f"/*@ assigns \\nothing; ensures \\result == {expected_result}; */\n"
                    "int main(void) { return helper(); }\n", encoding="utf-8",
                )
                original = source.read_bytes()
                output = root / "proof"
                runner = shlex.join([sys.executable, str(ROOT / "tests/fixtures/logos_fixture_runner.py")])
                args = parser().parse_args([
                    "--mode", "llm", "--llm-skill", str(Path(LOGOS) / "skill/SKILL.md"),
                    "--llm-runner", runner, "--wp-option=-wp-prover=qed", "--wp-rte",
                    "--output-dir", str(output), str(source),
                ])
                # Offline wrapper test only; production container LLM launches are unsupported.
                with patch("autodeduct_pipeline.llm.in_container", return_value=False):
                    report = run_pipeline(args)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(report.status, "passed" if expected_result == 1 else "failed", report.errors)
                evidence = json.loads((output / "llm-verification.json").read_text())
                self.assertEqual(evidence["returncode"], 0)  # WP also exits zero for unproved goals.
                self.assertEqual(evidence["verified"], expected_result == 1)
                self.assertEqual(evidence["source_sha256"], hashlib.sha256((output / "inferred.c").read_bytes()).hexdigest())
                if expected_result == 1:
                    self.assertEqual([stage.name for stage in report.stages], ["llm_workflow", "logos_verify", "skill_verify"])
                    self.assertEqual(report.stages[-1].status, "passed")


@unittest.skipUnless(LOGOS and os.environ.get("AUTODEDUCT_RUN_LOGOS_DOCKER") == "1",
                     "set AUTODEDUCT_LOGOS_ROOT and AUTODEDUCT_RUN_LOGOS_DOCKER=1 for host/Docker integration")
class LogosDockerIntegrationTest(unittest.TestCase):
    def test_host_launcher_and_real_container_wrapper(self):
        for expected_result in (1, 2):
            with self.subTest(expected_result=expected_result), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                source = root / "input with spaces.c"
                source.write_text(
                    "static inline int helper(void) { return 1; }\n"
                    f"/*@ assigns \\nothing; ensures \\result == {expected_result}; */\n"
                    "int main(void) { return helper(); }\n", encoding="utf-8",
                )
                original = source.read_bytes()
                output = root / "proof with spaces"
                runner = shlex.join([sys.executable, str(ROOT / "tests/fixtures/logos_fixture_runner.py")])
                args = parser().parse_args([
                    "--mode", "llm", "--llm-runtime", "docker",
                    "--llm-skill", str(Path(LOGOS).resolve() / "skill/SKILL.md"),
                    "--llm-runner", runner, "--wp-option=-wp-prover=qed", "--wp-rte",
                    "--output-dir", str(output), str(source),
                ])
                report = run_pipeline(args)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(report.status, "passed" if expected_result == 1 else "failed", report.errors)
                evidence = json.loads((output / "llm-verification.json").read_text())
                self.assertEqual(evidence["returncode"], 0)
                self.assertEqual(evidence["verified"], expected_result == 1)
                self.assertEqual(report.stages[1].command[:2], ["docker", "run"])
                self.assertEqual(report.stages[1].returncode, 0 if expected_result == 1 else 1)
                self.assertEqual(evidence["source_sha256"], hashlib.sha256((output / "inferred.c").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
