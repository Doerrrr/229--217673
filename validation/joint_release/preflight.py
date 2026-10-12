"""Author-side structural and public-contract preflight for joint DDI draft."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import argparse
import tomllib


ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--task-name", required=True)
args = parser.parse_args()
if not args.task_name.startswith("runtime_task_") or any(
    char in args.task_name for char in "/\\:."
):
    raise SystemExit("Use an owned runtime_task_* folder")
TASK = ROOT / args.task_name
FILES = {p.relative_to(TASK).as_posix(): p for p in TASK.rglob("*")
         if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
REQUIRED = {
    "environment/Dockerfile", "environment/app/curate.py",
    "environment/bin/ddi-curate", "environment/bin/ddi-release-audit",
    "environment/bridge/build.sh", "environment/bridge/client.py",
    "environment/bridge/panel_to_graph.py",
    "environment/bridge/src/bridge_index.cpp",
    "environment/release/release.py", "instruction.md", "task.toml",
    "solution/bridge_reference.cpp", "solution/ddi-curate",
    "solution/oracle_curate.py", "solution/release_reference.py",
    "solution/solve.sh", "tests/bridge/analytic_cases.py",
    "tests/bridge/check_graph.py", "tests/bridge/temporal_standard.py",
    "tests/bridge/test_outputs.py", "tests/curator/test_outputs.py",
    "tests/integration_standard.py", "tests/joint_score.py",
    "tests/test_joint.py", "tests/test.sh",
}
for name in ("drug_list.csv", "DDI_event.csv", "newddi.csv", "drug_changes.csv",
             "event_changes.csv", "interaction_changes.csv"):
    REQUIRED.add("environment/data/" + name)
assert FILES.keys() == REQUIRED, (sorted(FILES.keys() - REQUIRED), sorted(REQUIRED - FILES.keys()))
assert all(not path.is_symlink() for path in FILES.values())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
hidden_hashes = {sha(path) for name, path in FILES.items()
                 if name.startswith(("solution/", "tests/"))}
assert not any(sha(path) in hidden_hashes for name, path in FILES.items()
               if name.startswith("environment/")), "candidate contains a complete hidden file"
for name, path in FILES.items():
    if name.endswith(".py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=name)
assert FILES["solution/solve.sh"].read_bytes().startswith(b"#!/bin/bash")
assert FILES["tests/test.sh"].read_bytes().startswith(b"#!/bin/bash")
for name in (
    "environment/bin/ddi-curate", "environment/bin/ddi-release-audit",
    "solution/ddi-curate", "solution/solve.sh", "tests/test.sh",
    "environment/bridge/build.sh",
):
    assert b"\r" not in FILES[name].read_bytes(), f"CR line ending in {name}"
dockerfile = FILES["environment/Dockerfile"].read_text(encoding="utf-8")
assert "solution/" not in dockerfile and "tests/" not in dockerfile
assert "rdkit==2025.3.6" in dockerfile and "g++" in dockerfile
config = tomllib.loads(FILES["task.toml"].read_text(encoding="utf-8"))
assert config["schema_version"] == "1.3"
assert config["agent"]["timeout_sec"] == 3600
assert config["verifier"]["timeout_sec"] == 900
assert config["environment"]["allow_internet"] is False
instruction = FILES["instruction.md"].read_text(encoding="utf-8")
for clause in (
    "same six inputs", "one-based CSV data-row index", "parallel graph",
    "45-second wall-time", "1,536 MiB virtual-address-space",
    "CURRENT", "generation_id", "0.40", "0.20",
):
    assert clause in instruction, clause
expected_data = {
    "drug_list.csv": "208edfd36b34dc7f2d877f3b86636cff5fc14c11ff5617466b92b2633890a513",
    "DDI_event.csv": "3efbd7ade6ef3c6d3e0fb0422653b7689912b5a75316a29d85c8e26072bff311",
    "newddi.csv": "673d7ed6a0f3ecfdeaa1df54295f98ddf45266a837f6ec3a6a5f7934710d3b72",
}
for name, digest in expected_data.items():
    assert sha(FILES["environment/data/" + name]) == digest, name
module = ast.parse(FILES["tests/joint_score.py"].read_text(encoding="utf-8"))
groups = {}
for node in module.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("CURATOR", "BRIDGE"):
                groups[target.id] = ast.literal_eval(node.value)
assert len(groups["CURATOR"]) == 14 and len(groups["BRIDGE"]) == 6
assert abs(sum(weight for _, weight in groups["CURATOR"]) - 1) < 1e-12
assert abs(sum(weight for _, weight in groups["BRIDGE"]) - 1) < 1e-12
print(json.dumps({"status": "PASS", "required_files": len(REQUIRED),
                  "environment_hidden_exact_duplicates": 0,
                  "protected_original_csv": expected_data,
                  "scoring": {"curator": .4, "bridge": .4, "release": .2}}, indent=2))
