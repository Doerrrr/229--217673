#!/usr/bin/env python3
"""Independent black-box checks of the public DDI ledger contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback


COMMAND = "ddi-ledger"
OUT = Path("/logs/verifier")
NAMES = [
    "curation_alias_conflict", "curation_event_drop", "curation_directed_order",
    "curation_real_data", "batch_ordered_replay", "batch_duplicate_idempotency",
    "batch_conflict_and_gap", "batch_strict_json", "batch_two_writers",
    "crash_before_commit", "crash_after_commit", "crash_before_advertise",
    "crash_after_advertise", "recovery_stale_stage", "recovery_no_clobber",
    "generation_hashes", "generation_idempotent", "reader_pinned",
    "reader_corruption", "fatal_diagnostics",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def run(*argv: str, status: int = 0):
    result = subprocess.run([COMMAND, *map(str, argv)], capture_output=True, text=True,
                            timeout=90)
    if result.returncode != status:
        raise AssertionError(f"exit {result.returncode} != {status}: {argv}; {result.stderr[:350]}")
    if status not in (0, 75):
        assert result.stderr.strip(), f"no diagnostic: {argv}"
    return result


def failed(*argv: str):
    result = subprocess.run([COMMAND, *map(str, argv)], capture_output=True, text=True,
                            timeout=90)
    assert result.returncode not in (0, 75) and result.stderr.strip(), (
        argv, result.returncode, result.stderr[:350])
    return result


def fixture(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "drugs.csv").write_bytes(
        b"A,CCO\nB,OCC\nC,CCN\nBAD,not_smiles\nX,CCO\nX,CCC\n")
    (root / "events.csv").write_bytes(b"5,alpha\n05,alpha\n7,beta\n7,gamma\n")
    (root / "interactions.csv").write_bytes(
        b"d1,type,d2\nA,5,C\nB,05,C\nC,5,A\nA,7,C\nA,5,B\nA,5,A\n"
        b"BAD,5,C\nNO,5,C\nX,5,C\n")
    return root / "state"


def bootstrap(root: Path, state: Path):
    run("bootstrap", "--state-dir", state, "--drugs", root / "drugs.csv",
        "--events", root / "events.csv", "--interactions", root / "interactions.csv")


def base(root: Path):
    state = fixture(root)
    bootstrap(root, state)
    run("publish", "--state-dir", state)
    return state


def batch(root: Path, name: str, number: int, operations: list[dict]):
    path = root / (name + ".json")
    path.write_bytes(canonical({"batch_id": name, "number": number,
                                "operations": operations}))
    return path


def b1(root: Path):
    return batch(root, "b1", 1, [
        {"feed": "drug", "op": "UPSERT", "drug_id": "0", "SMILES": "OCC"},
        {"feed": "event", "op": "UPSERT", "event_type": "07", "description": "beta"},
        {"feed": "interaction", "op": "ADD", "d1": "0", "type": "05", "d2": "C"},
    ])


def latest(state: Path):
    generation = (state / "CURRENT").read_text(encoding="ascii").strip()
    assert len(generation) == 64 and set(generation) <= set("0123456789abcdef")
    folder = state / "releases" / generation
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    return generation, folder, manifest, report


def check_hashes(state: Path):
    generation, folder, manifest, report = latest(state)
    assert manifest["generation_id"] == generation
    assert set(manifest) == {"generation_id", "state_id", "base", "batches", "files"}
    assert set(manifest["files"]) == {"drugs_clean.csv", "interactions_clean.csv", "report.json"}
    assert (folder / "manifest.json").read_bytes() == canonical(manifest)
    assert (folder / "report.json").read_bytes() == canonical(report)
    assert (state / "CURRENT").read_bytes() == (generation + "\n").encode("ascii")
    assert set(manifest["base"]) == {"drugs", "events", "interactions"}
    assert all(set(receipt) == {"batch_id", "number", "sha256"}
               for receipt in manifest["batches"])
    assert set(report) == {"state_id", "batch_number", "raw_rows", "drugs",
                           "events", "interactions", "files"}
    assert manifest["state_id"] == sha(canonical({"base": manifest["base"],
                                                   "batches": manifest["batches"]}))
    assert generation == sha(canonical({"state_id": manifest["state_id"],
                                         "files": manifest["files"]}))
    for name, wanted in manifest["files"].items():
        assert sha((folder / name).read_bytes()) == wanted
    assert report["state_id"] == manifest["state_id"]
    assert report["batch_number"] == (manifest["batches"][-1]["number"]
                                      if manifest["batches"] else 0)
    assert report["files"] == {name: manifest["files"][name] for name in
                               ("drugs_clean.csv", "interactions_clean.csv")}
    return generation, folder, manifest, report


def check_curation_alias_conflict(root: Path):
    state = base(root)
    _, folder, _, report = latest(state)
    lines = (folder / "drugs_clean.csv").read_text().splitlines()
    assert lines == ["drug_id,canonical_smiles,aliases", "A,CCO,A;B", "C,CCN,C"]
    assert report["drugs"] == {"valid_ids": 3, "unique_molecules": 2,
                               "invalid_rows": 1, "invalid_only_ids": ["BAD"],
                               "conflicting_ids": ["X"]}
    edge_root = root / "csv-boundary"
    edge_root.mkdir()
    (edge_root / "drugs.csv").write_bytes(
        b'\xef\xbb\xbf\n , \n"A,one",CCO\n"B""two",OCC\nC,CCN\n')
    (edge_root / "events.csv").write_bytes(
        b'\xef\xbb\xbf\n5,"alpha,\nquoted ""word"""\n')
    (edge_root / "interactions.csv").write_bytes(
        b'\xef\xbb\xbf\n\nd1,type,d2\n"B""two",05,C\nC,5,"A,one"\n')
    bootstrap(edge_root, edge_root / "state")
    run("publish", "--state-dir", edge_root / "state")
    _, edge_folder, _, edge_report = check_hashes(edge_root / "state")
    assert (edge_folder / "drugs_clean.csv").read_bytes() == (
        b'drug_id,canonical_smiles,aliases\n"A,one",CCO,"A,one;B""two"\nC,CCN,C\n')
    assert (edge_folder / "interactions_clean.csv").read_bytes() == (
        b'd1,type,d2\n"A,one",5,C\nC,5,"A,one"\n')
    assert edge_report["raw_rows"] == {"drugs": 3, "events": 1, "interactions": 2}


