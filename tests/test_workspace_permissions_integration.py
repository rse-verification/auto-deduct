"""Opt-in Linux container account and workspace permission checks."""

import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from integration_support import IMAGE, INTEGRATION_SKIP_REASON, RUN_INTEGRATION


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class WorkspacePermissionsTests(unittest.TestCase):
    def setUp(self):
        self.volume = f"autodeduct-uid-test-{uuid.uuid4().hex}"
        subprocess.run(["docker", "volume", "create", self.volume],
                       check=True, capture_output=True, timeout=30)
        self.addCleanup(subprocess.run, ["docker", "volume", "rm", self.volume],
                        capture_output=True, timeout=30, check=False)

    def container(self, command, options=(), input=None):
        name = f"autodeduct-uid-test-{uuid.uuid4().hex}"
        try:
            return subprocess.run([
                "docker", "run", "--rm", "--pull", "never", "--network", "none",
                "--platform", os.environ.get("AUTODEDUCT_PLATFORM", "linux/amd64"),
                "--name", name, "-v", f"{self.volume}:/work", "-w", "/work",
                *options, IMAGE, *command,
            ], capture_output=True, text=True, input=input, timeout=60)
        finally:
            subprocess.run(["docker", "rm", "--force", name],
                           capture_output=True, timeout=30, check=False)

    def prepare_workspace(self, uid, gid):
        # Only this test's disposable volume is changed, never a host checkout.
        result = self.container([
            "-c", f"chown {uid}:{gid} /work && chmod 755 /work && "
            "touch /work/existing && chown 7777:8888 /work/existing",
        ], options=("--user", "0:0", "--entrypoint", "/bin/sh"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_named_owner_can_create_files_without_changing_existing_ownership(self):
        for uid, gid in ((2000, 2000), (2000, 45678), (34567, 45678), (123456, 234567)):
            with self.subTest(uid=uid, gid=gid):
                self.prepare_workspace(uid, gid)
                result = self.container([
                    "sh", "-ec", f"test $(id -u) = {uid}; test $(id -g) = {gid}; "
                    "whoami; getent passwd $(id -u); getent group $(id -g); "
                    f"mkdir output-{uid}-{gid}; touch output-{uid}-{gid}/report; "
                    f"test $(stat -c %u:%g output-{uid}-{gid}/report) = {uid}:{gid}; "
                    "test $(stat -c %u:%g existing) = 7777:8888; "
                    f"test $(stat -c %u:%g /work) = {uid}:{gid}",
                ], options=("--user", f"{uid}:{gid}", "--read-only",
                            "--tmpfs", "/tmp:rw,nosuid,size=256m", "--cap-drop", "ALL",
                            "--security-opt", "no-new-privileges"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.strip())

    def test_default_shell_keeps_dev_even_with_root_owned_workspace(self):
        self.prepare_workspace(0, 0)
        result = self.container([], options=("-i",), input="id -u; whoami; exit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["2000", "dev"])
        result = self.container(["id", "-u"], options=("--user", "0:0"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0")

    def test_host_user_can_write_bind_mount_with_resolvable_username(self):
        with tempfile.TemporaryDirectory(prefix="autodeduct-bind-test-") as temp:
            workspace = Path(temp)
            result = self.container([
                "bash", "-ec", "whoami; getent passwd $(id -u); "
                "prompt='\\u'; test \"${prompt@P}\" = \"$(whoami)\"; "
                "mkdir output; touch output/report; "
                "test $(stat -c %u output/report) = $(id -u)",
            ], options=("--user", f"{os.getuid()}:{os.getgid()}",
                        "-v", f"{workspace}:/bind-work", "-w", "/bind-work"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((workspace / "output/report").stat().st_uid, os.getuid())
