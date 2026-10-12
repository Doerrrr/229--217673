"""Candidate-side packer: submit only repairable source files and notes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
if args.out.exists():
    raise SystemExit("Preserve your first answer; choose a new output path")
members: dict[str, bytes] = {}
for source_dir, prefix, suffixes in (
    ("environment/app", "curator", {".py"}),
    ("environment/bridge/src", "bridge/src", {".cpp", ".h", ".hpp"}),
    ("environment/release", "release", {".py"}),
):
    root = ROOT / source_dir
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink() or path.suffix not in suffixes or path.stat().st_size > 5_000_000:
            raise SystemExit(f"Unsupported submitted source: {path}")
        members[prefix + "/" + path.relative_to(root).as_posix()] = path.read_bytes()
for name in ("ddi-curate", "ddi-release-audit"):
    path = ROOT / "environment/bin" / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5_000_000:
        raise SystemExit(f"Missing or oversized launcher: {name}")
    members["bin/" + name] = path.read_bytes()
notes = ROOT / "answer_notes.md"
if notes.is_file():
    members["answer_notes.md"] = notes.read_bytes()
if not {"curator/curate.py", "bridge/src/bridge_index.cpp", "release/release.py"} <= members.keys():
    raise SystemExit("Missing core source")
if sum(map(len, members.values())) > 22_000_000:
    raise SystemExit("Answer too large")
args.out.parent.mkdir(parents=True, exist_ok=True)
with args.out.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
    for name, body in sorted(members.items()):
        info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | (0o755 if name.startswith("bin/") else 0o644)) << 16
        archive.writestr(info, body)
print(json.dumps({"answer": str(args.out),
                  "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
                  "files": {name: hashlib.sha256(body).hexdigest()
                            for name, body in members.items()}}, indent=2))
