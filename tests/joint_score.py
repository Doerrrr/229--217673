"""Additive, failure-isolated DDI curator / bridge / publication scorer."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

from test_joint import CHECKS as INTEGRATION_CHECKS


LOG = Path("/logs/verifier")
CURATOR = [
    ("basic_parsing", .03), ("malformed_reporting", .03),
    ("canonical_aliases", .08), ("drug_conflicts", .07),
    ("event_validation", .05), ("directed_filtering", .09),
    ("determinism_and_hashes", .05), ("failure_no_clobber", .08),
    ("real_dataset_smoke", .07), ("replay_and_cascade", .12),
    ("alias_rename_is_not_delta", .12),
    ("repeated_upserts_resolve_conflicts", .09),
    ("duplicate_and_reverse_replay", .05),
    ("bad_changes_no_clobber", .07),
]
BRIDGE = [
    ("connected_components", .15), ("individual_bridges", .15),
    ("two_edge_blocks", .15), ("key_replacement_retraction", .10),
    ("raw_ddi_reclassification", .10),
    ("bounded_temporal_throughput", .35),
]
assert abs(sum(weight for _, weight in CURATOR) - 1) < 1e-12
assert abs(sum(weight for _, weight in BRIDGE) - 1) < 1e-12
assert len(INTEGRATION_CHECKS) == 4


def run_script(name: str, command: list[str], timeout: int) -> dict:
    outcome = subprocess.run(command, text=True, capture_output=True,
                             check=False, timeout=timeout)
    (LOG / f"{name}.stdout").write_text(outcome.stdout[-100_000:], encoding="utf-8")
    (LOG / f"{name}.stderr").write_text(outcome.stderr[-10_000:], encoding="utf-8")
    if outcome.returncode != 0:
        raise RuntimeError(f"{name} trusted verifier exited {outcome.returncode}")
    return json.loads((LOG / f"{name}_details.json").read_text(encoding="utf-8"))


def main() -> None:
    LOG.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    all_checks = []
    try:
        # The bridge module writes its legacy output paths. Read and move its
        # result before the joint report replaces them.
        outcome = subprocess.run(
            [sys.executable, "/tests/bridge/test_outputs.py"], text=True,
            capture_output=True, check=False, timeout=650,
        )
        (LOG / "bridge.stdout").write_text(outcome.stdout[-100_000:], encoding="utf-8")
        (LOG / "bridge.stderr").write_text(outcome.stderr[-10_000:], encoding="utf-8")
        if outcome.returncode != 0:
            raise RuntimeError(f"bridge trusted verifier exited {outcome.returncode}")
        bridge_details = json.loads((LOG / "details.json").read_text(encoding="utf-8"))
        bridge_by_name = {item["name"]: item for item in bridge_details["checks"]}
        if set(bridge_by_name) != {name for name, _ in BRIDGE}:
            raise RuntimeError("bridge check list changed")

        curator_details = run_script("curator", [
            sys.executable, "/tests/curator/test_outputs.py",
            "--reward-file", str(LOG / "curator_reward.txt"),
            "--details-file", str(LOG / "curator_details.json"),
        ], timeout=300)
        curator_by_name = {item["name"]: item for item in curator_details.get("checks", [])}
        if curator_details.get("hard_gate") and set(curator_by_name) != {name for name, _ in CURATOR}:
            raise RuntimeError("curator check list changed")

        for name, weight in CURATOR:
            old = curator_by_name.get(name, {})
            all_checks.append({
                "name": "curator/" + name, "weight": round(.40 * weight, 6),
                "passed": bool(curator_details.get("hard_gate") and old.get("passed")),
                "error": old.get("error", curator_details.get("gate_error")),
            })
        for name, weight in BRIDGE:
            old = bridge_by_name[name]
            all_checks.append({
                "name": "bridge/" + name, "weight": round(.40 * weight, 6),
                "passed": bool(old["passed"]), "error": old.get("error"),
            })
        for name, function in INTEGRATION_CHECKS:
            try:
                function()
                passed, error = True, None
            except Exception as exc:
                passed, error = False, f"{type(exc).__name__}: {exc}"[:1200]
            all_checks.append({"name": "release/" + name, "weight": .05,
                               "passed": passed, "error": error})
        reward = round(sum(item["weight"] for item in all_checks if item["passed"]), 6)
        details = {"verifier_completed": True, "scoring": "additive, no cap",
                   "checks": all_checks, "reward": reward,
                   "elapsed_sec": round(time.monotonic() - started, 3)}
    except Exception as exc:
        details = {"verifier_completed": False, "error": f"{type(exc).__name__}: {exc}",
                   "checks": all_checks, "reward": 0.0,
                   "elapsed_sec": round(time.monotonic() - started, 3)}
        reward = 0.0
    (LOG / "details.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    (LOG / "reward.txt").write_text(f"{reward:.6f}\n", encoding="ascii")
    print(json.dumps({"reward": reward, "verifier_completed": details["verifier_completed"],
                      "elapsed_sec": details["elapsed_sec"]}), flush=True)


if __name__ == "__main__":
    main()
