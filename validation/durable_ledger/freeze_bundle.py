"""Freeze one ledger task; keep public and operator-only files separate."""
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
TASK = ROOT / "runtime_task_v0"
parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
out = args.out.resolve()
assert not out.exists(), "Choose a new folder; preserve old evidence"
subprocess.run(["python", str(ROOT / "preflight.py")], check=True, capture_output=True)
assert not subprocess.check_output(["git", "status", "--porcelain", "--", ".gitattributes",
                                    "validation/durable_ledger"], cwd=REPO), "Commit first"
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
sha = lambda data: hashlib.sha256(data).hexdigest()
paths = [p for p in sorted(TASK.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
files = {p.relative_to(TASK).as_posix(): sha(p.read_bytes()) for p in paths}
for path in paths:
    name = path.relative_to(TASK).as_posix()
    committed = subprocess.check_output(["git", "show", "HEAD:validation/durable_ledger/runtime_task_v0/" + name], cwd=REPO)
    assert committed == path.read_bytes(), "Working bytes differ: " + name
digest = sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
public = out / "ddi_candidate"
private = out / "ddi_evaluator_private"
public.mkdir(parents=True)
private.mkdir(parents=True)
ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
shutil.copytree(TASK / "environment", public / "environment", ignore=ignore)
shutil.copyfile(TASK / "instruction.md", public / "instruction.md")
shutil.copyfile(ROOT / "public_pack_answer.py", public / "pack_answer.py")
(public / "answer_notes.md").write_text(
    "# First answer metadata\n\n- Model/version displayed: unknown\n"
    "- Start UTC / freeze UTC:\n- Environment-only waits:\n"
    "- Completed / timeout / error:\n- Builds and own tests actually run:\n"
    "- Known omissions:\n- No hidden solution/tests or old answers accessed:\n",
    encoding="utf-8", newline="\n")
(public / "start_here.md").write_text(
    "# Durable DDI evidence ledger\n\nRead instruction.md completely. Repair only the public\n"
    "application and launcher in environment/app and environment/bin. The supplied\n"
    "curation helper is public and may be used unchanged. No hidden solution, tests,\n"
    "repository history or prior answer is included. Do not inspect unrelated folders.\n\n"
    f"Frozen author commit: {commit}\nTask digest: {digest}\n"
    "Coding budget: 3600 seconds, excluding recorded environment-only waits.\n"
    "Do not change the data or Docker dependencies. Use Docker Desktop if available;\n"
    "do not repair host services. Freeze a single first answer without grader feedback.\n"
    "Finish answer_notes.md, run `python pack_answer.py --out answer.zip`, and return\n"
    "that immutable ZIP path. State any environment failure honestly.\n",
    encoding="utf-8", newline="\n")
public_files = {p.relative_to(public).as_posix(): sha(p.read_bytes())
                for p in sorted(public.rglob("*")) if p.is_file()}
(public / "public_manifest.json").write_text(json.dumps({
    "task_commit": commit, "task_digest": digest, "agent_budget_sec": 3600,
    "files": public_files}, indent=2) + "\n", encoding="utf-8", newline="\n")
shutil.copytree(TASK, private / "task", ignore=ignore)
shutil.copyfile(ROOT / "frozen_evaluator.py", private / "evaluate.py")
module = ast.parse((TASK / "tests/test_outputs.py").read_text(encoding="utf-8"))
names = next(ast.literal_eval(n.value) for n in module.body
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NAMES" for t in n.targets))
private_files = {p.relative_to(private).as_posix(): sha(p.read_bytes())
                 for p in sorted(private.rglob("*")) if p.is_file()}
(private / "manifest.json").write_text(json.dumps({
    "task_commit": commit, "task_digest": digest, "agent_budget_sec": 3600,
    "verifier_budget_sec": 900, "checks": [{"name": name, "weight": .05} for name in names],
    "files": private_files}, indent=2) + "\n", encoding="utf-8", newline="\n")
def package(folder, target):
    with target.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                assert not path.is_symlink()
                name = folder.name + "/" + path.relative_to(folder).as_posix()
                info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | (0o755 if path.suffix == ".sh" else 0o644)) << 16
                archive.writestr(info, path.read_bytes())
package(public, out / "ddi_candidate.zip")
package(private, out / "ddi_evaluator_private.zip")
(out / "checksums.json").write_text(json.dumps({
    "task_commit": commit, "task_digest": digest, "checks": len(names),
    "candidate_zip_sha256": sha((out / "ddi_candidate.zip").read_bytes()),
    "private_zip_sha256": sha((out / "ddi_evaluator_private.zip").read_bytes())}, indent=2)
    + "\n", encoding="utf-8", newline="\n")
print((out / "checksums.json").read_text())
