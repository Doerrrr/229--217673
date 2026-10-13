"""Frozen, root-only rule grading; execute untrusted answers as UID/GID 10001.

No production reference solver or stored expected output is imported.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import time

from certificate_check import canonical, check_part
from fixtures import CHECKS, diamond, scored_cases, serial_fixture

LOGS = Path("/logs/verifier")
COMMAND = "/usr/local/bin/ddi-lineage"
UID = GID = 10001


def child_identity():
    os.setsid()
    os.setgroups([])
    os.setgid(GID)
    os.setuid(UID)
    # Linux PR_SET_NO_NEW_PRIVS: an answer cannot regain root through exec.
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "cannot set no_new_privs")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))


def invoke(arguments, folder, label, invalid=False):
    stdout = LOGS / (label + ".stdout")
    stderr = LOGS / (label + ".stderr")
    started = time.monotonic()
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen([COMMAND, *arguments], cwd=folder, stdout=out, stderr=err,
                                   preexec_fn=child_identity,
                                   env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(folder),
                                        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
        timeout = 10 if invalid else 120
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=5)
        # No answer descendants may continue changing later tests.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return {"exit_code": code, "timed_out": timed_out,
            "stderr_nonempty": stderr.stat().st_size > 0,
            "elapsed_sec": round(time.monotonic() - started, 3)}


def workspace():
    folder = Path(tempfile.mkdtemp(prefix="lineage-", dir="/tmp"))
    folder.chmod(0o777)
    return folder


def output_bytes(out):
    result = {}
    for name in ("proof.json", "report.json"):
        path = out / name
        assert path.is_file() and not path.is_symlink(), "missing/nonregular output: " + name
        result[name] = path.read_bytes()
    return result


def input_at(folder, raw):
    path = folder / "observations.json"
    path.write_bytes(raw)
    path.chmod(0o644)
    return path


def valid_run(raw, label, out=None, folder=None):
    folder = folder or workspace()
    input_path = input_at(folder, raw)
    out = out or folder / "results"
    run = invoke(["--input", str(input_path), "--out-dir", str(out)], folder, label)
    assert run["exit_code"] == 0 and not run["timed_out"], "valid command failed: " + json.dumps(run)
    return folder, out, run


def semantic_check(name, section, data):
    raws = [canonical(data)]
    if name == "compressed_80_source_family":
        raws.append(canonical(serial_fixture(48)))
    runs = []
    for index, raw in enumerate(raws):
        _, out, run = valid_run(raw, name + "_" + str(index))
        proof_path = out / "proof.json"
        assert proof_path.is_file() and not proof_path.is_symlink(), "missing proof"
        report_path = out / "report.json"
        report = report_path.read_bytes() if report_path.is_file() and not report_path.is_symlink() else b""
        check_part(raw, proof_path.read_bytes(), report, section)
        runs.append(run)
    return {"commands": runs, "section": section}


def determinism_check():
    data = diamond(shared=True)
    data["queries"][0]["condition"] = [{"source_id": "b", "value": True},
                                      {"source_id": "c", "value": False}]
    raw = canonical(data)
    folder, out, first = valid_run(raw, "det_first")
    expected = output_bytes(out)
    check_part(raw, expected["proof.json"], expected["report.json"], "serialization")
    _, _, second = valid_run(raw, "det_repeat", out=out, folder=folder)
    assert output_bytes(out) == expected, "identical-input bytes changed"
    shuffled = deepcopy(data)
    for key in ("nodes", "sources", "edges", "queries"):
        shuffled[key].reverse()
    for item in shuffled["queries"]:
        item["event_types"].reverse()
        item["condition"].reverse()
    _, _, third = valid_run(canonical(shuffled), "det_permuted", out=out, folder=folder)
    assert output_bytes(out) == expected, "collection permutation changed output bytes"
    return {"commands": [first, second, third]}


def invalid_inputs():
    base = diamond(shared=True)
    cases = [("malformed_utf8", b"\xff"), ("bad_json", b"{"),
             ("duplicate_json_key", canonical(base).replace(b'"version":1', b'"version":1,"version":1'))]
    def add(name, change):
        data = deepcopy(base)
        change(data)
        cases.append((name, canonical(data)))
    add("unknown_field", lambda d: d.update({"unknown": 1}))
    add("missing_field", lambda d: d.pop("nodes"))
    add("boolean_version", lambda d: d.update(version=True))
    add("empty_nodes", lambda d: d.update(nodes=[]))
    add("duplicate_node", lambda d: d["nodes"].append(d["nodes"][0]))
    add("nonascii_id", lambda d: d["nodes"].__setitem__(0, "药物"))
    add("duplicate_source", lambda d: d["sources"].append(deepcopy(d["sources"][0])))
    add("boolean_numerator", lambda d: d["sources"][0].update(numerator=True))
    add("zero_denominator", lambda d: d["sources"][0].update(denominator=0))
    add("unknown_endpoint", lambda d: d["edges"][0].update(d1="missing"))
    add("unknown_source", lambda d: d["edges"][0].update(source_id="missing"))
    add("duplicate_edge", lambda d: d["edges"].append(deepcopy(d["edges"][0])))
    add("boolean_event", lambda d: d["edges"][0].update(type=True))
    add("duplicate_query", lambda d: d["queries"].append(deepcopy(d["queries"][0])))
    add("empty_queries", lambda d: d.update(queries=[]))
    add("duplicate_event_filter", lambda d: d["queries"][0].update(event_types=[5, 5]))
    add("condition_nonboolean", lambda d: d["queries"][0].update(condition=[{"source_id": "a", "value": 1}]))
    add("duplicate_condition", lambda d: d["queries"][0].update(condition=[{"source_id": "a", "value": True}, {"source_id": "a", "value": False}]))
    add("unknown_condition_source", lambda d: d["queries"][0].update(condition=[{"source_id": "missing", "value": True}]))
    add("leading_zero_rank", lambda d: d["queries"][0].update(ranks=["00"]))
    add("duplicate_rank", lambda d: d["queries"][0].update(ranks=["0", "0"]))
    add("numeric_rank", lambda d: d["queries"][0].update(ranks=[0]))
    add("rank_too_long", lambda d: d["queries"][0].update(ranks=["1" * 129]))
    add("missing_source_field", lambda d: d["sources"][0].pop("denominator"))
    add("unknown_source_field", lambda d: d["sources"][0].update(extra=0))
    add("missing_edge_field", lambda d: d["edges"][0].pop("source_id"))
    add("unknown_query_field", lambda d: d["queries"][0].update(extra=0))
    add("unknown_condition_field", lambda d: d["queries"][0].update(condition=[{"source_id": "a", "value": True, "extra": 0}]))
    add("unknown_query_endpoint", lambda d: d["queries"][0].update(end="missing"))
    add("event_out_of_range", lambda d: d["edges"][0].update(type=2**63))
    add("probability_out_of_range", lambda d: d["sources"][0].update(numerator=3))
    return cases


def seeded_outputs(label):
    raw = canonical(diamond())
    folder, out, run = valid_run(raw, label)
    output_bytes(out)
    sentinels = {"proof.json": b"old-proof\x00\xff\n", "report.json": b"old-report\r\n\x00"}
    for name, body in sentinels.items():
        path = out / name
        path.write_bytes(body)
        path.chmod(0o666)
    out.chmod(0o777)
    return folder, out, sentinels, run


def fatal_check():
    folder, out, sentinels, seed = seeded_outputs("fatal_seed")
    runs = [seed]
    for name, raw in invalid_inputs():
        path = input_at(folder, raw)
        run = invoke(["--input", str(path), "--out-dir", str(out)], folder, "fatal_" + name, invalid=True)
        assert not run["timed_out"] and run["exit_code"] != 0 and run["stderr_nonempty"], name
        assert output_bytes(out) == sentinels, "fatal input overwrote outputs: " + name
        runs.append(run)
    return {"commands": runs, "invalid_cases": len(runs) - 1}


def cli_check():
    folder, out, sentinels, seed = seeded_outputs("cli_seed")
    path = input_at(folder, canonical(diamond()))
    missing = folder / "missing_input.json"
    arguments = [[], ["--input", str(path)], ["--out-dir", str(out)],
                 ["--input", str(missing), "--out-dir", str(out)]]
    runs = [seed]
    for index, args in enumerate(arguments):
        run = invoke(args, folder, "cli_bad_" + str(index), invalid=True)
        assert not run["timed_out"] and run["exit_code"] != 0 and run["stderr_nonempty"]
        assert output_bytes(out) == sentinels
        runs.append(run)
    fresh = folder / "new" / "deep" / "release"
    assert not fresh.exists()
    raw = canonical(diamond())
    _, _, run = valid_run(raw, "cli_new_directory", out=fresh, folder=folder)
    outputs = output_bytes(fresh)
    check_part(raw, outputs["proof.json"], outputs["report.json"], "serialization")
    runs.append(run)
    return {"commands": runs, "created_absent_multilevel_directory": True}


def confinement_check():
    assert os.getuid() == 0, "verifier must run as root to isolate untrusted answer"
    for path in (Path("/tests"), LOGS):
        path.chmod(0o700)
    script = ("import os,pathlib; assert os.getuid()==10001; "
              "paths=['/tests/test_outputs.py','/logs/verifier/reward.txt']; "
              "assert all(not os.access(p,os.R_OK) for p in paths)")
    probe = subprocess.run(["python3", "-c", script], preexec_fn=child_identity,
                           capture_output=True, timeout=10)
    assert probe.returncode == 0, "candidate could access hidden verifier paths"
    return {"answer_uid": UID, "hidden_tests_readable": False, "reward_file_readable": False}


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    confinement = confinement_check()
    started = time.monotonic()
    records = []
    handlers = {"canonical_permutation_determinism": determinism_check,
                "fatal_input_nonclobber": fatal_check, "cli_and_new_output_directory": cli_check}
    semantic = {name: (section, data) for name, section, data in scored_cases()}
    for name, section, weight in CHECKS:
        try:
            evidence = semantic_check(name, *semantic[name]) if name in semantic else handlers[name]()
            records.append({"name": name, "weight": weight, "passed": True, "evidence": evidence})
        except (AssertionError, ValueError, KeyError, TypeError, OSError, RecursionError) as error:
            records.append({"name": name, "weight": weight, "passed": False,
                            "error": type(error).__name__ + ": " + str(error)})
    score = round(sum(record["weight"] for record in records if record["passed"]), 6)
    result = {"status": "completed", "reward": score, "passed_checks": sum(r["passed"] for r in records),
              "total_checks": len(records), "elapsed_sec": round(time.monotonic() - started, 3),
              "confinement": confinement, "checks": records, "reference_solution_imported": False}
    (LOGS / "details.json").write_bytes(canonical(result))
    (LOGS / "reward.txt").write_text(f"{score:.6f}\n", encoding="ascii")
    print(json.dumps({key: result[key] for key in ("status", "reward", "passed_checks", "total_checks", "elapsed_sec")}))


if __name__ == "__main__":
    main()