def check_curation_event_drop(root: Path):
    state = base(root)
    report = latest(state)[3]
    assert report["events"] == {"valid_types": 1, "invalid_rows": 0,
                                "conflicting_types": [7]}
    dropped = report["interactions"]["dropped"]
    assert dropped == {"malformed": 0, "missing_drug": 1, "conflicting_drug": 1,
                       "invalid_drug": 1, "unknown_type": 0, "conflicting_type": 1,
                       "self_interaction": 1, "alias_self_interaction": 1,
                       "duplicate": 1}


def check_curation_directed_order(root: Path):
    state = base(root)
    folder = latest(state)[1]
    assert (folder / "interactions_clean.csv").read_text().splitlines() == [
        "d1,type,d2", "A,5,C", "C,5,A"]
    change = b1(root)
    run("apply", "--state-dir", state, "--batch", change)
    run("publish", "--state-dir", state)
    _, folder, _, report = latest(state)
    assert (folder / "drugs_clean.csv").read_text().splitlines()[1] == "0,CCO,0;A;B"
    assert (folder / "interactions_clean.csv").read_text().splitlines() == [
        "d1,type,d2", "0,5,C", "0,7,C", "C,5,0"]
    assert report["events"]["conflicting_types"] == []


def check_curation_real_data(root: Path):
    state = root / "state"
    run("bootstrap", "--state-dir", state, "--drugs", "/data/drug_list.csv",
        "--events", "/data/DDI_event.csv", "--interactions", "/data/newddi.csv")
    run("publish", "--state-dir", state)
    _, folder, _, report = check_hashes(state)
    assert report["raw_rows"]["drugs"] > 1000
    assert report["raw_rows"]["interactions"] > 100000
    assert report["drugs"]["unique_molecules"] > 1000
    assert report["interactions"]["kept"] > 100000
    assert (folder / "drugs_clean.csv").read_bytes().startswith(b"drug_id,canonical_smiles,aliases\n")


