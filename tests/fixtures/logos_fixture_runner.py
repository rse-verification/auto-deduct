"""Test-only Codex substitute: known helper contract, real LOGOS and real WP.

This tests the integration protocol without an API account or model call.
It is not a contract generator for user programs.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

task = json.loads(Path("llm-task.json").read_text())
source = Path(task["source"]).read_text(encoding="utf-8")
Path(task["contracts"]).write_text(json.dumps({
    "format": "acsl-contracts-v2",
    "metadata": {"source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()},
    "contracts": {"helper": {"assigns": ["\\nothing"], "ensures": ["\\result == 1"]}},
}), encoding="utf-8")
wrapper = Path(task["skill"]).parent / "scripts" / "generate_acsl.py"
command = [sys.executable, str(wrapper), task["source"], "--contracts", task["contracts"],
           "-o", task["annotated_source"], "--verify", "--verification-json", task["verification_json"]]
command.extend(f"--frama-c-option={option}" for option in task["verification_options"])
raise SystemExit(subprocess.run(command, check=False).returncode)
