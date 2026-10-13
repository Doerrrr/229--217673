"""Static boundary/contract checks, with no candidate execution or model calls."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import tomllib

from certificate_check import parse_input
from fixtures import CHECKS

ROOT = Path(__file__).resolve().parent
TASK = ROOT / "runtime_task_v01"


def main():
    config = tomllib.loads((TASK / "task.toml").read_text(encoding="utf-8"))
    assert config["schema_version"] == "1.3" and config["environment"]["allow_internet"] is True
    assert config["agent"]["timeout_sec"] == config["verifier"]["timeout_sec"] == 3600
    assert len(CHECKS) == 20 and round(sum(item[2] for item in CHECKS), 6) == 1
    instruction = (TASK / "instruction.md").read_text(encoding="utf-8")
    assert all(name in instruction for name, _, _ in CHECKS)
    assert "120 seconds" in instruction and "10 seconds" in instruction
    assert not any(text in instruction for text in ("ledger scores", "blind score", "<=0.700", "https://github.com"))
    for path in (TASK / "environment/data").glob("*.json"):
        parse_input(path.read_bytes())
    hidden_hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (TASK / "tests").rglob("*") if p.is_file()}
    copied = [p for p in (TASK / "environment").rglob("*") if p.is_file()]
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() not in hidden_hashes for p in copied)
    for path in [p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts]:
        ast.parse(path.read_text(encoding="utf-8"))
    for path in copied:
        if path.suffix == ".py" or "bin" in path.parts or path.name == "Dockerfile":
            assert b"\r" not in path.read_bytes(), "Linux runtime must use LF: " + str(path)
    assert (TASK / "tests/certificate_check.py").read_bytes() == (ROOT / "certificate_check.py").read_bytes()
    assert (TASK / "tests/fixtures.py").read_bytes() == (ROOT / "fixtures.py").read_bytes()
    print(json.dumps({"status": "PASS", "checks": 20, "duplicated_hidden_files": 0,
                      "allow_internet": True, "task_execution": False, "model_calls": 0}))


if __name__ == "__main__":
    main()
