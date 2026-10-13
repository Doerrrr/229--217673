"""Author-side immutable-input and public/hidden boundary checks."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent
TASK = ROOT / "runtime_task_v0"
files = {p.relative_to(TASK).as_posix(): p for p in TASK.rglob("*")
         if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
required = {
    "environment/Dockerfile", "environment/app/ledger.py",
    "environment/app/curation.py", "environment/bin/ddi-ledger",
    "environment/data/drug_list.csv", "environment/data/DDI_event.csv",
    "environment/data/newddi.csv", "instruction.md", "task.toml",
    "solution/reference_ledger.py", "solution/solve.sh",
    "tests/test_outputs.py", "tests/test.sh",
}
assert set(files) == required, sorted(set(files) ^ required)
assert all(not p.is_symlink() for p in files.values())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
hidden = {sha(p) for name, p in files.items() if name.startswith(("solution/", "tests/"))}
assert not any(sha(p) in hidden for name, p in files.items() if name.startswith("environment/"))
for name, path in files.items():
    if name.endswith(".py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=name)
        if name.startswith("tests/"):
            for node in ast.walk(module):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith(("reference", "solution", "curation"))
    if name.endswith(".sh") or name == "environment/bin/ddi-ledger":
        assert path.read_bytes().startswith(b"#!/bin/bash\n") and b"\r" not in path.read_bytes(), name
expected = {
    "drug_list.csv": "208edfd36b34dc7f2d877f3b86636cff5fc14c11ff5617466b92b2633890a513",
    "DDI_event.csv": "3efbd7ade6ef3c6d3e0fb0422653b7689912b5a75316a29d85c8e26072bff311",
    "newddi.csv": "673d7ed6a0f3ecfdeaa1df54295f98ddf45266a837f6ec3a6a5f7934710d3b72",
}
for name, digest in expected.items():
    assert sha(files["environment/data/" + name]) == digest, name
config = tomllib.loads(files["task.toml"].read_text(encoding="utf-8"))
assert config["schema_version"] == "1.3"
assert config["environment"]["allow_internet"] is True
assert config["agent"]["timeout_sec"] == 3600
assert config["verifier"]["timeout_sec"] == 900
docker = files["environment/Dockerfile"].read_text(encoding="utf-8")
assert "rdkit==2025.3.6" in docker and "solution/" not in docker and "tests/" not in docker
tests = ast.parse(files["tests/test_outputs.py"].read_text(encoding="utf-8"))
names = next(ast.literal_eval(n.value) for n in tests.body
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NAMES" for t in n.targets))
assert len(names) == len(set(names)) == 20
instruction = files["instruction.md"].read_text(encoding="utf-8")
for clause in ("exactly once", "raw JSON file bytes", "after_prepare", "after_current",
               "never make `CURRENT` regress", "serialization lock", "process exits",
               "0.20", "0.25", "0.30", "0.05"):
    assert clause in instruction, clause
print(json.dumps({"status": "PASS", "files": len(files), "checks": len(names),
                  "weights": {"curation": .20, "batch": .25, "crash": .30,
                              "generation_reader": .20, "diagnostics": .05},
                  "environment_hidden_exact_duplicates": 0,
                  "original_csv_sha256": expected, "allow_internet": True}, indent=2))
