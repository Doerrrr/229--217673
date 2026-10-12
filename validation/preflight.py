"""Author-only package boundaries and protected Git asset validation."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "f99fd220e3d5a6665547a1419e8a975c37e45c17"
PROTECTED = ("environment/data/drug_list.csv", "environment/data/DDI_event.csv",
             "environment/data/newddi.csv", ".github/workflows/harbor-validation.yml")
copied = [ROOT / name for name in ("environment/app/curate.py", "environment/app/publication.py",
                                   "environment/bin/ddi-curate")]
copied += list((ROOT / "environment/data").glob("*.csv"))
hidden = [path for folder in ("solution", "tests") for path in (ROOT / folder).rglob("*")
          if path.is_file() and "__pycache__" not in path.parts]
duplicates = [(str(left.relative_to(ROOT)), str(right.relative_to(ROOT)))
              for left in copied for right in hidden if left.read_bytes() == right.read_bytes()]
if duplicates:
    raise SystemExit(f"candidate-hidden exact duplicates: {duplicates}")
for name in PROTECTED:
    revision = "HEAD" if name.startswith(".github/") else BASELINE
    tracked = subprocess.check_output(["git", "ls-tree", "--name-only", revision, "--", name], cwd=ROOT).strip()
    if not tracked:
        if (ROOT / name).exists():
            raise SystemExit(f"unexpected workflow introduced: {name}")
        continue  # A platform repo may have no workflow; preserve that absence.
    committed = subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=ROOT)
    working = (ROOT / name).read_bytes()
    # Git's text checkout may be CRLF on Windows; no other normalization is allowed.
    if working.replace(b"\r\n", b"\n") != committed.replace(b"\r\n", b"\n"):
        raise SystemExit(f"protected content changed: {name}")
for folder in ("environment/app", "solution", "tests", "validation"):
    for path in (ROOT / folder).glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
for path in (ROOT / "tests").glob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and (node.module.startswith("oracle") or node.module.startswith("solution")):
            raise SystemExit(f"verifier imports reference: {path.name}")
        if isinstance(node, ast.Import) and any(alias.name.startswith(("oracle", "solution")) for alias in node.names):
            raise SystemExit(f"verifier imports reference: {path.name}")
print(json.dumps({"protected_files": len(PROTECTED), "candidate_copied_files": len(copied),
                  "exact_duplicates": len(duplicates), "python_syntax": "PASS",
                  "verifier_reference_imports": 0, "status": "PASS"}))
