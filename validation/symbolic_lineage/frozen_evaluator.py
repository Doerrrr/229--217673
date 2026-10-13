"""Grade a frozen first answer in a fresh isolated Linux container.

The package is for external local trials, not a claimed platform Oracle run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import time
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unpack_answer(source, target):
    with zipfile.ZipFile(source) as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
        assert 1 <= len(entries) <= 128 and sum(info.file_size for info in entries) <= 16 * 1024 * 1024
        seen = set()
        for info in entries:
            name = PurePosixPath(info.filename)
            assert not name.is_absolute() and ".." not in name.parts and "\\" not in info.filename
            assert info.filename not in seen and not stat.S_ISLNK(info.external_attr >> 16)
            seen.add(info.filename)
            assert (name.parts[0] == "app" and name.suffix == ".py") or info.filename == "answer_notes.md"
            destination = target.joinpath(*name.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
        assert "app/lineage.py" in seen and "answer_notes.md" in seen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answer", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--docker-context")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        assert sha(root / name) == expected, "Frozen evaluator changed: " + name
    assert not args.out.exists(), "Preserve prior scores; choose a new output folder"
    args.out.mkdir(parents=True)
    answer_copy = args.out / "answer.zip"
    shutil.copyfile(args.answer, answer_copy)
    assert sha(answer_copy) == sha(args.answer)
    unpacked = args.out / "answer_sources"
    unpack_answer(answer_copy, unpacked)
    docker = ["docker"] + (["--context", args.docker_context] if args.docker_context else [])
    def run(parts, timeout=900, capture=False):
        return subprocess.run(docker + parts, check=True, timeout=timeout,
                              text=True, capture_output=capture)
    image = "ddi-symbolic-external:" + manifest["task_digest"][:12]
    print("Building frozen public environment...", flush=True)
    run(["build", "-t", image, str(root / "task/environment")])
    container = run(["create", "--network", "none", "--cpus", "2", "--memory", "4g",
                     "--pids-limit", "128", "--security-opt", "no-new-privileges", image,
                     "bash", "/tests/test.sh"], capture=True).stdout.strip()
    (args.out / "container_id.txt").write_text(container + "\n", encoding="ascii")
    run(["cp", str(root / "task/tests") + "/.", container + ":/tests"])
    run(["cp", str(unpacked / "app") + "/.", container + ":/app"])
    print("Running frozen verifier; no model is called...", flush=True)
    started = time.monotonic()
    run(["start", container], capture=True)
    exception = None
    try:
        run(["wait", container], timeout=3700, capture=True)
    except Exception as error:
        exception = type(error).__name__ + ": " + str(error)
        subprocess.run(docker + ["kill", container], timeout=15, capture_output=True)
    state = json.loads(run(["inspect", container], capture=True).stdout)[0]["State"]
    logs = run(["logs", container], capture=True)
    (args.out / "container_stdout.txt").write_text(logs.stdout, encoding="utf-8")
    (args.out / "container_stderr.txt").write_text(logs.stderr, encoding="utf-8")
    copy = subprocess.run(docker + ["cp", container + ":/logs/verifier", str(args.out / "verifier")],
                          text=True, capture_output=True, timeout=60)
    details_path = args.out / "verifier/details.json"
    normal = (exception is None and state["ExitCode"] == 0 and not state["OOMKilled"]
              and copy.returncode == 0 and details_path.is_file())
    details = json.loads(details_path.read_text(encoding="utf-8")) if normal else None
    result = {"status": "completed" if normal else "infrastructure_error",
              "task_id": "DDI-008", "version": "v01", "task_commit": manifest["task_commit"],
              "task_digest": manifest["task_digest"], "answer_sha256": sha(answer_copy),
              "reward": details["reward"] if normal else None,
              "passed_checks": details["passed_checks"] if normal else None,
              "total_checks": 20, "container_state": state, "exception": exception,
              "grading_elapsed_sec": round(time.monotonic() - started, 3),
              "formal_platform_t1": False, "model_called": False,
              "freshness_and_coding_time": "must be established by first-answer metadata, not grader"}
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    if not normal:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
