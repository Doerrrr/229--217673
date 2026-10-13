#!/usr/bin/env python3
"""DDI publication ledger. The persistence/recovery path needs repair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def state_file(folder: Path) -> Path:
    return folder / "ledger.json"


def load(folder: Path) -> dict:
    return json.loads(state_file(folder).read_text(encoding="utf-8"))


def save(folder: Path, value: dict) -> None:
    # Known weakness: this writes the only copy of the ledger in place.
    state_file(folder).write_text(json.dumps(value), encoding="utf-8")


def bootstrap(args):
    folder = Path(args.state_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if state_file(folder).exists():
        return
    paths = {"drugs": Path(args.drugs), "events": Path(args.events),
             "interactions": Path(args.interactions)}
    base = {name: path.read_bytes().decode("utf-8") for name, path in paths.items()}
    save(folder, {"base": base, "batches": []})


def apply(args):
    folder = Path(args.state_dir)
    state = load(folder)
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    state["batches"].append(batch)
    save(folder, state)


def publish(args):
    folder = Path(args.state_dir)
    state = load(folder)
    generation = sha(json.dumps(state).encode("utf-8"))
    output = folder / "releases" / generation
    output.mkdir(parents=True, exist_ok=True)
    (folder / "CURRENT").write_text(generation + "\n", encoding="ascii")
    (output / "manifest.json").write_text(json.dumps({"generation_id": generation}), encoding="utf-8")


def read(args):
    folder = Path(args.state_dir)
    generation = (folder / "CURRENT").read_text(encoding="ascii").strip() if args.generation == "CURRENT" else args.generation
    manifest = json.loads((folder / "releases" / generation / "manifest.json").read_text(encoding="utf-8"))
    print(json.dumps(manifest, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("bootstrap")
    b.add_argument("--state-dir", required=True)
    b.add_argument("--drugs", required=True)
    b.add_argument("--events", required=True)
    b.add_argument("--interactions", required=True)
    a = commands.add_parser("apply")
    a.add_argument("--state-dir", required=True)
    a.add_argument("--batch", required=True)
    a.add_argument("--crash", choices=("after_prepare", "after_commit"))
    p = commands.add_parser("publish")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--crash", choices=("after_generation", "after_current"))
    p.add_argument("--ready")
    p.add_argument("--continue", dest="continue_path")
    r = commands.add_parser("recover")
    r.add_argument("--state-dir", required=True)
    rd = commands.add_parser("read")
    rd.add_argument("--state-dir", required=True)
    rd.add_argument("--generation", required=True)
    rd.add_argument("--ready")
    rd.add_argument("--continue", dest="continue_path")
    args = parser.parse_args()
    try:
        if args.command == "bootstrap":
            bootstrap(args)
        elif args.command == "apply":
            apply(args)
        elif args.command in ("publish", "recover"):
            publish(args)
        else:
            read(args)
    except (OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
