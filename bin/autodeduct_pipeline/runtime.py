"""Shared Docker execution for the LOGOS and AcTa workflows."""

import os
import re
import subprocess
from pathlib import Path

from .stages import PipelineError, run_stage


def in_container() -> bool:
    return (os.environ.get("AUTODEDUCT_CONTAINER") == "1"
            or Path("/.dockerenv").exists() or Path("/run/.containerenv").exists())


def validate_mount_path(path):
    if "," in str(path) or "\n" in str(path):
        raise PipelineError("input", "Docker bind-mount paths cannot contain commas or newlines")


def docker_run_options(platform, name):
    return ["docker", "run", "--rm", "--pull", "never", "--name", name, "--platform", platform,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,nosuid,size=256m",
            "--user", f"{os.getuid()}:{os.getgid()}"]


def run_container_stage(*, container_name, report, **stage_options):
    """Stop a failed or timed-out container as well as its Docker client."""
    result = None
    try:
        result = run_stage(**stage_options)
        return result
    finally:
        if container_name and (result is None or result.status != "passed"):
            try:
                completed = subprocess.run(["docker", "rm", "--force", container_name],
                                           capture_output=True, timeout=10, check=False)
                if completed.returncode and "No such container" not in completed.stderr.decode(errors="replace"):
                    report.errors.append({"stage": "cleanup", "message": f"could not confirm cleanup of container {container_name}"})
            except (OSError, subprocess.TimeoutExpired):
                report.errors.append({"stage": "cleanup", "message": f"could not confirm cleanup of container {container_name}"})


def resolve_image(image, *, name, report, output_dir, timeout):
    stage = run_stage(
        name=name, description="Resolve the verifier image to an immutable ID",
        command=["docker", "image", "inspect", "--format", "{{.Id}}", image],
        cwd=output_dir, output_dir=output_dir, timeout=timeout,
    )
    report.stages.append(stage)
    if stage.status != "passed":
        report.errors.append({"stage": name, "message":
                              f"{stage.error or 'image inspection failed'}; build or load the selected verifier image first"})
        return None
    image_id = Path(stage.stdout_file).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        stage.status = "failed"
        stage.error = "Docker did not return a valid immutable image ID"
        report.errors.append({"stage": name, "message": stage.error})
        return None
    return image_id
