#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase, main


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = REPO_ROOT / "Dockerfiles" / "bin" / "autodeduct-contract-assistant"
GUI = REPO_ROOT / "Dockerfiles" / "bin" / "autodeduct-contract-assistant-gui"
SAMPLE = REPO_ROOT / "tests" / "contract-assistant" / "missing_helper.c"


def load_script(name, path):
    loader = SourceFileLoader(name, str(path))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class ContractAssistantTests(TestCase):
    def run_assistant(self, *args):
        return subprocess.run(
            [sys.executable, str(ASSISTANT), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_reports_missing_helper_contract(self):
        result = self.run_assistant("--json", str(SAMPLE))

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        missing_helpers = report[0]["missing_helper_contracts"]
        self.assertEqual([helper["name"] for helper in missing_helpers], ["maybe_add"])
        self.assertEqual(report[0]["called_by"]["maybe_add"], ["main"])

    def test_fail_on_missing_uses_nonzero_exit(self):
        result = self.run_assistant("--fail-on-missing", str(SAMPLE))

        self.assertEqual(result.returncode, 1)
        self.assertIn("maybe_add", result.stdout)

    def test_writes_llm_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "prompt.md"
            result = self.run_assistant("--llm-prompt", str(prompt_path), str(SAMPLE))

            self.assertEqual(result.returncode, 0, result.stderr)
            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("Missing helper function: maybe_add", prompt)
            self.assertIn("Frama-C/WP/Eva", prompt)
            self.assertIn("void maybe_add", prompt)

    def test_accepts_directory_with_cross_file_helper_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "helper.c").write_text(
                "void helper(int *p) { *p = *p + 1; }\n",
                encoding="utf-8",
            )
            (root / "main.c").write_text(
                """int value;
void helper(int *p);
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
""",
                encoding="utf-8",
            )

            result = self.run_assistant("--json", str(root))

        self.assertEqual(result.returncode, 0, result.stderr)
        reports = json.loads(result.stdout)
        missing_helpers = [
            helper["name"]
            for report in reports
            for helper in report["missing_helper_contracts"]
        ]
        self.assertEqual(missing_helpers, ["helper"])

    def test_duplicate_helper_names_do_not_mark_unrelated_file_reachable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.c").write_text(
                """static void helper(int *p) {
  *p = *p + 1;
}

/*@
  ensures \\result >= 0;
*/
int main(void) {
  int x = 0;
  helper(&x);
  return x;
}
""",
                encoding="utf-8",
            )
            (root / "b.c").write_text(
                """static void helper(int *p) {
  *p = *p + 2;
}
""",
                encoding="utf-8",
            )

            result = self.run_assistant("--json", str(root))

        self.assertEqual(result.returncode, 0, result.stderr)
        reports = {
            Path(report["file"]).name: report for report in json.loads(result.stdout)
        }
        self.assertEqual(
            [helper["name"] for helper in reports["a.c"]["missing_helper_contracts"]],
            ["helper"],
        )
        self.assertEqual(reports["a.c"]["called_by"]["helper"], ["main"])
        self.assertEqual(reports["b.c"]["missing_helper_contracts"], [])
        self.assertEqual(reports["b.c"]["called_by"]["helper"], [])

    def test_isp_report_mapping_is_authoritative_for_duplicate_names(self):
        assistant = load_script("autodeduct_contract_assistant_backend", ASSISTANT)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.c").write_text(
                """static void helper(int *p) {
  *p = *p + 1;
}

/*@
  ensures \\result >= 0;
*/
int main(void) {
  int x = 0;
  helper(&x);
  return x;
}
""",
                encoding="utf-8",
            )
            (root / "b.c").write_text(
                """static void helper(int *p) {
  *p = *p + 2;
}
""",
                encoding="utf-8",
            )

            reports = assistant.analyze_files([root], False, backend="source")
            mapped = assistant.apply_isp_missing_helper_report(
                reports,
                {
                    "missing_helper_contracts": [
                        {
                            "function": "helper",
                            "file": "b.c",
                            "line": 1,
                            "called_by": [
                                {"function": "contracted_entry", "file": "b.c", "line": 7}
                            ],
                        }
                    ]
                },
                root,
            )

        reports_by_name = {report.path.name: report for report in mapped}
        self.assertEqual(reports_by_name["a.c"].missing_helper_contracts, [])
        self.assertEqual(
            [function.name for function in reports_by_name["b.c"].missing_helper_contracts],
            ["helper"],
        )
        self.assertEqual(
            reports_by_name["b.c"].called_by["helper"], ["contracted_entry"]
        )
        self.assertEqual(reports_by_name["b.c"].analysis_backend, "isp-frama-c")

    def test_auto_backend_falls_back_to_source_scan_when_isp_is_unavailable(self):
        assistant = load_script("autodeduct_contract_assistant_fallback", ASSISTANT)
        original_runner = assistant.run_isp_missing_helper_report

        def failing_runner(*_args, **_kwargs):
            raise RuntimeError("test ISP failure")

        assistant.run_isp_missing_helper_report = failing_runner
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / "helper.c").write_text(
                    "void helper(int *p) { *p = *p + 1; }\n",
                    encoding="utf-8",
                )
                (root / "main.c").write_text(
                    """int value;
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
""",
                    encoding="utf-8",
                )

                reports = assistant.analyze_files([root], False, backend="auto")
        finally:
            assistant.run_isp_missing_helper_report = original_runner

        missing_helpers = [
            function.name
            for report in reports
            for function in report.missing_helper_contracts
        ]
        self.assertEqual(missing_helpers, ["helper"])
        self.assertTrue(all(report.analysis_backend == "source-scan" for report in reports))
        self.assertTrue(
            all("test ISP failure" in report.analysis_warning for report in reports)
        )

    def test_directory_fixture_reports_domain_named_missing_helper_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "account.h").write_text(
                "typedef struct { int balance; } Account;\n"
                "void deposit_one(Account *account);\n",
                encoding="utf-8",
            )
            (root / "account.c").write_text(
                '#include "account.h"\n'
                "void deposit_one(Account *account) {\n"
                "  account->balance = account->balance + 1;\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "main.c").write_text(
                '#include "account.h"\n'
                "int initial_balance;\n"
                "int final_balance;\n"
                "/*@\n"
                "  requires initial_balance >= 0;\n"
                "  ensures final_balance == initial_balance + 1;\n"
                "*/\n"
                "int main(void) {\n"
                "  Account account = { initial_balance };\n"
                "  deposit_one(&account);\n"
                "  final_balance = account.balance;\n"
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            result = self.run_assistant("--json", str(root))

        self.assertEqual(result.returncode, 0, result.stderr)
        reports = json.loads(result.stdout)
        missing_helpers = [
            helper["name"]
            for report in reports
            for helper in report["missing_helper_contracts"]
        ]
        self.assertEqual(missing_helpers, ["deposit_one"])

    def test_gui_analysis_response_contains_pipeline_and_prompt(self):
        gui = load_script("autodeduct_contract_assistant_gui", GUI)

        response = gui.analyze_code("missing_helper.c", SAMPLE.read_text(), False)

        self.assertEqual(response["status"], "Analysis complete.")
        self.assertEqual(response["report"][0]["file"], "missing_helper.c")
        self.assertIn("maybe_add", response["summary"])
        self.assertIn("Missing helper function: maybe_add", response["llm_prompt"])
        helper_step = response["pipeline"][2]
        self.assertEqual(helper_step["name"], "Check helper contracts")
        self.assertEqual(helper_step["status"], "warn")

    def test_gui_analysis_accepts_multiple_files(self):
        gui = load_script("autodeduct_contract_assistant_gui_multi", GUI)
        files = [
            {
                "filename": "src/helper.c",
                "code": "void helper(int *p) { *p = *p + 1; }\n",
            },
            {
                "filename": "src/main.c",
                "code": """int value;
void helper(int *p);
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
""",
            },
            {"filename": "include/helper.h", "code": "void helper(int *p);\n"},
        ]

        response = gui.analyze_project(files, False)

        missing_helpers = [
            helper["name"]
            for report in response["report"]
            for helper in report["missing_helper_contracts"]
        ]
        self.assertEqual(missing_helpers, ["helper"])
        self.assertIn("src/helper.c", response["summary"])
        self.assertEqual(response["pipeline"][2]["status"], "warn")

    def test_gui_analysis_accepts_project_path(self):
        gui = load_script("autodeduct_contract_assistant_gui_path", GUI)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "helper.c").write_text(
                "void helper(int *p) { *p = *p + 1; }\n",
                encoding="utf-8",
            )
            (root / "main.c").write_text(
                """int value;
void helper(int *p);
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
""",
                encoding="utf-8",
            )

            response = gui.analyze_project_path(str(root), False)

        missing_helpers = [
            helper["name"]
            for report in response["report"]
            for helper in report["missing_helper_contracts"]
        ]
        self.assertEqual(missing_helpers, ["helper"])
        self.assertIn("helper.c", response["summary"])

    def test_gui_analysis_accepts_backend_selection(self):
        gui = load_script("autodeduct_contract_assistant_gui_backend", GUI)

        response = gui.analyze_project(
            [
                {
                    "filename": "helper.c",
                    "code": "void helper(int *p) { *p = *p + 1; }\n",
                },
                {
                    "filename": "main.c",
                    "code": """int value;
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
""",
                },
            ],
            include_main=False,
            backend="source",
        )

        self.assertEqual(response["report"][0]["analysis_backend"], "source-scan")
        self.assertIn("Backend: source-scan.", response["pipeline"][2]["detail"])

    def test_gui_lists_container_project_path(self):
        gui = load_script("autodeduct_contract_assistant_gui_list_path", GUI)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "example").mkdir()
            (root / "main.c").write_text("int main(void) { return 0; }\n")
            (root / "helper.h").write_text("void helper(void);\n")
            (root / "README.md").write_text("not shown\n")

            response = gui.list_project_path(str(root))

        names = [entry["name"] for entry in response["entries"]]
        self.assertEqual(response["path"], str(root))
        self.assertIn("example", names)
        self.assertIn("main.c", names)
        self.assertIn("helper.h", names)
        self.assertNotIn("README.md", names)

    def test_gui_uses_mounted_project_path_inputs(self):
        gui = load_script("autodeduct_contract_assistant_gui_html", GUI)

        self.assertIn("Browse Docker Path", gui.HTML_PAGE)
        self.assertIn("Generate Contract Draft", gui.HTML_PAGE)
        self.assertIn("Run WP with Draft", gui.HTML_PAGE)
        self.assertIn('value="/project"', gui.HTML_PAGE)
        self.assertNotIn('type="file"', gui.HTML_PAGE)

    def test_openai_payload_requests_structured_contract_suggestions(self):
        gui = load_script("autodeduct_contract_assistant_gui_openai_payload", GUI)

        payload = gui.openai_response_payload("draft contracts", "gpt-test")

        self.assertEqual(payload["model"], "gpt-test")
        text_format = payload["text"]["format"]
        self.assertEqual(text_format["type"], "json_schema")
        self.assertEqual(text_format["name"], "acsl_contract_suggestions")
        self.assertTrue(text_format["strict"])

    def test_contract_draft_is_applied_to_temporary_copy_only(self):
        gui = load_script("autodeduct_contract_assistant_gui_apply_draft", GUI)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "original"
            copy = Path(tmpdir) / "copy"
            root.mkdir()
            copy.mkdir()
            helper = "void helper(int *p) { *p = *p + 1; }\n"
            main_source = """int value;
void helper(int *p);
/*@
  ensures value >= 0;
*/
int main(void) {
  helper(&value);
  return 0;
}
"""
            (root / "helper.c").write_text(helper, encoding="utf-8")
            (root / "main.c").write_text(main_source, encoding="utf-8")
            (copy / "helper.c").write_text(helper, encoding="utf-8")
            (copy / "main.c").write_text(main_source, encoding="utf-8")

            reports = gui.ASSISTANT.analyze_files([root], False)
            draft = {
                "suggestions": [
                    {
                        "file": "helper.c",
                        "function": "helper",
                        "contract": "/*@\n  assigns *p;\n*/",
                        "rationale": "The helper increments the pointed value.",
                    }
                ]
            }

            applied = gui.apply_contract_draft_to_copy(root, copy, reports, draft)

            self.assertEqual(applied, 1)
            self.assertEqual((root / "helper.c").read_text(encoding="utf-8"), helper)
            self.assertTrue(
                (copy / "helper.c").read_text(encoding="utf-8").startswith("/*@")
            )

    def test_contract_draft_rejects_regular_c_block_comment(self):
        gui = load_script("autodeduct_contract_assistant_gui_bad_comment", GUI)

        with self.assertRaisesRegex(ValueError, "starting with /\\*@"):
            gui.apply_contract_draft_to_copy(
                Path("/tmp/original"),
                Path("/tmp/copy"),
                [],
                {
                    "suggestions": [
                        {
                            "file": "helper.c",
                            "function": "helper",
                            "contract": "/**\n * assigns *p;\n */",
                        }
                    ]
                },
            )

    def test_contract_draft_rejects_nested_block_comment_markers(self):
        gui = load_script("autodeduct_contract_assistant_gui_nested_comment", GUI)

        with self.assertRaisesRegex(ValueError, "nested C block-comment"):
            gui.apply_contract_draft_to_copy(
                Path("/tmp/original"),
                Path("/tmp/copy"),
                [],
                {
                    "suggestions": [
                        {
                            "file": "helper.c",
                            "function": "helper",
                            "contract": "/*@\n  /* bad nested comment */\n  assigns *p;\n*/",
                        }
                    ]
                },
            )

    def test_gui_frama_c_command_accepts_extra_args(self):
        gui = load_script("autodeduct_contract_assistant_gui_args", GUI)

        command = gui.frama_c_command(
            "wp",
            [Path("/tmp/project/original/sgme.c")],
            '-cpp-extra-args="-D__GNUC__=12 -Ioriginal"',
        )

        self.assertEqual(command[0], "frama-c")
        self.assertIn("-wp", command)
        self.assertIn("-cpp-extra-args=-D__GNUC__=12 -Ioriginal", command)
        self.assertEqual(command[-1], "/tmp/project/original/sgme.c")


if __name__ == "__main__":
    main()
