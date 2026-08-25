import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "autodeduct_pipeline.py"
SPEC = importlib.util.spec_from_file_location("autodeduct_pipeline", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AutoDeductPipelineTests(unittest.TestCase):
    def test_missing_contract_names_come_from_isp_report(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / MODULE.MISSING_CONTRACT_OUTPUT
            report.write_text(
                json.dumps({"missing_helper_contracts": ["helper_a", "helper_b"]}),
                encoding="utf-8",
            )

            self.assertEqual(
                MODULE.missing_contract_names(report), ["helper_a", "helper_b"]
            )

    def test_include_paths_are_forwarded_to_the_c_preprocessor(self):
        args = MODULE.parser().parse_args(["--include", "include", "example.c"])

        self.assertIn(
            f"-cpp-extra-args=-I{Path('include').resolve()}",
            MODULE.command_options(args),
        )

    def test_directory_inputs_expand_c_files_and_skip_generated_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src" / "nested").mkdir()
            (root / "build").mkdir()
            (root / "autodeduct-output").mkdir()
            (root / "src" / "main.c").write_text("int main(void) { return 0; }\n")
            (root / "src" / "nested" / "helper.c").write_text("void helper(void) {}\n")
            (root / "build" / "generated.c").write_text("void generated(void) {}\n")
            (root / "autodeduct-output" / "out.c").write_text("void output(void) {}\n")

            paths = MODULE.source_paths([str(root)])

            self.assertEqual(
                paths,
                [
                    (root / "src" / "main.c").resolve(),
                    (root / "src" / "nested" / "helper.c").resolve(),
                ],
            )

    def test_directory_inputs_accept_uppercase_c_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "UPPER.C"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            self.assertEqual(MODULE.source_paths([temp]), [source.resolve()])

    def test_output_directory_cannot_be_inside_input_source_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = project / "results"

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.validate_output_directory([source], output)

            self.assertEqual(raised.exception.stage, "output")
            self.assertIn("inside the input source tree", raised.exception.message)

            with self.assertRaises(MODULE.PipelineError):
                MODULE.validate_output_directory([source], output, [project])

    def test_cli_does_not_write_report_to_an_unsafe_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = project / "results"

            with patch.object(MODULE, "print_human_report"):
                result = MODULE.main(
                    ["--output-dir", str(output), str(project)]
                )

            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_prepare_output_directory_removes_only_known_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            stale = output / MODULE.SAIDA_OUTPUT
            user_file = output / "keep.txt"
            stale.write_text("old generated source\n", encoding="utf-8")
            (output / "parse.stderr.log").write_text("old log\n", encoding="utf-8")
            user_file.write_text("keep me\n", encoding="utf-8")

            MODULE.prepare_output_directory(output)

            self.assertFalse(stale.exists())
            self.assertFalse((output / "parse.stderr.log").exists())
            self.assertTrue(user_file.exists())

    def test_directory_without_c_files_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.source_paths([temp])

            self.assertEqual(raised.exception.stage, "input")
            self.assertIn("no C source files", raised.exception.message)

    def test_source_directories_are_forwarded_for_generated_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "main.c"
            source.write_text("int main(void) { return 0; }\n")
            args = MODULE.parser().parse_args([str(source)])

            self.assertIn(
                f"-cpp-extra-args=-I{source.parent}",
                MODULE.command_options(args, [source]),
            )

    def test_missing_isp_report_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / MODULE.MISSING_CONTRACT_OUTPUT

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.missing_contract_names(report)

            self.assertEqual(raised.exception.stage, "contract-check")
            self.assertIn("did not produce", raised.exception.message)

    def test_malformed_isp_missing_helper_entry_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / MODULE.MISSING_CONTRACT_OUTPUT
            report.write_text(
                json.dumps({"missing_helper_contracts": [{"unexpected": "value"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.missing_contract_names(report)

            self.assertEqual(raised.exception.stage, "contract-check")
            self.assertIn("malformed missing-helper entry", raised.exception.message)

    def test_cli_runs_all_stages_and_keeps_missing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            source = project / "example.c"
            source.write_text(
                "/*@ ensures result == 1; */\n"
                "int main(void) { return helper(); }\n"
                "int helper(void) { return 1; }\n",
                encoding="utf-8",
            )
            output = Path(temp) / "results"
            args = MODULE.parser().parse_args(
                ["--output-dir", str(output), str(source)]
            )
            commands = []

            def fake_run(command, cwd, **_kwargs):
                commands.append(command)
                if "-saida" in command:
                    (Path(cwd) / MODULE.SAIDA_OUTPUT).write_text(
                        source.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                if "-isp" in command:
                    (Path(cwd) / MODULE.ISP_OUTPUT).write_text(
                        source.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    (Path(cwd) / MODULE.MISSING_CONTRACT_OUTPUT).write_text(
                        json.dumps({"missing_helper_contracts": ["helper"]}),
                        encoding="utf-8",
                    )
                stdout = "Proved goals: 1 / 1\n" if "-wp" in command else "ok\n"
                return MODULE.subprocess.CompletedProcess(command, 0, stdout, "")

            with patch.object(MODULE.shutil, "which", return_value="/usr/bin/fake"), patch.object(
                MODULE.subprocess, "run", side_effect=fake_run
            ):
                report = MODULE.run_pipeline(args)

            self.assertEqual(report.status, "failed")
            self.assertEqual([stage.name for stage in report.stages], [
                "parse", "saida_tricera", "isp_eva", "contract_check", "wp"
            ])
            self.assertEqual(report.contract_report.missing_contracts, ["helper"])
            self.assertEqual(report.contract_report.source, "ISP")
            isp_command = commands[2]
            self.assertIn("-isp-missing-helper-contracts", isp_command)
            self.assertIn("-isp-missing-helper-contracts-json", isp_command)
            self.assertEqual(source.read_text(encoding="utf-8").count("helper"), 2)

    def test_pipeline_stops_when_isp_does_not_write_contract_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            source = project / "example.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = Path(temp) / "results"
            args = MODULE.parser().parse_args(
                ["--output-dir", str(output), str(source)]
            )

            def fake_run(command, cwd, **_kwargs):
                if "-saida" in command:
                    (Path(cwd) / MODULE.SAIDA_OUTPUT).write_text(
                        source.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                if "-isp" in command:
                    (Path(cwd) / MODULE.ISP_OUTPUT).write_text(
                        source.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                return MODULE.subprocess.CompletedProcess(command, 0, "ok\n", "")

            with patch.object(MODULE.shutil, "which", return_value="/usr/bin/fake"), patch.object(
                MODULE.subprocess, "run", side_effect=fake_run
            ):
                report = MODULE.run_pipeline(args)

            self.assertEqual(report.status, "failed")
            self.assertEqual(
                [stage.name for stage in report.stages],
                ["parse", "saida_tricera", "isp_eva"],
            )
            self.assertIn("did not produce", report.errors[0]["message"])

    def test_stage_failure_keeps_actionable_stderr(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            completed = MODULE.subprocess.CompletedProcess(
                ["frama-c"], 2, "", "error: missing header\n"
            )
            with patch.object(MODULE.subprocess, "run", return_value=completed):
                result = MODULE.run_stage(
                    name="parse",
                    description="parse",
                    command=["frama-c"],
                    cwd=output,
                    output_dir=output,
                    timeout=1,
                )

            self.assertEqual(result.status, "failed")
            self.assertIn("missing header", result.error)

    def test_stage_failure_uses_stdout_when_stderr_is_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            completed = MODULE.subprocess.CompletedProcess(
                ["frama-c"], 1, "[kernel] User Error: invalid option\n", ""
            )
            with patch.object(MODULE.subprocess, "run", return_value=completed):
                result = MODULE.run_stage(
                    name="parse",
                    description="parse",
                    command=["frama-c"],
                    cwd=output,
                    output_dir=output,
                    timeout=1,
                )

            self.assertIn("User Error: invalid option", result.error)

    def test_wp_requires_all_goals_to_be_proved(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            log = output / "wp.stdout.log"
            log.write_text("Proved goals:   3 / 4\n", encoding="utf-8")
            stage = MODULE.StageResult(
                name="wp",
                description="wp",
                status="passed",
                stdout_file=str(log),
            )

            self.assertEqual(MODULE.wp_diagnostic(stage), "WP proved 3 of 4 goals")

    def test_tricera_fallback_is_not_a_clean_result(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            log = output / "saida.stderr.log"
            log.write_text(
                "Warning: TriCera preprocessor (tri-pp) returned an empty file",
                encoding="utf-8",
            )
            stage = MODULE.StageResult(
                name="saida_tricera",
                description="saida",
                status="passed",
                stderr_file=str(log),
            )

            self.assertIn("fallback", MODULE.tricera_diagnostic(stage))


if __name__ == "__main__":
    unittest.main()
