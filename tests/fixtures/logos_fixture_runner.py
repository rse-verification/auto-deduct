"""Test-only Codex substitute: known helper contract, real LOGOS and real WP.

This tests the integration protocol without an API account or model call.
It is not a contract generator for user programs.
"""

import hashlib
import json
from pathlib import Path

task = json.loads(Path("agent-task.json").read_text())
source = Path(task["source"]).read_text(encoding="utf-8")
Path(task["contracts"]).write_text(json.dumps({
    "format": "acsl-contracts-v2",
    "metadata": {"source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()},
    "contracts": {"helper": {"assigns": ["\\nothing"], "ensures": ["\\result == 1"]}},
}), encoding="utf-8")
assert task["workflow"] == "generate-only"
