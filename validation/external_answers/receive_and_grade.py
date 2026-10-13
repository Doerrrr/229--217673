"""Private intake and evidence audit for the frozen DDI-008 external trial.

No model calls, answer editing, reweighting or platform operations are performed.
An operator supplies observed first-answer metadata; the grader cannot prove it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import zipfile

TASK = {
    "task_id": "DDI-008", "version": "v01",
    "task_commit": "2febd68d3b50358952cad3fe19364729697b11a5",
    "task_digest": "368ba809fa38bf798ec248eb801188d60e40b33f83e8e824526e65c350b22a0f",
    "candidate_sha256": "617d9249d3016d5f3c109ff9fbaeb24b64779b00f5d1f089b7e0bf21d9149690",
    "private_sha256": "3732c08ed1a313d903ecc73a20c7538d14add2884075008c73c2c0784ebe0772",
    "agent_budget_sec": 3600,
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def write_new(path, data):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timestamp needs an explicit timezone")
    return parsed


def verify_frozen(folder):
    folder = Path(folder).resolve(strict=True)
    checksums = read_json(folder / "checksums.json")
    for key in ("task_id", "version", "task_commit", "task_digest"):
        require(checksums[key] == TASK[key], "Different frozen task: " + key)
    for role in ("candidate", "private"):
        archive = folder / checksums[role]["file"]
        require(archive.parent == folder, "Unsafe frozen archive path")
        require(sha(archive) == checksums[role]["sha256"] == TASK[role + "_sha256"],
                "Frozen archive hash mismatch: " + role)
    private = folder / "DDI-008_v01_evaluator_private"
    private = private.resolve(strict=True)
    require(private.is_relative_to(folder), "Private evaluator outside frozen folder")
    with zipfile.ZipFile(folder / checksums["private"]["file"]) as archive:
        frozen_manifest = archive.read("DDI-008_v01_evaluator_private/manifest.json")
    require((private / "manifest.json").read_bytes() == frozen_manifest,
            "Unpacked evaluator manifest differs from frozen ZIP")
    manifest = read_json(private / "manifest.json")
    for key in ("task_id", "version", "task_commit", "task_digest", "agent_budget_sec"):
        require(manifest[key] == TASK[key], "Different evaluator: " + key)
    for name, expected in manifest["files"].items():
        file = (private / name).resolve(strict=True)
        require(file.is_relative_to(private) and sha(file) == expected,
                "Frozen evaluator changed: " + name)
    require(len(manifest["checks"]) == 20, "Different check count")
    require(sum(Decimal(str(c["weight"])) for c in manifest["checks"]) == Decimal(1),
            "Different weight total")
    return private, manifest


def validate_answer(path):
    require(Path(path).is_file() and not Path(path).is_symlink(), "Answer must be a regular ZIP")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(1 <= len(entries) <= 128, "Unexpected answer entry count")
        require(sum(e.file_size for e in entries) <= 16 * 1024 * 1024, "Answer too large")
        seen = set()
        for entry in entries:
            name = PurePosixPath(entry.filename)
            require(entry.orig_filename == entry.filename, "Noncanonical raw ZIP path")
            require(not name.is_absolute() and ".." not in name.parts and
                    "\\" not in entry.filename and ":" not in entry.filename,
                    "Unsafe answer path")
            require(entry.filename not in seen and not stat.S_ISLNK(entry.external_attr >> 16),
                    "Duplicate or symlink answer entry")
            require(not entry.is_dir() and ((len(name.parts) > 1 and name.parts[0] == "app"
                    and name.suffix == ".py") or entry.filename == "answer_notes.md"),
                    "Unexpected answer file: " + entry.filename)
            seen.add(entry.filename)
        require({"app/lineage.py", "answer_notes.md"} <= seen, "Missing source or notes")
        require(archive.testzip() is None, "Corrupt answer ZIP")
    return sorted(seen)


def metadata_reasons(metadata):
    """Unknown facts remain unverified, not silently assumed eligible."""
    reasons = []
    for key, expected in (("origin", "external_agent"), ("first_answer", True),
                          ("independent_session", True), ("feedback_before_freeze", False),
                          ("completion_status", "completed")):
        value = metadata.get(key)
        if value != expected or (isinstance(expected, bool) and type(value) is not bool):
            reasons.append(key + " is unverified or ineligible")
    for key in ("session_id", "model", "evidence_note"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            reasons.append(key + " is missing")
    coding = None
    try:
        wall = (timestamp(metadata["frozen_at"]) - timestamp(metadata["started_at"])).total_seconds()
        waits = metadata["environment_waits"]
        require(isinstance(waits, list), "Wait intervals must be a list")
        intervals = []
        for wait in waits:
            start, end = timestamp(wait["started_at"]), timestamp(wait["ended_at"])
            require(timestamp(metadata["started_at"]) <= start <= end <= timestamp(metadata["frozen_at"]),
                    "Wait interval outside coding session")
            require(isinstance(wait.get("reason"), str) and wait["reason"].strip(), "Wait needs evidence")
            intervals.append((start, end))
        intervals.sort()
        require(all(intervals[i - 1][1] <= intervals[i][0] for i in range(1, len(intervals))),
                "Overlapping wait intervals")
        coding = wall - sum((end - start).total_seconds() for start, end in intervals)
        require(0 <= coding <= TASK["agent_budget_sec"], "Outside declared coding budget")
    except (KeyError, TypeError, ValueError) as error:
        reasons.append("coding time unverified/ineligible: " + str(error))
    return reasons, coding


def receive(args):
    verify_frozen(args.frozen)
    names = validate_answer(args.answer)
    metadata = read_json(args.metadata)
    require(isinstance(metadata, dict), "Metadata must be a JSON object")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.record_id) is not None,
            "Use an ASCII record ID without path separators")
    args.root.mkdir(parents=True, exist_ok=True)
    target = args.root / args.record_id
    target.mkdir(exist_ok=False)
    original_hash = sha(args.answer)
    shutil.copyfile(args.answer, target / "answer.zip")
    require(sha(target / "answer.zip") == original_hash, "Answer changed during intake")
    reasons, coding = metadata_reasons(metadata)
    record = {**TASK, "record_id": args.record_id, "answer_sha256": original_hash,
              "answer_entries": names, "metadata": metadata,
              "received_at": datetime.now(timezone.utc).isoformat(),
              "coding_elapsed_sec": coding, "qualification_reasons": reasons,
              "model_called": False, "formal_platform_t1": False}
    write_new(target / "record.json", record)
    print(json.dumps({"record": str(target), "answer_sha256": original_hash,
                      "qualification_reasons": reasons}, ensure_ascii=False))


def load_record(folder):
    record = read_json(folder / "record.json")
    for key, expected in TASK.items():
        require(record.get(key) == expected, "Record uses a different task: " + key)
    require(sha(folder / "answer.zip") == record["answer_sha256"], "Stored answer changed")
    validate_answer(folder / "answer.zip")
    return record


def summarize_result(result, details, record, manifest):
    """Validate all fixed checks; don't accept a bare reward or failed runtime."""
    for key in ("task_id", "version", "task_commit", "task_digest", "answer_sha256"):
        require(result.get(key) == record[key], "Result does not belong to this answer: " + key)
    if result.get("status") != "completed":
        require(result.get("reward") is None, "Infrastructure failure must not have a score")
        return {"status": "infrastructure_error", "reward": None}
    state = result.get("container_state", {})
    require(state.get("ExitCode") == 0 and state.get("OOMKilled") is False
            and state.get("Running") is False and result.get("exception") is None,
            "Abnormal container cannot supply a valid score")
    require(details.get("status") == "completed" and details.get("reference_solution_imported") is False,
            "Incomplete or different grading details")
    expected = {c["name"]: Decimal(str(c["weight"])) for c in manifest["checks"]}
    require(len(expected) == len(details.get("checks", [])) == 20, "Missing or duplicate check")
    seen, total, passed = set(), Decimal(0), 0
    for check in details["checks"]:
        name = check["name"]
        require(name in expected and name not in seen and type(check["passed"]) is bool,
                "Unexpected, duplicate or nonboolean check")
        require(Decimal(str(check["weight"])) == expected[name], "Changed check weight")
        seen.add(name)
        if check["passed"]:
            total += expected[name]
            passed += 1
    require(total == Decimal(str(result["reward"])) == Decimal(str(details["reward"]))
            and passed == result["passed_checks"] == details["passed_checks"]
            and details["total_checks"] == result["total_checks"] == 20, "Inconsistent reward")
    require(details["confinement"] == {"answer_uid": 10001, "hidden_tests_readable": False,
                                     "reward_file_readable": False}, "Unisolated grader")
    return {"status": "completed", "reward": float(total), "passed_checks": passed,
            "failed_checks": [c["name"] for c in details["checks"] if not c["passed"]]}


