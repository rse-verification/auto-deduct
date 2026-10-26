"""Offline checks of the single AcTa invocation and report import."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from autodeduct_pipeline import PipelineError, main, parser, run_pipeline, validate_forwarded_options
from autodeduct_pipeline.acta import validate_acta_options

SOURCE = "/*@ ensures \\result == 1; */\nint main(void) { return 1; }\n"
IMAGE_ID = "sha256:" + "b" * 64


class ActaTests(unittest.TestCase):
    def exercise(self, failure=None, runtime="local"):
        with tempfile.TemporaryDirectory(prefix="acta tests ") as directory:
            root = Path(directory).resolve()
            source = root / "src" / "input with spaces.c"
            source.parent.mkdir()
            source.write_text(SOURCE)
            output = root / "results with spaces"
            output.mkdir()
            for name in ("report.json", "acta-harness.c", "cbmc.json", "acta-report.json"):
                (output / name).write_text("stale")
            args = parser().parse_args([
                "--mode", "acta", "--acta-runtime", runtime, "--cbmc-unwind", "7",
                "--cbmc-option=--trace", "--output-dir", str(output), str(source),
            ])
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                if command[:3] == ["docker", "image", "inspect"]:
                    return subprocess.CompletedProcess(command, 1 if failure == "image" else 0,
                                                       "invalid" if failure == "image_id" else IMAGE_ID, "")
                if runtime == "docker":
                    self.assertEqual(command[:2], ["docker", "run"])
                    self.assertIn(IMAGE_ID, command)
                    self.assertIn("frama-c", command)
                    self.assertIn("--read-only", command)
                    self.assertEqual(command[command.index("--network") + 1], "none")
                    self.assertIn(f"type=bind,source={source.parent},target={source.parent},readonly", command)
                    self.assertIn(f"type=bind,source={output},target={output}", command)
                self.assertIn("-acta-run-cbmc", command)
                self.assertEqual(command[command.index("-acta-report") + 1], str(output / "acta-report.json"))
                self.assertEqual(command[command.index("-acta-cbmc-unwind") + 1], "7")
                extras = json.loads(command[command.index("-acta-cbmc-args") + 1])
                self.assertEqual(extras, ["--trace", "-I", str(source.parent)])
                # AutoDeduct launches only AcTa, never a separate CBMC command.
                self.assertNotIn("--json-ui", command)
                for name in ("acta-harness.c", "cbmc.json", "acta-report.json"):
                    self.assertFalse((output / name).exists())
                if failure == "timeout":
                    raise subprocess.TimeoutExpired(command, 1)
                if failure in {"generate", "no_report"}:
                    return subprocess.CompletedProcess(command, 1 if failure == "generate" else 0, "", "")
                result = {
                    "schema_version": 1, "status": "passed", "entry_point": "main",
                    "harness_function": "acta_harness_main", "unwind": 7,
                    "cbmc_exit_code": 0, "properties": 1, "proved": 1,
                    "failed_properties": [], "error": None,
                }
                if failure in {"unsafe", "false_success", "unwinding"}:
                    result.update(status="failed", cbmc_exit_code=10, proved=0,
                                  failed_properties=["main.unwind.0" if failure == "unwinding" else "acta_harness_main.assertion.1"],
                                  error="CBMC verification failed")
                if failure == "false_success":
                    result["status"] = "passed"
                if failure == "error":
                    result.update(status="error", error="CBMC output is malformed")
                for name, field, value in (("schema", "schema_version", 2), ("entry", "entry_point", "other"),
                                            ("bound", "unwind", 8), ("counts", "proved", 2),
                                            ("empty", "properties", 0), ("types", "proved", True),
                                            ("status_type", "status", ["passed"])):
                    if failure == name:
                        result[field] = value
                (output / "acta-report.json").write_text("bad JSON" if failure == "json" else json.dumps(result))
                return subprocess.CompletedProcess(command, 1 if failure == "unsafe" else 0, "AcTa finished", "")

            with patch("autodeduct_pipeline.acta.in_container", return_value=False), patch(
                "autodeduct_pipeline.acta.shutil.which", side_effect=lambda value: value
            ), patch("autodeduct_pipeline.stages._run_command", side_effect=fake_run), patch(
                "autodeduct_pipeline.runtime.subprocess.run"
            ) as cleanup:
                cleanup.return_value = subprocess.CompletedProcess([], 0, b"", b"")
                report = run_pipeline(args)
                if runtime == "docker" and failure == "timeout":
                    self.assertEqual(cleanup.call_args.args[0][:3], ["docker", "rm", "--force"])
            self.assertEqual(source.read_text(), SOURCE)
            self.assertEqual(report.mode, "acta")
            self.assertIsNone(report.contract_report)
            return report, commands

    def test_local_and_docker_import_the_acta_report(self):
        defaults = parser().parse_args(["input.c"])
        self.assertEqual(defaults.acta_docker_image, defaults.llm_docker_image)
        self.assertEqual(defaults.acta_docker_image, "auto-deduct:latest")
        for runtime in ("local", "docker"):
            with self.subTest(runtime=runtime):
                report, commands = self.exercise(runtime=runtime)
                self.assertEqual(report.status, "passed", report.errors)
                self.assertEqual([stage.name for stage in report.stages],
                                 (["acta_image"] if runtime == "docker" else []) + ["acta_verify"])
                self.assertEqual(report.cbmc_report.proved, 1)
                self.assertEqual(report.cbmc_report.unwind, 7)
                self.assertEqual(len(commands), 2 if runtime == "docker" else 1)

    def test_missing_malformed_or_failed_reports_are_not_success(self):
        for failure in ("generate", "no_report", "timeout", "false_success", "unwinding", "unsafe",
                        "error", "schema", "entry", "bound", "counts", "empty", "types", "status_type", "json"):
            with self.subTest(failure=failure):
                report, commands = self.exercise(failure)
                self.assertEqual(report.status, "failed")
                self.assertEqual(len(commands), 1)
                self.assertEqual(report.errors[-1]["stage"], "acta_verify")

    def test_docker_failures_and_timeouts(self):
        for failure in ("image", "image_id", "timeout", "unsafe"):
            with self.subTest(failure=failure):
                report, _ = self.exercise(failure, runtime="docker")
                self.assertEqual(report.status, "failed")

    def test_owned_acta_options_cannot_be_forwarded(self):
        for option in ("-acta-run-cbmc", "-acta-report=other.json", "-acta-out=other.c", "-no-acta"):
            with self.subTest(option=option), self.assertRaises(PipelineError):
                validate_forwarded_options(parser().parse_args([f"--frama-c-option={option}", "input.c"]))

    def test_wp_options_and_nested_docker_are_rejected(self):
        for words in (["--wp-rte"], ["--wp-option=-wp-prover=qed"], ["--entry-point=bad-name"]):
            args = parser().parse_args(["--mode", "acta", *words, "input.c"])
            with self.assertRaises(PipelineError):
                validate_acta_options(args, Path("output").resolve())
        args = parser().parse_args(["--mode", "acta", "--acta-runtime", "docker", "input.c"])
        with patch("autodeduct_pipeline.acta.in_container", return_value=True), self.assertRaises(PipelineError):
            validate_acta_options(args, Path("output").resolve())

    def test_local_missing_tools_persists_a_failed_cli_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.c"
            source.write_text(SOURCE)
            output = root / "output"
            with patch("autodeduct_pipeline.acta.shutil.which", return_value=None), patch("builtins.print"):
                code = main(["acta", "--json", "--output-dir", str(output), str(source)])
            self.assertEqual(code, 1)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["errors"][0]["stage"], "environment")

    def test_invalid_options_clear_old_success_but_protected_runtime_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.c"
            source.write_text(SOURCE)
            output = root / "output"
            output.mkdir()
            old_report = output / "report.json"
            old_report.write_text("old success")
            with patch("builtins.print"):
                self.assertEqual(main(["acta", "--acta-plugin", str(old_report),
                                       "--output-dir", str(output), str(source)]), 1)
            self.assertEqual(old_report.read_text(), "old success")
            with patch("builtins.print"):
                self.assertEqual(main(["acta", "--entry-point=bad-name",
                                       "--output-dir", str(output), str(source)]), 1)
            self.assertFalse(old_report.exists())


if __name__ == "__main__":
    unittest.main()