def check_batch_ordered_replay(root: Path):
    state = base(root)
    first = b1(root)
    second = batch(root, "b2", 2, [
        {"feed": "drug", "op": "DELETE", "drug_id": "0"},
        {"feed": "interaction", "op": "DELETE", "d1": "B", "type": "5", "d2": "C"},
        {"feed": "interaction", "op": "ADD", "d1": "C", "type": "5", "d2": "A"},
    ])
    run("apply", "--state-dir", state, "--batch", first)
    run("apply", "--state-dir", state, "--batch", second)
    run("publish", "--state-dir", state)
    _, folder, manifest, report = latest(state)
    assert [x["number"] for x in manifest["batches"]] == [1, 2]
    assert manifest["base"] == {
        "drugs": sha((root / "drugs.csv").read_bytes()),
        "events": sha((root / "events.csv").read_bytes()),
        "interactions": sha((root / "interactions.csv").read_bytes()),
    }
    assert [x["sha256"] for x in manifest["batches"]] == [
        sha(first.read_bytes()), sha(second.read_bytes())]
    assert (folder / "drugs_clean.csv").read_text().splitlines()[1] == "A,CCO,A;B"
    assert (folder / "interactions_clean.csv").read_text().splitlines() == [
        "d1,type,d2", "A,5,C", "A,7,C", "C,5,A"]
    assert report["batch_number"] == 2


def check_batch_duplicate_idempotency(root: Path):
    state = base(root)
    first = b1(root)
    second = batch(root, "b2", 2, [])
    for path in (first, second, first):
        run("apply", "--state-dir", state, "--batch", path)
    run("publish", "--state-dir", state)
    assert [x["batch_id"] for x in latest(state)[2]["batches"]] == ["b1", "b2"]


def check_batch_conflict_and_gap(root: Path):
    state = base(root)
    old_generation = latest(state)[0]
    bootstrap(root, state)
    assert latest(state)[0] == old_generation
    other_base = root / "different-drugs.csv"
    other_base.write_bytes((root / "drugs.csv").read_bytes() + b"NEW,CCO\n")
    failed("bootstrap", "--state-dir", state, "--drugs", other_base,
           "--events", root / "events.csv", "--interactions", root / "interactions.csv")
    assert latest(state)[0] == old_generation
    first = b1(root)
    run("apply", "--state-dir", state, "--batch", first)
    old = first.read_bytes()
    first.write_bytes(old + b" \n")
    failed("apply", "--state-dir", state, "--batch", first)
    gap = batch(root, "gap", 3, [])
    failed("apply", "--state-dir", state, "--batch", gap)
    failed("apply", "--state-dir", state, "--batch", gap,
           "--crash", "after_prepare")
    reuse = batch(root, "other", 1, [])
    failed("apply", "--state-dir", state, "--batch", reuse)
    failed("apply", "--state-dir", state, "--batch", first,
           "--crash", "after_prepare")
    run("publish", "--state-dir", state)
    assert [x["batch_id"] for x in latest(state)[2]["batches"]] == ["b1"]


def check_batch_strict_json(root: Path):
    state = base(root)
    bad = root / "bad.json"
    samples = [
        b'{"batch_id":"b","batch_id":"b","number":1,"operations":[]}',
        b'{"batch_id":"b","number":true,"operations":[]}',
        b'{"batch_id":"b","number":1,"operations":[],"extra":0}',
        b'{"batch_id":"b","number":1,"operations":[{"feed":"drug","op":"UPSERT","drug_id":"A"}]}',
        b'{"batch_id":"b","number":1,"operations":NaN}',
        b'{"batch_id":"b","number":0,"operations":[]}',
        b'{"batch_id":"b","number":1.0,"operations":[]}',
        b'{"batch_id":"bad/id","number":1,"operations":[]}',
        b'{"batch_id":"b","number":1,"operations":[{"feed":"event","op":"DELETE","event_type":"-1"}]}',
        b'{"batch_id":"b","number":1,"operations":[{"feed":"drug","op":"DELETE","drug_id":"A","drug_id":"A"}]}',
        b'{"batch_id":"b","number":1,"operations":[{"feed":"drug","op":"DELETE","drug_id":"A","extra":0}]}',
        b'{"batch_id":"b","number":1,"operations":[{"feed":"interaction","op":"ADD","d1":" ","type":"5","d2":"C"}]}',
    ]
    before = (state / "CURRENT").read_bytes()
    for raw in samples:
        bad.write_bytes(raw)
        failed("apply", "--state-dir", state, "--batch", bad)
        assert (state / "CURRENT").read_bytes() == before
    run("publish", "--state-dir", state)
    assert latest(state)[2]["batches"] == []


