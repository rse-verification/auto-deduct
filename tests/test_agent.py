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
from autodeduct_pipeline.agent import validate_annotation_only, validate_agent_options

SOURCE = "int helper(void)\n{\n    return 1;\n}\n/*@ ensures \\result == 1; */\nint main(void)\n{\n    return helper();\n}\n"
ANNOTATED = "/*@ assigns \\nothing; ensures \\result == 1; */\n" + SOURCE
IMAGE_ID = "sha256:" + "a" * 64
IMAGE_SKILL = "Use the image's LOGOS contract skill. λόγος\n"


class AgentModeTests(unittest.TestCase):
    def setUp(self):
        guard = patch("autodeduct_pipeline.agent.in_container", return_value=False)
        guard.start()
        self.addCleanup(guard.stop)

    def exercise(self, failure=None, wp="Proved goals: 2 / 2\n", runner="codex exec", runtime="local"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "src" / "input.c"
            source.parent.mkdir()
            source.write_text(SOURCE)
            skill = root / "SKILL.md"
            skill.write_text("Use the test contract skill and its verifier.")
            (root / "scripts").mkdir()
            (root / "scripts/generate_acsl.py").write_text("# test wrapper")
            output = root / "output"
            output.mkdir()
            for artifact in ("agent-verification.json", "agent-contracts.json", "inferred.c"):
                (output / artifact).write_text("stale")
            args = parser().parse_args([
                "--mode", "agent", "--agent-runner", runner,
                *(["--agent-skill", str(skill)] if runtime == "local" else []),
                "--agent-runtime", runtime,
                "--wp-rte", "--wp-option=-wp-prover=qed", "--output-dir", str(output), str(source),
            ])
            commands = []
            cached_skill = None

            def fake_run(command, **kwargs):
                nonlocal cached_skill
                if command[:3] == ["docker", "image", "inspect"]:
                    if failure == "image":
                        return subprocess.CompletedProcess(command, 1, "", "No such image")
                    return subprocess.CompletedProcess(command, 0, "invalid" if failure == "image_id" else IMAGE_ID + "\n", "")
                if command[:2] == ["docker", "run"]:
                    self.assertIn(IMAGE_ID, command)
                if "-c" in command and "SKILL.md" in command[-1]:
                    self.assertNotIn("--mount", command)
                    if failure == "extraction_timeout":
                        raise subprocess.TimeoutExpired(command, 1)
                    if failure == "extraction":
                        return subprocess.CompletedProcess(command, 1, "", "SKILL.md missing")
                    return subprocess.CompletedProcess(command, 0, "  \n" if failure == "empty_skill" else IMAGE_SKILL, "")
                if "--check-dependencies" in command:
                    if failure == "dependencies":
                        return subprocess.CompletedProcess(command, 1, "", "Frama-C was not found in PATH; install Frama-C with WP")
                    if failure == "preflight_timeout":
                        raise subprocess.TimeoutExpired(command, 1)
                    return subprocess.CompletedProcess(command, 0, "LOGOS verification dependencies are available", "")
                commands.append(command)
                task = json.loads((output / "agent-task.json").read_text())
                self.assertEqual(task["workflow"], "generate-only")
                self.assertIn("-wp-rte", task["verification_options"])
                self.assertIn("-wp-prover=qed", task["verification_options"])
                if len(commands) == 1:
                    selected_skill = Path(task["skill"])
                    self.assertTrue(selected_skill.is_file())
                    expected_skill = IMAGE_SKILL if runtime == "docker" else skill.read_text()
                    self.assertEqual(selected_skill.read_text(), expected_skill)
                    self.assertEqual(task["skill_sha256"], hashlib.sha256(expected_skill.encode()).hexdigest())
                    self.assertEqual(task["docker_image_id"], IMAGE_ID if runtime == "docker" else None)
                    if runtime == "docker":
                        cached_skill = selected_skill
                        self.assertNotIn(output, selected_skill.parents)
                    self.assertEqual(command[:2], ["codex", "exec"])
                    self.assertEqual("--sandbox" in command, "--approve-for-me" not in command)
                    self.assertIn(str(selected_skill), command[-1])
                    self.assertIn("complete SKILL.md", command[-1])
                    self.assertIn("generate-only", command[-1])
                    for artifact in ("agent-verification.json", "agent-contracts.json", "inferred.c"):
                        self.assertFalse((output / artifact).exists())
                    if failure == "runner":
                        return subprocess.CompletedProcess(command, 1, "", "agent unavailable")
                    if failure != "missing":
                        (output / "agent-contracts.json").write_text(json.dumps({
                            "format": "acsl-contracts-v2", "contracts": {"helper": {}},
                            "metadata": {"source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest()},
                        }))
                    if failure == "agent_evidence":
                        (output / "agent-verification.json").write_text("{}")
                    if failure == "log_symlink":
                        (output / "skill_verify.stdout.log").symlink_to(source)
                    if failure == "changed_skill":
                        selected_skill.chmod(0o600)
                        selected_skill.write_text("changed instructions")
                    if failure == "snapshot_symlink":
                        (output / "agent-skill.md").symlink_to(source)
                    return subprocess.CompletedProcess(command, 0, "generated contracts", "")
                if runtime == "docker":
                    self.assertEqual(command[:2], ["docker", "run"])
                    self.assertIn("--read-only", command)
                    self.assertEqual(command[command.index("--network") + 1], "none")
                    self.assertIn(f"type=bind,source={source.parent},target={source.parent},readonly", command)
                    self.assertIn(f"type=bind,source={output},target={output}", command)
                    self.assertIn("/opt/logos/skill/scripts/generate_acsl.py", command)
                    self.assertNotIn("--privileged", command)
                    self.assertFalse(any(".codex" in word or "docker.sock" in word for word in command))
                    if failure in {"timeout", "cleanup_failure"}:
                        raise subprocess.TimeoutExpired(command, 1)
                else:
                    self.assertEqual(command[:2], [sys.executable, str(root / "scripts/generate_acsl.py")])
                self.assertIn("--verify", command)
                self.assertIn("--verification-json", command)
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
                (output / "agent-verification.json").write_text(
                    "invalid json" if failure == "json" else json.dumps(evidence)
                )
                return subprocess.CompletedProcess(command, 1 if failure == "wrapper_exit" else 0, "wrapper finished", "")

            with patch("autodeduct_pipeline.agent.in_container", return_value=False), patch(
                "autodeduct_pipeline.agent.shutil.which", return_value="docker" if runtime == "docker" else None
            ), patch(
                "autodeduct_pipeline.stages._run_command", side_effect=fake_run
            ), patch("autodeduct_pipeline.runtime.subprocess.run") as cleanup:
                cleanup.return_value = subprocess.CompletedProcess(
                    ["docker", "rm"], 1 if failure == "cleanup_failure" else 0,
                    b"", b"cannot connect to Docker daemon" if failure == "cleanup_failure" else b"",
                )
                report = run_pipeline(args)
                if failure in {"timeout", "preflight_timeout", "extraction_timeout"}:
                    self.assertEqual(cleanup.call_args.args[0][:3], ["docker", "rm", "--force"])
            self.assertEqual(source.read_text(), SOURCE)
            self.assertIsNone(report.contract_report)
            self.assertEqual(report.mode, "agent")
            setup_failure = failure in {"image", "image_id", "extraction", "extraction_timeout", "empty_skill", "dependencies", "preflight_timeout"}
            self.assertEqual(len(commands), 0 if setup_failure else
                             1 if failure in {"runner", "missing", "agent_evidence", "changed_skill"} else 2)
            if cached_skill is not None:
                self.assertFalse(cached_skill.parent.exists())
            self.assertEqual(list(root.glob(".autodeduct-logos-skill-*")), [])
            if runtime == "docker" and failure not in {"image", "image_id", "extraction", "extraction_timeout", "empty_skill"}:
                self.assertFalse((output / "agent-skill.md").is_symlink())
                self.assertEqual((output / "agent-skill.md").read_text(), IMAGE_SKILL)
            return report

    def test_host_generation_and_explicit_verification(self):
        for runner in ("codex exec", "codex exec --approve-for-me"):
            with self.subTest(runner=runner):
                report = self.exercise(runner=runner)
                self.assertEqual(report.status, "passed", report.errors)
                self.assertEqual([stage.name for stage in report.stages], ["logos_environment", "agent_workflow", "logos_verify", "skill_verify"])

    def test_missing_dependencies_stop_before_generation(self):
        for runtime in ("local", "docker"):
            with self.subTest(runtime=runtime):
                report = self.exercise(runtime=runtime, failure="dependencies")
                self.assertEqual(report.status, "failed")
                self.assertEqual([stage.name for stage in report.stages],
                                 (["logos_image", "logos_skill"] if runtime == "docker" else []) + ["logos_environment"])
                self.assertEqual(report.errors[-1]["stage"], "environment")
                self.assertIn("install Frama-C", report.errors[-1]["message"])

    def test_docker_preflight_timeout_stops_container(self):
        report = self.exercise(runtime="docker", failure="preflight_timeout")
        self.assertEqual(report.stages[-1].status, "timeout")
        self.assertEqual(report.errors[-1]["stage"], "environment")

    def test_docker_runtime_keeps_agent_on_host(self):
        report = self.exercise(runtime="docker")
        self.assertEqual(report.status, "passed", report.errors)
        self.assertEqual([stage.name for stage in report.stages],
                         ["logos_image", "logos_skill", "logos_environment", "agent_workflow", "logos_verify", "skill_verify"])

    def test_docker_image_and_skill_errors_stop_before_generation(self):
        for failure in ("image", "image_id", "extraction", "extraction_timeout", "empty_skill"):
            with self.subTest(failure=failure):
                report = self.exercise(runtime="docker", failure=failure)
                self.assertEqual(report.status, "failed")
                self.assertNotIn("agent_workflow", [stage.name for stage in report.stages])
                self.assertTrue(report.errors)

    def test_modified_extracted_skill_is_rejected(self):
        report = self.exercise(runtime="docker", failure="changed_skill")
        self.assertEqual(report.status, "failed")
        self.assertIn("skill changed", report.errors[-1]["message"])

    def test_docker_generation_failure_cleans_temporary_skill(self):
        report = self.exercise(runtime="docker", failure="runner")
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.errors[-1]["stage"], "agent_workflow")

    @unittest.skipUnless(sys.platform != "win32", "requires ordinary symlink creation")
    def test_extracted_snapshot_cannot_redirect_into_source(self):
        report = self.exercise(runtime="docker", failure="snapshot_symlink")
        self.assertEqual(report.status, "passed", report.errors)

    def test_docker_ignores_host_skill_but_local_requires_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            args = parser().parse_args(["--mode", "agent", "--agent-runtime", "docker",
                                       "--agent-skill", str(output / "nonexistent.md"), "input.c"])
            with patch("autodeduct_pipeline.agent.shutil.which", return_value="docker"):
                validate_agent_options(args, output)
            args.agent_runtime = "local"
            with self.assertRaisesRegex(PipelineError, "set --agent-skill"):
                validate_agent_options(args, output)

    @unittest.skipUnless(sys.platform != "win32", "requires ordinary symlink creation")
    def test_generator_cannot_redirect_verification_logs_into_source(self):
        report = self.exercise(failure="log_symlink")
        self.assertEqual(report.status, "passed", report.errors)

    def test_docker_timeout_stops_verifier_container(self):
        report = self.exercise(runtime="docker", failure="timeout")
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.stages[-1].status, "timeout")
        self.assertEqual(report.errors[-1]["stage"], "logos_verify")

    def test_docker_cleanup_failure_is_reported(self):
        report = self.exercise(runtime="docker", failure="cleanup_failure")
        self.assertEqual(report.status, "failed")
        cleanup_error = next(error for error in report.errors if error["stage"] == "cleanup")
        self.assertIn("could not confirm cleanup of container", cleanup_error["message"])

    def test_invalid_results_and_changed_source_never_pass(self):
        for failure in ("runner", "missing", "agent_evidence", "wrapper_exit", "json", "hash", "verifier", "changed", "options", "malformed"):
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
            args = parser().parse_args(["--mode", "agent", "--agent-skill", str(skill), "--output-dir", str(output), "/unrelated/input.c"])
            with self.assertRaises(PipelineError):
                run_pipeline(args)
            self.assertEqual(skill.read_text(), "keep me")

    def test_default_runner_is_allowed_when_cwd_is_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            skill = root / "SKILL.md"
            skill.write_text("test skill")
            (root / "scripts").mkdir()
            (root / "scripts/generate_acsl.py").write_text("# test wrapper")
            output = root / "output"
            output.mkdir()
            args = parser().parse_args(["--mode", "agent", "--agent-skill", str(skill), "input.c"])
            with patch("os.getcwd", return_value=str(output)):
                validate_agent_options(args, output)
            runner = output / "runner.py"
            runner.write_text("keep me")
            args.agent_runner = f"python3 {runner}"
            with self.assertRaises(PipelineError):
                validate_agent_options(args, output)
            self.assertEqual(runner.read_text(), "keep me")

    def test_local_runtime_cannot_be_inside_writable_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            skill = root / "skill" / "SKILL.md"
            skill.parent.mkdir()
            skill.write_text("test skill")
            runtime = skill.parent / "scripts"
            runtime.mkdir()
            wrapper = runtime / "generate_acsl.py"
            wrapper.write_text("keep wrapper outside agent workspace")
            args = parser().parse_args(["--mode", "agent", "--agent-skill", str(skill), "input.c"])
            for output in (runtime, runtime / "output"):
                with self.subTest(output=output), self.assertRaisesRegex(PipelineError, "LOGOS runtime files must be outside"):
                    validate_agent_options(args, output)
            self.assertEqual(wrapper.read_text(), "keep wrapper outside agent workspace")

    def test_container_launch_is_rejected_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            artifact = output / "agent-contracts.json"
            artifact.write_text("keep me")
            args = parser().parse_args(["--mode", "agent", "--output-dir", str(output), "/unrelated/input.c"])
            with patch("autodeduct_pipeline.agent.in_container", return_value=True), self.assertRaisesRegex(
                PipelineError, "must be launched on the host"
            ):
                run_pipeline(args)
            self.assertEqual(artifact.read_text(), "keep me")

    def test_old_contracts_option_is_removed(self):
        with self.assertRaises(SystemExit):
            parser().parse_args(["--mode", "agent", "--contracts", "contracts.json", "input.c"])

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
