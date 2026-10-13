"""Offline checks of skill delegation and verifier evidence; no model calls."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from autodeduct_pipeline import parser, run_pipeline, PipelineError
from autodeduct_pipeline.llm import validate_annotation_only, validate_llm_options

SOURCE = "int helper(void)\n{\n    return 1;\n}\n/*@ ensures \\result == 1; */\nint main(void)\n{\n    return helper();\n}\n"
ANNOTATED = "/*@ assigns \\nothing; ensures \\result == 1; */\n" + SOURCE


class LLMModeTests(unittest.TestCase):
    def exercise(self, failure=None, wp="Proved goals: 2 / 2\n", runner="codex exec"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "src" / "input.c"
            source.parent.mkdir()
            source.write_text(SOURCE)
            skill = root / "SKILL.md"
            skill.write_text("Use the test contract skill and its verifier.")
            output = root / "output"
            output.mkdir()
            for artifact in ("llm-verification.json", "llm-contracts.json", "inferred.c"):
                (output / artifact).write_text("stale")
            args = parser().parse_args([
                "--mode", "llm", "--llm-skill", str(skill), "--llm-runner", runner,
                "--wp-rte", "--wp-option=-wp-prover=qed", "--output-dir", str(output), str(source),
            ])
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                self.assertEqual(command[:2], ["codex", "exec"])
                self.assertEqual("--sandbox" in command, "--approve-for-me" not in command)
                self.assertIn(str(skill), command[-1])
                self.assertIn("complete SKILL.md", command[-1])
                self.assertIn("--verify", command[-1])
                self.assertIn("--verification-json", command[-1])
                for artifact in ("llm-verification.json", "llm-contracts.json", "inferred.c"):
                    self.assertFalse((output / artifact).exists())
                if failure == "runner":
                    return subprocess.CompletedProcess(command, 1, "", "agent unavailable")
                if failure == "missing":
                    return subprocess.CompletedProcess(command, 0, "claimed success", "")
                task = json.loads((output / "llm-task.json").read_text())
                self.assertIn("-wp-rte", task["verification_options"])
                self.assertIn("-wp-prover=qed", task["verification_options"])
                (output / "llm-contracts.json").write_text(json.dumps({
                    "format": "acsl-contracts-v2", "contracts": {"helper": {}},
                    "metadata": {"source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest()},
                }))
                content = ANNOTATED.replace("return 1;", "return 2;") if failure == "changed" else ANNOTATED
                (output / "inferred.c").write_text(content)
                evidence = {
                    "schema_version": 1, "returncode": 1 if failure == "verifier" else 0,
                    "source_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "command": ["frama-c", *task["verification_options"], "-wp", task["annotated_source"]],
                    "stdout": wp, "stderr": "",
                }
                if failure == "hash":
                    evidence["source_sha256"] = "0" * 64
                if failure == "options":
                    evidence["command"].remove("-wp-rte")
                if failure == "malformed":
                    evidence["returncode"] = "0"
                (output / "llm-verification.json").write_text(
                    "invalid json" if failure == "json" else json.dumps(evidence)
                )
                return subprocess.CompletedProcess(command, 0, "agent finished", "")

            # No local Frama-C or TriCera is required: the skill owns execution.
            with patch("autodeduct_pipeline.pipeline.shutil.which", return_value=None), patch(
                "autodeduct_pipeline.stages._run_command", side_effect=fake_run
            ):
                report = run_pipeline(args)
            self.assertEqual(source.read_text(), SOURCE)
            self.assertIsNone(report.contract_report)
            self.assertEqual(report.mode, "llm")
            self.assertEqual(len(commands), 1)
            return report

    def test_skill_handles_generation_and_verification_once(self):
        for runner in ("codex exec", "codex exec --approve-for-me"):
            with self.subTest(runner=runner):
                report = self.exercise(runner=runner)
                self.assertEqual(report.status, "passed", report.errors)
                self.assertEqual([stage.name for stage in report.stages], ["llm_workflow", "skill_verify"])

    def test_invalid_results_and_changed_source_never_pass(self):
        for failure in ("runner", "missing", "json", "hash", "verifier", "changed", "options", "malformed"):
            with self.subTest(failure=failure):
                report = self.exercise(failure=failure)
                self.assertEqual(report.status, "failed")
                self.assertTrue(report.errors)

    def test_unproved_zero_or_missing_goals_are_not_success(self):
        for summary in ("Proved goals: 1 / 2\n", "Proved goals: 0 / 0\n", "verification finished"):
            with self.subTest(summary=summary):
                report = self.exercise(wp=summary)
                self.assertEqual(report.status, "failed")
                self.assertEqual(report.errors[-1]["stage"], "skill_verify")

    def test_skill_in_output_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            skill = output / "SKILL.md"
            skill.write_text("keep me")
            args = parser().parse_args(["--mode", "llm", "--llm-skill", str(skill), "--output-dir", str(output), "/unrelated/input.c"])
            with self.assertRaises(PipelineError):
                run_pipeline(args)
            self.assertEqual(skill.read_text(), "keep me")

    def test_default_runner_is_allowed_when_cwd_is_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            skill = root / "SKILL.md"
            skill.write_text("test skill")
            output = root / "output"
            output.mkdir()
            args = parser().parse_args(["--mode", "llm", "--llm-skill", str(skill), "input.c"])
            with patch("os.getcwd", return_value=str(output)):
                validate_llm_options(args, output)
            runner = output / "runner.py"
            runner.write_text("keep me")
            args.llm_runner = f"python3 {runner}"
            with self.assertRaises(PipelineError):
                validate_llm_options(args, output)
            self.assertEqual(runner.read_text(), "keep me")

    def test_old_contracts_option_is_removed(self):
        with self.assertRaises(SystemExit):
            parser().parse_args(["--mode", "llm", "--contracts", "contracts.json", "input.c"])

    def test_annotation_guard_preserves_code_existing_specs_and_strings(self):
        validate_annotation_only(SOURCE, ANNOTATED)
        for candidate in (
            ANNOTATED.replace("return 1;", "return 2;"),
            ANNOTATED.replace("/*@ ensures \\result == 1; */", "/*@ ensures 1; */"),
            "/*@ ensures 1; */\nint injected;\n" + SOURCE,
        ):
            with self.assertRaises(ValueError):
                validate_annotation_only(SOURCE, candidate)
        original = '/* existing\ncomment */\n' + SOURCE
        with self.assertRaises(ValueError):
            validate_annotation_only(original, original.replace('comment */', '/*@ ensures 1; */\ncomment */'))


if __name__ == "__main__":
    unittest.main()
