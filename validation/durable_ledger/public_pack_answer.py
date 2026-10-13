"""Freeze only the repaired ledger application, launcher and answer metadata."""
from __future__ import annotations
import argparse
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True, type=Path)
args = parser.parse_args()
files = {"app/" + p.relative_to(ROOT / "environment/app").as_posix(): p
         for p in sorted((ROOT / "environment/app").rglob("*.py"))
         if "__pycache__" not in p.parts}
files["bin/ddi-ledger"] = ROOT / "environment/bin/ddi-ledger"
files["answer_notes.md"] = ROOT / "answer_notes.md"
assert "app/ledger.py" in files and "app/curation.py" in files
assert args.out.resolve() not in [p.resolve() for p in files.values()]
with args.out.open("xb") as stream, zipfile.ZipFile(stream, "w") as archive:
    for name, path in files.items():
        assert path.is_file() and not path.is_symlink(), path
        info = zipfile.ZipInfo(name, (2026, 10, 13, 0, 0, 0))
        info.create_system = 3
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | (0o755 if name.startswith("bin/") else 0o644)) << 16
        archive.writestr(info, path.read_bytes())
print(args.out.resolve())
