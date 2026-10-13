"""Operator-only evaluator for one frozen durable DDI ledger task."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import time
import zipfile


ROOT = Path(__file__).resolve().parent


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_bundle() -> dict:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for name, wanted in manifest["files"].items():
        path = ROOT / name
        assert path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == wanted, name
    return manifest


def read_answer(path: Path) -> dict[str, bytes]:
    assert path.stat().st_size <= 24_000_000, "oversized answer ZIP"
    bodies: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            assert name not in bodies and not item.is_dir() and not item.flag_bits & 1
            assert not stat.S_ISLNK(item.external_attr >> 16)
            assert item.file_size <= 5_000_000
            safe = (all(part not in (".", "..") for part in parts)
                    and PurePosixPath(name).as_posix() == name
                    and "\\" not in name and ":" not in name)
            allowed = (
                name == "answer_notes.md"
                or name == "bin/ddi-ledger"
                or (len(parts) >= 2 and parts[0] == "app"
                    and PurePosixPath(name).suffix == ".py")
            )
            assert safe and allowed, name
            bodies[name] = archive.read(item)
    assert {"app/ledger.py", "app/curation.py", "bin/ddi-ledger"} <= bodies.keys()
    assert sum(len(body) for body in bodies.values()) <= 22_000_000
    return bodies


def verified_score(folder: Path, manifest: dict) -> tuple[float, dict]:
    details = json.loads((folder / "details.json").read_text(encoding="utf-8"))
    reward = float((folder / "reward.txt").read_text(encoding="ascii"))
    assert details["verifier_completed"] is True and math.isfinite(reward)
    assert 0 <= reward <= 1 and len(details["checks"]) == len(manifest["checks"])
    for result, expected in zip(details["checks"], manifest["checks"]):
        assert result["name"] == expected["name"]
        assert result["weight"] == expected["weight"]
        assert type(result["passed"]) is bool
    calculated = round(sum(item["weight"] for item in details["checks"] if item["passed"]), 6)
    assert reward == details["reward"] == calculated
    return reward, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("candidate", "oracle", "nop"), default="candidate")
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--answer-status", choices=("completed", "timeout", "error"), default="completed")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    assert (args.mode == "candidate") == (args.submission is not None)
    out = args.out_dir.resolve()
    assert not out.exists(), "Preserve prior evidence; choose a new output path"
    out.mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    started = time.monotonic()
    index = 0
    container_id = None
    report = {"mode": args.mode, "model": args.model,
              "answer_status": args.answer_status, "status": "infrastructure_error",
              "reward": None, "formal_platform_t1": False,
              "eligible_for_difficulty_analysis": False}

    def docker(*argv: str, timeout: int = 60) -> bytes:
        nonlocal index
        index += 1
        log = logs / f"{index:02d}_{argv[0]}.log"
        command = ["docker", "--context", "desktop-linux", *map(str, argv)]
        with log.open("wb") as stream:
            stream.write((json.dumps(command) + "\n").encode("utf-8"))
            stream.flush()
            result = subprocess.run(command, capture_output=True, timeout=timeout)
            stream.write(result.stdout + result.stderr)
        assert result.returncode == 0, f"Docker {argv[0]} failed; see {log.name}"
        return result.stdout

    try:
        manifest = verify_bundle()
        task = ROOT / "task"
        for key in ("task_commit", "task_digest", "agent_budget_sec", "verifier_budget_sec"):
            report[key] = manifest[key]
        report["manifest_sha256"] = sha((ROOT / "manifest.json").read_bytes())
        payloads: dict[str, bytes] = {}
        if args.mode == "candidate":
            payloads = read_answer(args.submission)
            raw = args.submission.read_bytes()
            (out / "answer.zip").write_bytes(raw)
            report["answer_sha256"] = sha(raw)
            report["installed_files"] = {
                name: sha(body) for name, body in payloads.items() if name != "answer_notes.md"
            }
        elif args.mode == "oracle":
            payloads = {
                "app/ledger.py": (task / "solution/reference_ledger.py").read_bytes(),
            }
        assert docker("info", "--format", "{{.OSType}}", timeout=20).strip() == b"linux"
        image = "ddi-ledger-eval:task-" + manifest["task_digest"][:16]
        label = "ddi.ledger.task=" + manifest["task_digest"]
        if not args.skip_build:
            docker("build", "--label", label, "-t", image, task / "environment", timeout=900)
        image_info = json.loads(docker("image", "inspect", image))[0]
        assert (image_info["Config"].get("Labels") or {}).get("ddi.ledger.task") == manifest["task_digest"]
        report["image_id"] = image_info["Id"]
        container_id = docker(
            "create", "--network", "none", "--cpus", "2", "--memory", "4g",
            "--memory-swap", "4g", "--pids-limit", "512",
            "--security-opt", "no-new-privileges:true", "--label", label,
            image_info["Id"], "bash", "-lc",
            "chmod 0755 /usr/local/bin/ddi-ledger; bash /tests/test.sh",
        ).decode().strip()
        assert len(container_id) == 64 and all(char in "0123456789abcdef" for char in container_id)
        report["container_id"] = container_id
        docker("cp", task / "tests", container_id + ":/tests")
        with tempfile.TemporaryDirectory(prefix="ddi-ledger-answer-") as folder:
            source = Path(folder)
            for name, body in payloads.items():
                if name == "answer_notes.md":
                    continue
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            if payloads:
                for local, remote in (
                    ("app", "/opt/ddi-ledger"),
                    ("bin", "/usr/local/bin"),
                ):
                    folder_path = source / local
                    if folder_path.exists():
                        docker("cp", str(folder_path) + "/.", container_id + ":" + remote)
        docker("start", "--attach", container_id, timeout=manifest["verifier_budget_sec"])
        state = json.loads(docker("inspect", container_id))[0]["State"]
        report["container_state"] = state
        assert state["Status"] == "exited" and not state["OOMKilled"]
        assert state["ExitCode"] == 0 and not state["Error"], "Verifier did not finish normally"
        verifier = out / "verifier"
        docker("cp", container_id + ":/logs/verifier/.", verifier)
        reward, details = verified_score(verifier, manifest)
        eligible = args.mode == "candidate" and args.answer_status == "completed"
        report.update({"status": "completed", "reward": reward,
                       "eligible_for_difficulty_analysis": eligible,
                       "local_threshold_met": reward <= 0.7 if eligible else None,
                       "failed_checks": [item["name"] for item in details["checks"] if not item["passed"]],
                       "verifier_completed": True})
        if args.mode != "candidate":
            report["control_expected"] = 1.0 if args.mode == "oracle" else 0.0
            report["control_passed"] = reward == report["control_expected"]
    except subprocess.TimeoutExpired as exc:
        report.update({"status": "timeout", "error": f"operation exceeded {exc.timeout} seconds"})
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if container_id:
            report["retained_container_id"] = container_id
            try:
                report["retained_container_state"] = json.loads(docker("inspect", container_id))[0]["State"]
            except Exception as exc:
                report["retention_warning"] = str(exc)
        report["elapsed_sec"] = round(time.monotonic() - started, 3)
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0 if report["status"] == "completed" and report.get("control_passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