def check_batch_two_writers(root: Path):
    state = base(root)
    one = batch(root, "left", 1, [])
    two = batch(root, "right", 1, [])
    commands = [[COMMAND, "apply", "--state-dir", str(state), "--batch", str(p)]
                for p in (one, two)]
    procs = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for command in commands]
    results = [process.communicate(timeout=30) for process in procs]
    codes = sorted(process.returncode for process in procs)
    assert codes[0] == 0 and codes[1] not in (0, 75), (codes, results)
    run("recover", "--state-dir", state)
    assert len(latest(state)[2]["batches"]) == 1


def check_crash_before_commit(root: Path):
    state = base(root)
    old = (state / "CURRENT").read_bytes()
    first = b1(root)
    run("apply", "--state-dir", state, "--batch", first,
        "--crash", "after_prepare", status=75)
    assert (state / "CURRENT").read_bytes() == old
    run("recover", "--state-dir", state)
    assert latest(state)[2]["batches"] == []
    run("apply", "--state-dir", state, "--batch", first)


def check_crash_after_commit(root: Path):
    state = base(root)
    first = b1(root)
    run("apply", "--state-dir", state, "--batch", first,
        "--crash", "after_commit", status=75)
    run("apply", "--state-dir", state, "--batch", first)
    run("recover", "--state-dir", state)
    assert [x["batch_id"] for x in latest(state)[2]["batches"]] == ["b1"]


def check_crash_before_advertise(root: Path):
    state = base(root)
    old = latest(state)[0]
    run("apply", "--state-dir", state, "--batch", b1(root))
    run("publish", "--state-dir", state, "--crash", "after_generation", status=75)
    assert latest(state)[0] == old
    run("recover", "--state-dir", state)
    assert latest(state)[0] != old and latest(state)[3]["batch_number"] == 1


def check_crash_after_advertise(root: Path):
    state = base(root)
    run("apply", "--state-dir", state, "--batch", b1(root))
    run("publish", "--state-dir", state, "--crash", "after_current", status=75)
    new = check_hashes(state)[0]
    run("recover", "--state-dir", state)
    assert latest(state)[0] == new


def check_recovery_stale_stage(root: Path):
    state = base(root)
    stale = state / "releases" / ".stage-interrupted"
    stale.mkdir()
    (stale / "manifest.json").write_bytes(b"partial")
    run("apply", "--state-dir", state, "--batch", b1(root))
    run("recover", "--state-dir", state)
    assert check_hashes(state)[3]["batch_number"] == 1


def check_recovery_no_clobber(root: Path):
    state = base(root)
    old_gen, old_folder, _, _ = latest(state)
    old_bytes = {p.name: p.read_bytes() for p in old_folder.iterdir() if p.is_file()}
    run("apply", "--state-dir", state, "--batch", b1(root))
    run("recover", "--state-dir", state)
    assert latest(state)[0] != old_gen
    assert {p.name: p.read_bytes() for p in old_folder.iterdir() if p.is_file()} == old_bytes


def check_generation_hashes(root: Path):
    state = base(root)
    check_hashes(state)
    run("apply", "--state-dir", state, "--batch", b1(root))
    run("publish", "--state-dir", state)
    check_hashes(state)


