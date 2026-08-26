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
    def test_timeout_must_be_finite_and_positive(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(
                MODULE.argparse.ArgumentTypeError
            ):
                MODULE.positive_timeout(value)

    def test_pipeline_owned_framac_option_is_rejected(self):
        args = MODULE.parser().parse_args(
            ["--frama-c-option=-main=other", "example.c"]
        )

        with self.assertRaises(MODULE.PipelineError) as raised:
            MODULE.validate_forwarded_options(args)

        self.assertEqual(raised.exception.stage, "input")
        self.assertIn("pipeline-owned option -main", raised.exception.message)

    def test_pipeline_owned_wp_option_is_rejected(self):
        args = MODULE.parser().parse_args(
            ["--wp-option=-no-wp", "example.c"]
        )

        with self.assertRaises(MODULE.PipelineError) as raised:
            MODULE.validate_forwarded_options(args)

        self.assertEqual(raised.exception.stage, "input")
        self.assertIn("pipeline-owned option -no-wp", raised.exception.message)

    def test_supported_forwarded_options_are_accepted(self):
        args = MODULE.parser().parse_args(
            [
                "--frama-c-option=-cpp-extra-args=-DTEST",
                "--wp-option=-wp-prover=alt-ergo",
                "example.c",
            ]
        )

        MODULE.validate_forwarded_options(args)

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

    def test_missing_contract_names_are_normalized_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / MODULE.MISSING_CONTRACT_OUTPUT
            report.write_text(
                json.dumps(
                    {
                        "missing_helper_contracts": [
                            " helper ",
                            {"function": "helper"},
                            {"name": "other"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                MODULE.missing_contract_names(report), ["helper", "other"]
            )

    def test_include_paths_are_forwarded_to_the_c_preprocessor(self):
        args = MODULE.parser().parse_args(["--include", "include", "example.c"])

        self.assertIn(
            f"-cpp-extra-args=-I{Path('include').resolve()}",
            MODULE.command_options(args),
        )

    def test_include_paths_with_spaces_are_shell_quoted(self):
        args = MODULE.parser().parse_args(
            ["--include", "include directory", "example.c"]
        )

        self.assertIn(
            f"-cpp-extra-args=-I'{Path('include directory').resolve()}'",
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

    def test_pipeline_rejects_multiple_translation_units_before_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            (project / "main.c").write_text(
                "int main(void) { return 0; }\n", encoding="utf-8"
            )
            (project / "helper.c").write_text(
                "int helper(void) { return 1; }\n", encoding="utf-8"
            )
            args = MODULE.parser().parse_args(
                ["--output-dir", str(root / "results"), str(project)]
            )

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.run_pipeline(args)

            self.assertEqual(raised.exception.stage, "input")
            self.assertIn("exactly one C translation unit", raised.exception.message)
            self.assertIn("Saida", raised.exception.message)

    def test_directory_inputs_accept_uppercase_c_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "UPPER.C"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            self.assertEqual(MODULE.source_paths([temp]), [source.resolve()])

    def test_directory_discovery_ignores_non_regular_c_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            fifo = root / "blocking.c"
            try:
                MODULE.os.mkfifo(fifo)
            except (AttributeError, OSError) as error:
                self.skipTest(f"FIFO files are unavailable: {error}")

            self.assertEqual(MODULE.source_paths([temp]), [source.resolve()])

    def test_explicit_non_c_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "header.h"
            source.write_text("int value;\n", encoding="utf-8")

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.source_paths([str(source)])

            self.assertEqual(raised.exception.stage, "input")
            self.assertIn("unsupported source file type", raised.exception.message)

    def test_cli_does_not_write_report_on_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "header.h"
            source.write_text("int value;\n", encoding="utf-8")
            output = Path(temp) / "results"

            with patch.object(MODULE, "print_human_report"):
                result = MODULE.main(["--output-dir", str(output), str(source)])

            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_input_error_invalidates_a_stale_report_in_a_safe_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "header.h"
            source.write_text("int value;\n", encoding="utf-8")
            output = Path(temp) / "results"
            output.mkdir()
            report = output / "report.json"
            report.write_text('{"status": "passed"}\n', encoding="utf-8")

            with patch.object(MODULE, "print_human_report"):
                result = MODULE.main(["--output-dir", str(output), str(source)])

            self.assertEqual(result, 1)
            self.assertFalse(report.exists())

    def test_output_directory_cannot_be_inside_input_source_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = project / "results"

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.validate_output_directory([source], output, [project])

            self.assertEqual(raised.exception.stage, "output")
            self.assertIn("overlaps the input source tree", raised.exception.message)

    def test_output_directory_cannot_be_an_ancestor_of_input_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            project = output / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.validate_output_directory([source], output, [project])

            self.assertEqual(raised.exception.stage, "output")
            self.assertIn("overlaps", raised.exception.message)

    def test_output_symlink_resolving_inside_input_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            actual_output = project / "results"
            actual_output.mkdir()
            output_link = root / "output-link"
            try:
                output_link.symlink_to(actual_output, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks are unavailable: {error}")

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.validate_output_directory(
                    [source], output_link, [project]
                )

            self.assertEqual(raised.exception.stage, "output")

    def test_output_directory_cannot_be_below_a_requested_source_path(self):
        with tempfile.TemporaryDirectory() as temp:
            missing_source = Path(temp) / "missing.c"
            output = missing_source / "results"

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.validate_output_directory([missing_source], output)

            self.assertEqual(raised.exception.stage, "output")

    def test_single_file_can_use_child_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            MODULE.validate_output_directory([source], project / "results")

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

    def test_unsafe_output_validation_does_not_remove_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            source = project / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = project / "results"
            output.mkdir()
            report = output / "report.json"
            original = '{"status": "passed"}\n'
            report.write_text(original, encoding="utf-8")

            with patch.object(MODULE, "print_human_report"):
                result = MODULE.main(
                    ["--output-dir", str(output), str(project)]
                )

            self.assertEqual(result, 1)
            self.assertEqual(report.read_text(encoding="utf-8"), original)

    def test_existing_file_is_rejected_as_the_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "main.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = Path(temp) / "result-file"
            output.write_text("keep\n", encoding="utf-8")

            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.run_pipeline(
                    MODULE.parser().parse_args(
                        ["--output-dir", str(output), str(source)]
                    )
                )

            self.assertEqual(raised.exception.stage, "output")
            self.assertIn("not a directory", raised.exception.message)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep\n")

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

    def test_prepare_output_preflights_all_artifacts_before_removing_any(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            stale = output / MODULE.SAIDA_OUTPUT
            stale.write_text("keep until validation succeeds\n", encoding="utf-8")
            invalid = output / MODULE.ISP_OUTPUT
            invalid.mkdir()

            with self.assertRaises(MODULE.PipelineError):
                MODULE.prepare_output_directory(output)

            self.assertTrue(stale.is_file())
            self.assertTrue(invalid.is_dir())

    def test_output_permission_failure_has_an_output_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "results"
            error = PermissionError(13, "Permission denied", str(output))

            with patch.object(Path, "mkdir", side_effect=error):
                with self.assertRaises(MODULE.PipelineError) as raised:
                    MODULE.prepare_output_directory(output)

            self.assertEqual(raised.exception.stage, "output")
            self.assertIn("could not prepare output directory", raised.exception.message)

    def test_directory_without_c_files_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(MODULE.PipelineError) as raised:
                MODULE.source_paths([temp])

            self.assertEqual(raised.exception.stage, "input")
            self.assertIn("no C source files", raised.exception.message)

    def test_unreadable_source_directory_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            error = PermissionError(13, "Permission denied", str(root / "locked"))

            def unreadable_walk(_path, *, onerror):
                onerror(error)
                return []

            with patch.object(MODULE.os, "walk", side_effect=unreadable_walk):
                with self.assertRaises(MODULE.PipelineError) as raised:
                    MODULE.source_paths([temp])

            self.assertEqual(raised.exception.stage, "input")
            self.assertIn("could not read source directory", raised.exception.message)

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

    def test_saida_partial_assigns_warning_continues_to_final_wp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "example.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = root / "results"
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
                    return MODULE.subprocess.CompletedProcess(
                        command,
                        0,
                        "[saida] Warning: [SAIDA-W001] frame requires WP\n",
                        "",
                    )
                if "-isp" in command:
                    (Path(cwd) / MODULE.ISP_OUTPUT).write_text(
                        source.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    (Path(cwd) / MODULE.MISSING_CONTRACT_OUTPUT).write_text(
                        json.dumps({"missing_helper_contracts": []}),
                        encoding="utf-8",
                    )
                stdout = "Proved goals: 1 / 1\n" if "-wp" in command else "ok\n"
                return MODULE.subprocess.CompletedProcess(command, 0, stdout, "")

            with patch.object(MODULE.shutil, "which", return_value="/usr/bin/fake"), patch.object(
                MODULE.subprocess, "run", side_effect=fake_run
            ):
                report = MODULE.run_pipeline(args)

            self.assertEqual(report.status, "passed")
            self.assertEqual(report.stages[1].name, "saida_tricera")
            self.assertEqual(report.stages[1].status, "warning")
            self.assertIn("final WP", report.stages[1].error)
            self.assertIn("-wp", commands[-1])

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

    def test_pipeline_stops_before_wp_when_isp_reports_partial_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "example.c"
            source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output = root / "results"
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
                        json.dumps({"missing_helper_contracts": []}),
                        encoding="utf-8",
                    )
                    return MODULE.subprocess.CompletedProcess(
                        command,
                        0,
                        "",
                        "[isp] Warning: [ISP-W003] unsupported mutation\n",
                    )
                return MODULE.subprocess.CompletedProcess(command, 0, "ok\n", "")

            with patch.object(
                MODULE.shutil, "which", return_value="/usr/bin/fake"
            ), patch.object(MODULE.subprocess, "run", side_effect=fake_run):
                report = MODULE.run_pipeline(args)

            self.assertEqual(report.status, "failed")
            self.assertEqual(
                [stage.name for stage in report.stages],
                ["parse", "saida_tricera", "isp_eva"],
            )
            self.assertIn("partial auxiliary inference", report.errors[0]["message"])
            self.assertFalse(any("-wp" in command for command in commands))

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

    def test_stage_start_os_error_keeps_the_stage_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            error = PermissionError(13, "Permission denied", "frama-c")
            with patch.object(MODULE.subprocess, "run", side_effect=error):
                result = MODULE.run_stage(
                    name="parse",
                    description="parse",
                    command=["frama-c"],
                    cwd=output,
                    output_dir=output,
                    timeout=1,
                )

            self.assertEqual(result.status, "error")
            self.assertEqual(result.returncode, 13)
            self.assertIn("could not start command", result.error)

    def test_stage_replaces_invalid_utf8_in_tool_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = MODULE.run_stage(
                name="parse",
                description="parse",
                command=[
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.buffer.write(bytes([255]))",
                ],
                cwd=output,
                output_dir=output,
                timeout=5,
            )

            self.assertEqual(result.status, "passed")
            self.assertEqual(
                (output / "parse.stdout.log").read_text(encoding="utf-8"),
                "\ufffd",
            )

    def test_missing_entry_point_has_actionable_parse_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            completed = MODULE.subprocess.CompletedProcess(
                ["frama-c"],
                1,
                "",
                "[kernel] User Error: 'paper_entry' is not a defined function. "
                "Please choose a valid function name for option -main\n",
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

            self.assertEqual(
                result.error,
                "entry point 'paper_entry' was not found as a function definition "
                "in the input C sources; check --entry-point and ensure the function "
                "is defined",
            )

    def test_missing_forward_declaration_has_actionable_parse_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            completed = MODULE.subprocess.CompletedProcess(
                ["frama-c"],
                1,
                "",
                "error: implicit declaration of function 'update_state'\n",
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

            self.assertEqual(
                result.error,
                "function 'update_state' is called without a visible declaration; "
                "add a prototype in the source or an included header before running "
                "AutoDeduct",
            )

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

    def test_wp_rejects_a_run_without_proof_goals(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "wp.stdout.log"
            log.write_text("Proved goals: 0 / 0\n", encoding="utf-8")
            stage = MODULE.StageResult(
                name="wp",
                description="wp",
                status="passed",
                stdout_file=str(log),
            )

            self.assertEqual(
                MODULE.wp_diagnostic(stage), "WP generated no proof goals"
            )

    def test_wp_uses_the_final_proved_goals_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "wp.stdout.log"
            log.write_text(
                "Proved goals: 1 / 2\nProved goals: 2 / 2\n",
                encoding="utf-8",
            )
            stage = MODULE.StageResult(
                name="wp",
                description="wp",
                status="passed",
                stdout_file=str(log),
            )

            self.assertIsNone(MODULE.wp_diagnostic(stage))

    def test_wp_diagnostic_names_unresolved_goal(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            log = output / "wp.stdout.log"
            log.write_text(
                "[wp] [Timeout] typed_update_global_array_ensures_2\n"
                "[wp] Proved goals:   20 / 21\n",
                encoding="utf-8",
            )
            stage = MODULE.StageResult(
                name="wp",
                description="wp",
                status="passed",
                stdout_file=str(log),
            )

            self.assertEqual(
                MODULE.wp_diagnostic(stage),
                "WP proved 20 of 21 goals; unresolved: "
                "Timeout: typed_update_global_array_ensures_2",
            )

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

    def test_tricera_fallback_detection_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "saida.stderr.log"
            log.write_text("ROSETTA ERROR: preprocessing failed\n", encoding="utf-8")
            stage = MODULE.StageResult(
                name="saida_tricera",
                description="saida",
                status="passed",
                stderr_file=str(log),
            )

            self.assertIn("fallback", MODULE.tricera_diagnostic(stage))

    def test_tricera_fallback_is_detected_on_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "saida.stdout.log"
            log.write_text("rosetta error: preprocessing failed\n", encoding="utf-8")
            stage = MODULE.StageResult(
                name="saida_tricera",
                description="saida",
                status="passed",
                stdout_file=str(log),
            )

            self.assertIn("fallback", MODULE.tricera_diagnostic(stage))

    def test_saida_partial_assigns_warning_is_surfaced(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "saida.stdout.log"
            log.write_text(
                "[saida] Warning: [SAIDA-W001] frame requires WP\n",
                encoding="utf-8",
            )
            stage = MODULE.StageResult(
                name="saida_tricera",
                description="saida",
                status="passed",
                stdout_file=str(log),
            )

            self.assertIn("final WP", MODULE.saida_partial_diagnostic(stage))

    def test_isp_partial_warning_is_a_failure_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "isp.stderr.log"
            log.write_text(
                "[isp] Warning: [ISP-W003] unsupported mutation\n"
                "[isp] Warning: [isp-w007] Eva could not evaluate a term\n",
                encoding="utf-8",
            )
            stage = MODULE.StageResult(
                name="isp_eva",
                description="isp",
                status="passed",
                stderr_file=str(log),
            )

            diagnostic = MODULE.isp_partial_diagnostic(stage)

            self.assertIn("ISP-W003", diagnostic)
            self.assertIn("ISP-W007", diagnostic)


if __name__ == "__main__":
    unittest.main()