def grade(args):
    private, manifest = verify_frozen(args.frozen)
    record = load_record(args.record)
    require(not (args.record / "grade_receipt.json").exists(), "Already graded; preserve first result")
    output = args.record / "grade"
    require(not output.exists(), "An earlier grading attempt exists; inspect it before any retry")
    command = [sys.executable, str(private / "evaluate.py"), "--answer",
               str(args.record / "answer.zip"), "--out", str(output)]
    if args.docker_context:
        command += ["--docker-context", args.docker_context]
    started = datetime.now(timezone.utc).isoformat()
    with (args.record / "grade_stdout.txt").open("x", encoding="utf-8") as stdout, \
         (args.record / "grade_stderr.txt").open("x", encoding="utf-8") as stderr:
        process = subprocess.run(command, stdout=stdout, stderr=stderr, text=True, check=False)
    result_path, details_path = output / "result.json", output / "verifier/details.json"
    evidence = {}
    try:
        require(result_path.is_file(), "No grader result; read stderr before a controlled retry")
        result = read_json(result_path)
        details = read_json(details_path) if result.get("status") == "completed" else {}
        summary = summarize_result(result, details, record, manifest)
        require((summary["status"] == "completed" and process.returncode == 0)
                or (summary["status"] != "completed" and process.returncode != 0), "Unexpected grader exit")
        evidence = {str(path.relative_to(args.record)): sha(path)
                    for path in (result_path, details_path) if path.is_file()}
    except (KeyError, TypeError, ValueError) as error:
        summary = {"status": "infrastructure_error", "reward": None, "error": str(error)}
    receipt = {**summary, "started_at": started,
               "finished_at": datetime.now(timezone.utc).isoformat(),
               "record_sha256": sha(args.record / "record.json"),
               "evidence_sha256": evidence, "grader_exit_code": process.returncode,
               "model_called": False, "formal_platform_t1": False}
    write_new(args.record / "grade_receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def audit(args):
    _, manifest = verify_frozen(args.frozen)
    rows, seen_hashes, seen_sessions = [], set(), set()
    for folder in args.records:
        record = load_record(folder)
        reasons, coding = metadata_reasons(record["metadata"])
        receipt = read_json(folder / "grade_receipt.json")
        require(receipt["record_sha256"] == sha(folder / "record.json"), "Record changed after grading")
        for name, expected in receipt["evidence_sha256"].items():
            path = (folder / name).resolve(strict=True)
            require(path.is_relative_to(folder.resolve()) and sha(path) == expected, "Grading evidence changed")
        if receipt["status"] == "completed":
            result = summarize_result(read_json(folder / "grade/result.json"),
                                      read_json(folder / "grade/verifier/details.json"), record, manifest)
            require(receipt["reward"] == result["reward"], "Receipt reward differs")
        else:
            result = {"status": "infrastructure_error", "reward": None}
            reasons.append("grading did not finish normally")
        session = record["metadata"].get("session_id")
        if not isinstance(session, str):
            session = None
        if record["answer_sha256"] in seen_hashes or session in seen_sessions:
            reasons.append("duplicate answer hash or session; independence needs review")
        seen_hashes.add(record["answer_sha256"])
        seen_sessions.add(session)
        rows.append({"record_id": record["record_id"], "answer_sha256": record["answer_sha256"],
                     "coding_elapsed_sec": coding, **result,
                     "qualified": not reasons, "qualification_reasons": reasons})
    # Do not cherry-pick two low scores from a longer retry sequence.
    enough = len(rows) == 2
    if enough:
        latest_freeze = max(timestamp(load_record(p)["metadata"]["frozen_at"])
                            for p in args.records) if all(r["qualified"] for r in rows) else None
        if latest_freeze is not None:
            for folder, row in zip(args.records, rows):
                if timestamp(read_json(folder / "grade_receipt.json")["started_at"]) < latest_freeze:
                    row["qualified"] = False
                    row["qualification_reasons"].append("both answers were not frozen before grading")
    qualified = enough and all(r["qualified"] for r in rows)
    passed = qualified and all(Decimal(str(r["reward"])) <= Decimal("0.700") for r in rows)
    result = {**TASK, "local_difficulty_standard": "two independent first answers, each <= 0.700",
              "status": "LOCAL_STANDARD_MET" if passed else
                        "SCORES_ABOVE_TARGET" if qualified else "INSUFFICIENT_QUALIFIED_EVIDENCE",
              "rows": rows, "goal_complete": passed, "formal_platform_t1": False,
              "full_platform_submission_ready": False, "model_called": False}
    write_new(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    receive_parser = sub.add_parser("receive")
    receive_parser.add_argument("--frozen", type=Path, required=True)
    receive_parser.add_argument("--root", type=Path, required=True)
    receive_parser.add_argument("--record-id", required=True)
    receive_parser.add_argument("--answer", type=Path, required=True)
    receive_parser.add_argument("--metadata", type=Path, required=True)
    receive_parser.set_defaults(handler=receive)
    grade_parser = sub.add_parser("grade")
    grade_parser.add_argument("--frozen", type=Path, required=True)
    grade_parser.add_argument("--record", type=Path, required=True)
    grade_parser.add_argument("--docker-context")
    grade_parser.set_defaults(handler=grade)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--frozen", type=Path, required=True)
    audit_parser.add_argument("--records", type=Path, nargs="+", required=True)
    audit_parser.add_argument("--out", type=Path, required=True)
    audit_parser.set_defaults(handler=audit)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
