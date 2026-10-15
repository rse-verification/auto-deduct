"""Offline regressions for host access to Docker integration artifacts."""

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from integration_support import DockerPipelineTestCase


@unittest.skipUnless(os.name == "posix", "integration harness requires POSIX host IDs")
class DockerHarnessTests(unittest.TestCase):
    def test_private_reports_use_host_identity_and_need_no_root_cleanup(self):
        for returncode in (0, 1):
            with self.subTest(returncode=returncode):
                outputs = []
                report = {"status": "passed" if returncode == 0 else "failed"}

                def run_container(command, **kwargs):
                    self.assertIn("--user", command)
                    self.assertEqual(command[command.index("--user") + 1], "1001:1002")
                    self.assertIn(":/work:ro", " ".join(command))
                    mount = next(word for word in command if word.endswith(":/output"))
                    output = Path(mount.removesuffix(":/output"))
                    outputs.append(output)
                    self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                    artifact = output / "report.json"
                    artifact.write_text(json.dumps(report), encoding="utf-8")
                    artifact.chmod(0o600)
                    return subprocess.CompletedProcess(command, returncode, "pipeline result", "")

                with patch("integration_support.shutil.which", return_value="docker"), \
                        patch("integration_support.os.getuid", return_value=1001), \
                        patch("integration_support.os.getgid", return_value=1002), \
                        patch("integration_support.subprocess.run", side_effect=run_container) as run:
                    result = DockerPipelineTestCase().run_autodeduct("examples/ase-2024", "main")

                self.assertEqual(result.returncode, returncode)
                self.assertEqual(result.report, report)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(len(outputs), 1)
                self.assertFalse(outputs[0].exists())