def check_generation_idempotent(root: Path):
    state = base(root)
    generation, folder, _, _ = latest(state)
    before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    run("publish", "--state-dir", state)
    assert latest(state)[0] == generation
    assert {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()} == before
    # A documented barrier pins an older publisher. The later worker may
    # finish or remain serialized; either is permitted. Only final state,
    # not a scheduling assumption, determines the assertion.
    ready, cont = root / "publish.ready", root / "publish.continue"
    old_publisher = subprocess.Popen(
        [COMMAND, "publish", "--state-dir", str(state), "--ready", str(ready),
         "--continue", str(cont)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    worker = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and old_publisher.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.read_bytes() == b"ready\n"
        first = b1(root)
        script = (
            "import subprocess,sys; "
            "subprocess.run(sys.argv[1:5]+['--batch',sys.argv[5]],check=True); "
            "subprocess.run([sys.argv[1],'publish','--state-dir',sys.argv[4]],check=True)"
        )
        worker = subprocess.Popen(
            [sys.executable, "-c", script, COMMAND, "apply", "--state-dir",
             str(state), str(first)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 1.5
        while worker.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        cont.write_bytes(b"continue\n")
        old_stdout, old_stderr = old_publisher.communicate(timeout=30)
        worker_stdout, worker_stderr = worker.communicate(timeout=30)
        assert old_publisher.returncode == 0, (old_stdout, old_stderr)
        assert worker.returncode == 0, (worker_stdout, worker_stderr)
        assert check_hashes(state)[3]["batch_number"] == 1, "CURRENT regressed"
        assert {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()} == before
    finally:
        for process in (old_publisher, worker):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


def check_reader_pinned(root: Path):
    state = base(root)
    old = latest(state)[0]
    ready, cont = root / "reader.ready", root / "reader.continue"
    process = subprocess.Popen([COMMAND, "read", "--state-dir", str(state),
                                "--generation", "CURRENT", "--ready", str(ready),
                                "--continue", str(cont)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.read_bytes() == b"ready\n"
        run("apply", "--state-dir", state, "--batch", b1(root))
        run("publish", "--state-dir", state)
        assert latest(state)[0] != old
        cont.write_text("continue\n", encoding="ascii")
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["generation_id"] == old
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def check_reader_corruption(root: Path):
    state = base(root)
    generation, folder, _, _ = latest(state)
    output = run("read", "--state-dir", state, "--generation", generation)
    assert json.loads(output.stdout)["generation_id"] == generation
    (folder / "drugs_clean.csv").write_bytes(b"corrupt\n")
    failed("read", "--state-dir", state, "--generation", generation)


def check_fatal_diagnostics(root: Path):
    state = base(root)
    old_gen, old_folder, _, _ = latest(state)
    before = {p.name: p.read_bytes() for p in old_folder.iterdir() if p.is_file()}
    bad = root / "bad.json"
    bad.write_bytes(b"{")
    failed("apply", "--state-dir", state, "--batch", bad)
    failed("read", "--state-dir", state, "--generation", "../bad")
    failed("read", "--state-dir", state, "--generation", "CURRENT",
           "--ready", root / "ready-only")
    failed("publish", "--state-dir", state, "--ready", root / "publish-only")
    first = b1(root)
    failed("apply", "--state-dir", root / "missing-state", "--batch", first,
           "--crash", "after_prepare")
    invalid_csv = root / "invalid.csv"
    invalid_csv.write_bytes(b'd1,type,d2\n"unterminated')
    failed("bootstrap", "--state-dir", state, "--drugs", root / "drugs.csv",
           "--events", root / "events.csv", "--interactions", invalid_csv)
    assert latest(state)[0] == old_gen
    assert {p.name: p.read_bytes() for p in old_folder.iterdir() if p.is_file()} == before


CASES = [
    check_curation_alias_conflict, check_curation_event_drop,
    check_curation_directed_order, check_curation_real_data,
    check_batch_ordered_replay, check_batch_duplicate_idempotency,
    check_batch_conflict_and_gap, check_batch_strict_json, check_batch_two_writers,
    check_crash_before_commit, check_crash_after_commit, check_crash_before_advertise,
    check_crash_after_advertise, check_recovery_stale_stage, check_recovery_no_clobber,
    check_generation_hashes, check_generation_idempotent, check_reader_pinned,
    check_reader_corruption, check_fatal_diagnostics,
]


def main():
    assert len(NAMES) == len(CASES) == 20
    details = []
    for name, check in zip(NAMES, CASES):
        try:
            with tempfile.TemporaryDirectory(prefix="ddi-ledger-check-") as folder:
                check(Path(folder))
            details.append({"name": name, "weight": .05, "passed": True})
        except Exception:
            details.append({"name": name, "weight": .05, "passed": False,
                            "error": traceback.format_exc(limit=4)[-1200:]})
    reward = round(sum(item["weight"] for item in details if item["passed"]), 6)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "details.json").write_text(json.dumps({"verifier_completed": True,
                                                   "reward": reward,
                                                   "checks": details}, indent=2) + "\n",
                                       encoding="utf-8")
    (OUT / "reward.txt").write_text(f"{reward:.6f}\n", encoding="ascii")
    print(json.dumps({"reward": reward,
                      "failed": [x["name"] for x in details if not x["passed"]]}))


if __name__ == "__main__":
    main()
