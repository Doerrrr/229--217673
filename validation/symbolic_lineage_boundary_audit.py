"""Audit frozen packet boundaries and the answer packer without model calls."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import warnings
import zipfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--frozen", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    assert not args.out.exists()
    args.out.mkdir(parents=True)
    checksums = json.loads((args.frozen / "checksums.json").read_text(encoding="utf-8"))
    for role, folder_name in (("candidate", "DDI-008_v01_candidate"), ("private", "DDI-008_v01_evaluator_private")):
        archive_path = args.frozen / checksums[role]["file"]
        assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == checksums[role]["sha256"]
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            for info in archive.infolist():
                name = Path(info.filename)
                assert name.parts[0] == folder_name and ".." not in name.parts
                if role == "candidate":
                    assert not any(part in {"solution", "tests", ".git", "__pycache__", "answer.zip"} for part in name.parts)
                assert (args.frozen / name).read_bytes() == archive.read(info)
        folder = args.frozen / folder_name
        manifest = json.loads((folder / ("public_manifest.json" if role == "candidate" else "manifest.json")).read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    smoke = args.out / "packer_smoke"
    shutil.copytree(args.frozen / "DDI-008_v01_candidate", smoke)
    answer = smoke / "answer.zip"
    subprocess.run([sys.executable, str(smoke / "pack_answer.py"), "--out", str(answer)], check=True)
    evaluator_path = args.frozen / "DDI-008_v01_evaluator_private/evaluate.py"
    spec = importlib.util.spec_from_file_location("frozen_lineage_evaluator", evaluator_path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    evaluator.unpack_answer(answer, args.out / "accepted_answer")
    rejected = []
    for kind in ("traversal", "symlink", "unexpected_file", "duplicate_path"):
        path = args.out / (kind + ".zip")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("app/lineage.py", "pass\n")
                archive.writestr("answer_notes.md", "boundary control\n")
                name = {"traversal": "app/../../outside.py", "unexpected_file": "tests/test_outputs.py",
                        "duplicate_path": "app/lineage.py", "symlink": "app/link.py"}[kind]
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = ((stat.S_IFLNK if kind == "symlink" else stat.S_IFREG) | 0o644) << 16
                archive.writestr(info, "/tests/test_outputs.py")
        try:
            evaluator.unpack_answer(path, args.out / (kind + "_extract"))
        except AssertionError:
            rejected.append(kind)
        else:
            raise AssertionError("Unsafe answer accepted: " + kind)
    result = {"status": "PASS", "task_digest": checksums["task_digest"],
              "public_and_private_hashes": "PASS", "public_hidden_boundary": "PASS",
              "public_packer_smoke": "PASS", "unsafe_answer_rejections": rejected,
              "model_calls": 0, "candidate_task_execution": False}
    (args.out / "boundary_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
