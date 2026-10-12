"""Freeze candidate-only and operator-only copies of a prevalidated task."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--task-name", required=True)
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
task = ROOT / args.task_name
out = args.out.resolve()
if out.exists() or args.task_name != "runtime_task_r2":
    raise SystemExit("Use a new frozen output folder and an owned task folder")


def git(*argv: str) -> bytes:
    return subprocess.check_output(["git", *argv], cwd=REPO)


commit = git("rev-parse", "HEAD").decode().strip()
if git("status", "--porcelain", "--", ".gitattributes",
       "validation/joint_release/runtime_task_r2",
       "validation/joint_release/freeze_bundle.py",
       "validation/joint_release/frozen_evaluator.py",
       "validation/joint_release/public_pack_answer.py"):
    raise SystemExit("Commit author source before freezing")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


files = {p.relative_to(task).as_posix(): sha(p.read_bytes())
         for p in sorted(task.rglob("*"))
         if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
if len(files) != 31:
    raise SystemExit("Unexpected generated task files; run preflight first")
if any(files[name] != sha(git("show", "HEAD:validation/joint_release/" +
                             args.task_name + "/" + name)) for name in files):
    raise SystemExit("Frozen task no longer matches committed source")
subprocess.run(["python", str(ROOT / "preflight.py"), "--task-name", args.task_name],
               check=True, capture_output=True)
module = ast.parse((task / "tests/joint_score.py").read_text(encoding="utf-8"))
groups = {}
for node in module.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("CURATOR", "BRIDGE"):
                groups[target.id] = ast.literal_eval(node.value)
integration = ast.parse((task / "tests/test_joint.py").read_text(encoding="utf-8"))
integration_names = []
for node in integration.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "CHECKS" for target in node.targets
    ):
        integration_names = [item.elts[0].value for item in node.value.elts]
weights = (
    [("curator/" + name, round(.40 * value, 6)) for name, value in groups["CURATOR"]]
    + [("bridge/" + name, round(.40 * value, 6)) for name, value in groups["BRIDGE"]]
    + [("release/" + name, .05) for name in integration_names]
)
if len(weights) != 24 or abs(sum(weight for _, weight in weights) - 1.0) > 1e-12:
    raise SystemExit("Invalid frozen weights")
digest = sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
public = out / "ddi_candidate"
private = out / "ddi_evaluator_private"
public.mkdir(parents=True)
private.mkdir(parents=True)
shutil.copytree(task / "environment", public / "environment",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copyfile(task / "instruction.md", public / "instruction.md")
shutil.copyfile(ROOT / "public_pack_answer.py", public / "pack_answer.py")
(public / "answer_notes.md").write_text(
    "# Answer metadata\n\n"
    "- Model and version displayed by your interface: unknown\n"
    "- Start UTC / freeze UTC:\n"
    "- Environment-only waiting time:\n"
    "- Completed / timeout / error:\n"
    "- Own build and tests actually run:\n"
    "- Known omissions or uncertain requirements:\n"
    "- No solution, hidden tests or old answers accessed:\n",
    encoding="utf-8", newline="\n",
)
guide = f"""# Candidate-only joined DDI release audit

Read `instruction.md` fully. Repair the curation application, native bridge
engine, and release publisher within `environment/`. This copy contains no
solution, hidden tests, repository history or prior answers.

Frozen task commit: {commit}
Frozen task digest: {digest}
Coding budget: 3600 seconds (60 minutes), excluding documented environment-only waits.
Freeze a single first answer. Do not read unrelated workspaces or hidden files.

You may use the supplied original CSVs, your own small CSV fixtures, the
public client, and the native graph protocol. Use the installed Docker Desktop
Linux engine or available C++ compiler. Do not repair host WSL/Docker services.
If execution environment is unavailable, record the error and stop instead
of treating it as a low model score.

After finishing the source, complete `answer_notes.md` and run:

    python pack_answer.py --out answer.zip

Return only the frozen answer ZIP path. The operator grades it once against
the frozen hidden standard after your answer is final.
"""
(public / "start_here.md").write_text(guide, encoding="utf-8", newline="\n")
public_hashes = {p.relative_to(public).as_posix(): sha(p.read_bytes())
                 for p in sorted(public.rglob("*")) if p.is_file()}
(public / "public_manifest.json").write_text(json.dumps(
    {"task_commit": commit, "task_digest": digest, "agent_budget_sec": 3600,
     "files": public_hashes}, indent=2) + "\n", encoding="utf-8")
shutil.copytree(task, private / "task",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copyfile(ROOT / "frozen_evaluator.py", private / "evaluate.py")
private_files = {p.relative_to(private).as_posix(): sha(p.read_bytes())
                 for p in sorted(private.rglob("*")) if p.is_file()}
(private / "manifest.json").write_text(json.dumps({
    "task_commit": commit, "task_digest": digest,
    "agent_budget_sec": 3600, "verifier_budget_sec": 900,
    "checks": [{"name": name, "weight": weight} for name, weight in weights],
    "files": private_files,
}, indent=2) + "\n", encoding="utf-8")


def package(folder: Path, target: Path) -> None:
    with target.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            if path.is_symlink():
                raise SystemExit("Symlink not allowed in task archive")
            name = folder.name + "/" + path.relative_to(folder).as_posix()
            info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | (0o755 if path.suffix == ".sh" else 0o644)) << 16
            archive.writestr(info, path.read_bytes())


package(public, out / "ddi_candidate.zip")
package(private, out / "ddi_evaluator_private.zip")
if any(bad in name.lower() for name in public_hashes
       for bad in ("solution", "oracle", "tests/", "reference.cpp", ".git/")):
    raise SystemExit("Hidden content appears in candidate package")
(out / "checksums.json").write_text(json.dumps({
    "task_commit": commit, "task_digest": digest,
    "candidate_zip_sha256": sha((out / "ddi_candidate.zip").read_bytes()),
    "private_zip_sha256": sha((out / "ddi_evaluator_private.zip").read_bytes()),
    "checks": len(weights),
}, indent=2) + "\n", encoding="utf-8")
print((out / "checksums.json").read_text(encoding="utf-8"))
