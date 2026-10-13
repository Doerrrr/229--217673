"""Exercise installation/grading with finite hand-known controls, not an agent.

The canned fixture dispatcher is NOT a general Oracle solution. It is never
included in a public packet or used as evidence of model difficulty.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

from certificate_check import canonical, parse_input
from fixtures import diamond, scored_cases, serial_fixture
from quality_bench import control

ROOT = Path(__file__).resolve().parent
TASK = ROOT / "runtime_task_v01"


def normalized(data):
    data = parse_input(canonical(data))
    for query in data["queries"]:
        query["event_types"].sort()
        query["condition"].sort(key=lambda item: item["source_id"])
    return canonical(data)


def control_records():
    inputs = [data for _, _, data in scored_cases()]
    inputs += [serial_fixture(48)]
    det = diamond(shared=True)
    det["queries"][0]["condition"] = [{"source_id": "b", "value": True},
                                     {"source_id": "c", "value": False}]
    inputs += [det, json.loads((TASK / "environment/data/evidence_graph.json").read_bytes())]
    records = {}
    for data in inputs:
        _, proof, report = control(data)
        key = hashlib.sha256(normalized(data)).hexdigest()
        records[key] = {"proof": proof.decode(), "report": report.decode()}
    return records


CONTROL_PREFIX = '''"""AUTHOR-ONLY finite known-fixture dispatcher; not a general solver."""
import argparse, hashlib, json, pathlib, sys
def pairs(items):
    result={}
    for k,v in items:
        if k in result: raise ValueError("duplicate key")
        result[k]=v
    return result
def canonical(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\\n").encode()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=pathlib.Path)
    p.add_argument("--out-dir",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        d=json.loads(a.input.read_bytes().decode("utf-8"),object_pairs_hook=pairs)
        d["nodes"].sort()
        for collection,key in (("sources","source_id"),("edges","edge_id"),("queries","query_id")):
            d[collection].sort(key=lambda x:x[key])
        for q in d["queries"]:
            q["event_types"].sort(); q["condition"].sort(key=lambda x:x["source_id"])
        row=RECORDS[hashlib.sha256(canonical(d)).hexdigest()]
        a.out_dir.mkdir(parents=True,exist_ok=True)
        (a.out_dir/"proof.json").write_bytes(row["proof"].encode())
        (a.out_dir/"report.json").write_bytes(row["report"].encode())
        return 0
    except Exception as error:
        print("known-fixture control rejected input: "+str(error),file=sys.stderr); return 1
'''


def answer_zip(records, target, variant):
    if variant == "nop":
        source = (TASK / "environment/app/lineage.py").read_bytes()
    else:
        rows = deepcopy(records)
        for row in rows.values():
            if variant == "bad_probability":
                report = json.loads(row["report"])
                for item in report["results"]:
                    if item["probability"] is None:
                        item["probability"] = {"numerator": "1", "denominator": "1"}
                        item["probability_state"] = "DEFINED"
                    else:
                        item["probability"]["numerator"] = str(int(item["probability"]["numerator"]) + 1)
                row["report"] = canonical(report).decode()
            elif variant == "bad_minimal":
                proof = json.loads(row["proof"])
                for item in proof["queries"]:
                    item["minimal_root"] = 0
                body = canonical(proof)
                report = json.loads(row["report"])
                report["proof_sha256"] = hashlib.sha256(body).hexdigest()
                row["proof"], row["report"] = body.decode(), canonical(report).decode()
        source = (CONTROL_PREFIX + "\nRECORDS=" + repr(rows) +
                  "\nif __name__=='__main__': raise SystemExit(main())\n").encode()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in (("app/lineage.py", source), ("answer_notes.md", b"AUTHOR QUALITY CONTROL ONLY; not an agent answer or production Oracle.\n")):
            info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)


def stage_operator(destination, commit="UNFROZEN_QUALITY_ONLY"):
    destination.mkdir(parents=True)
    shutil.copytree(TASK, destination / "task", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(ROOT / "frozen_evaluator.py", destination / "evaluate.py")
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest = {"task_commit": commit, "task_digest": hashlib.sha256(canonical(files)).hexdigest(), "files": files}
    (destination / "manifest.json").write_bytes(canonical(manifest))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--operator", type=Path, help="Use final frozen operator instead of a staging copy")
    args = p.parse_args()
    assert not args.out.exists()
    args.out.mkdir(parents=True)
    operator = args.operator or args.out / "operator"
    if not args.operator:
        stage_operator(operator)
    records = control_records()
    results = []
    for variant, expected in (("positive_known_fixtures", 1.0), ("nop", 0.0),
                              ("bad_probability", 0.8), ("bad_minimal", 0.45)):
        answer = args.out / (variant + ".zip")
        answer_zip(records, answer, variant)
        score = args.out / variant
        subprocess.run([sys.executable, str(operator / "evaluate.py"), "--answer", str(answer),
                        "--out", str(score), "--docker-context", "desktop-linux"], check=True)
        result = json.loads((score / "result.json").read_text(encoding="utf-8"))
        assert result["status"] == "completed" and result["reward"] == expected, (variant, result)
        results.append({"variant": variant, "score": result["reward"],
                        "answer_sha256": result["answer_sha256"], "normal_exit": True,
                        "grader_seconds": result["grading_elapsed_sec"]})
    receipt = {"status": "PASS", "controls": results, "model_calls": 0,
               "production_oracle_solution": False, "external_blind_score": None,
               "operator_is_frozen": args.operator is not None}
    (args.out / "quality_receipt.json").write_bytes(canonical(receipt))
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
