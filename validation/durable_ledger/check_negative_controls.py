"""Probe an already frozen checker with intentionally broken author controls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--frozen", required=True, type=Path)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
frozen = args.frozen.resolve()
out = args.out.resolve()
assert not out.exists(), "Preserve old control evidence"
out.mkdir(parents=True)
private = frozen / "ddi_evaluator_private"
task = private / "task"
reference = (task / "solution/reference_ledger.py").read_text(encoding="utf-8")

def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)

wrong_identity = replace_once(reference, 'if old[0] != wanted:', 'if False:')
early_commit = replace_once(reference,
    '        if args.crash == "after_prepare":\n            os._exit(75)\n', '')
early_commit = replace_once(early_commit,
    '        if args.crash == "after_commit":\n',
    '        if args.crash == "after_prepare":\n            os._exit(75)\n'
    '        if args.crash == "after_commit":\n')
late_pin = replace_once(reference,
    '    barrier(args.ready, args.continue_path)\n    manifest_bytes =',
    '    barrier(args.ready, args.continue_path)\n'
    '    if args.generation == "CURRENT":\n'
    '        generation_id = (state / "CURRENT").read_text(encoding="ascii").strip()\n'
    '        folder = state / "releases" / generation_id\n'
    '    manifest_bytes =')
early_current = replace_once(reference,
    '        if args.crash == "after_generation":\n            os._exit(75)',
    '        if args.crash == "after_generation":\n'
    '            (state / "CURRENT").write_text(generation_id + "\\n", encoding="ascii")\n'
    '            os._exit(75)')
begin = reference.index('def publish(args):')
end = reference.index('\ndef read(args):')
publish = reference[begin:end]
publish = replace_once(publish, 'db.execute("BEGIN IMMEDIATE")', 'db.execute("BEGIN")')
unsafe_publish = reference[:begin] + publish + reference[end:]
variants = [
    ("semantic_not_byte_identity", wrong_identity, "batch_conflict_and_gap"),
    ("commit_before_prepare_crash", early_commit, "crash_before_commit"),
    ("reader_repins_current", late_pin, "reader_pinned"),
    ("advertise_before_checkpoint", early_current, "crash_before_advertise"),
    ("unserialized_old_publisher", unsafe_publish, "generation_idempotent"),
]
records = []
for name, source, expected_failure in variants:
    target = out / name
    target.mkdir()
    answer = target / "author_mutant.zip"
    with zipfile.ZipFile(answer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("app/ledger.py", source.encode("utf-8"))
        archive.writestr("app/curation.py", (task / "environment/app/curation.py").read_bytes())
        archive.writestr("bin/ddi-ledger", (task / "environment/bin/ddi-ledger").read_bytes())
        archive.writestr("answer_notes.md", "Author negative control, not an independent model answer.\n")
    run = subprocess.run([sys.executable, str(private / "evaluate.py"),
                          "--submission", str(answer), "--model", "author-negative-control/" + name,
                          "--skip-build", "--out-dir", str(target / "score")],
                         capture_output=True, text=True, timeout=180)
    result = json.loads((target / "score/result.json").read_text(encoding="utf-8"))
    detected = (run.returncode == 0 and result["status"] == "completed"
                and expected_failure in result["failed_checks"])
    records.append({"name": name, "expected_failed_check": expected_failure,
                    "detected": detected, "reward": result["reward"],
                    "normal_verifier_completion": result["status"] == "completed",
                    "model_difficulty_evidence": False,
                    "answer_sha256": hashlib.sha256(answer.read_bytes()).hexdigest()})
    print(json.dumps(records[-1]), flush=True)
    (out / "results.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
assert all(record["detected"] for record in records), "A core counterexample was not detected"
