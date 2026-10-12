"""Copy an author draft into a clean, never-overwritten Harbor task folder."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--target", required=True)
args = parser.parse_args()
if not args.source.startswith("runtime_task_") or not args.target.startswith("runtime_task_"):
    raise SystemExit("Use owned runtime_task_* folder names")
if any(char in args.source + args.target for char in "/\\:."):
    raise SystemExit("Nested paths and dotted names are not allowed")
source = ROOT / args.source
target = ROOT / args.target
if not source.is_dir() or target.exists():
    raise SystemExit("Source must exist and target must be new")
shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                symlinks=False)
print(target)
