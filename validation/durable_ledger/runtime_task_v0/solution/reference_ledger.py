#!/usr/bin/env python3
"""Reference process-crash-safe DDI ledger; internal to the author bundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time

from curation import CuratorError, curate_snapshot, parse_event_type, render_csv


FEEDS = ("drugs", "events", "interactions")
BASE_NAMES = {"drugs": "drug_list.csv", "events": "DDI_event.csv", "interactions": "newddi.csv"}
BATCH_ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
GENERATION_ID = re.compile(r"[0-9a-f]{64}\Z")
DROP_KEYS = ("malformed", "missing_drug", "conflicting_drug", "invalid_drug",
             "unknown_type", "conflicting_type", "self_interaction",
             "alias_self_interaction", "duplicate")


class LedgerError(Exception):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise LedgerError(f"non-finite JSON value: {value}")


def strict_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicate_keys,
                          parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerError(f"invalid UTF-8 JSON: {exc}") from exc


def exact_keys(value, expected: set[str], where: str):
    if type(value) is not dict or set(value) != expected:
        raise LedgerError(f"invalid fields in {where}")


def decimal(value: str, where: str) -> str:
    if type(value) is not str or not value or not value.isascii() or not value.isdecimal():
        raise LedgerError(f"invalid decimal in {where}")
    return str(int(value))


def clean_id(value, where: str) -> str:
    if type(value) is not str or not value.strip():
        raise LedgerError(f"invalid identifier in {where}")
    return value.strip()


def parse_batch(raw: bytes):
    batch = strict_json(raw)
    exact_keys(batch, {"batch_id", "number", "operations"}, "batch")
    if type(batch["batch_id"]) is not str or BATCH_ID.fullmatch(batch["batch_id"]) is None:
        raise LedgerError("invalid batch_id")
    if type(batch["number"]) is not int or batch["number"] <= 0:
        raise LedgerError("invalid batch number")
    if type(batch["operations"]) is not list:
        raise LedgerError("operations must be an array")
    operations = []
    for index, operation in enumerate(batch["operations"]):
        where = f"operation {index + 1}"
        if type(operation) is not dict or operation.get("feed") not in ("drug", "event", "interaction"):
            raise LedgerError(f"invalid feed in {where}")
        feed, action = operation["feed"], operation.get("op")
        if feed == "drug":
            expected = {"feed", "op", "drug_id"} | ({"SMILES"} if action == "UPSERT" else set())
            exact_keys(operation, expected, where)
            if action not in ("UPSERT", "DELETE"):
                raise LedgerError(f"invalid drug operation in {where}")
            key = clean_id(operation["drug_id"], where)
            if action == "UPSERT":
                if type(operation["SMILES"]) is not str:
                    raise LedgerError(f"invalid SMILES field in {where}")
                operations.append(("drug", action, key, operation["SMILES"].strip()))
            else:
                operations.append(("drug", action, key))
        elif feed == "event":
            expected = {"feed", "op", "event_type"} | ({"description"} if action == "UPSERT" else set())
            exact_keys(operation, expected, where)
            if action not in ("UPSERT", "DELETE"):
                raise LedgerError(f"invalid event operation in {where}")
            key = decimal(operation["event_type"].strip() if type(operation["event_type"]) is str else None, where)
            if action == "UPSERT":
                if type(operation["description"]) is not str:
                    raise LedgerError(f"invalid event description in {where}")
                operations.append(("event", action, key, operation["description"].strip()))
            else:
                operations.append(("event", action, key))
        else:
            exact_keys(operation, {"feed", "op", "d1", "type", "d2"}, where)
            if action not in ("ADD", "DELETE"):
                raise LedgerError(f"invalid interaction operation in {where}")
            d1 = clean_id(operation["d1"], where)
            d2 = clean_id(operation["d2"], where)
            event_type = decimal(operation["type"].strip() if type(operation["type"]) is str else None, where)
            operations.append(("interaction", action, d1, event_type, d2))
    return batch["batch_id"], batch["number"], operations


def records(raw: bytes, feed: str):
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        rows = []
        for row in reader:
            if not row or all(not field.strip() for field in row):
                continue
            rows.append((reader.line_num, [field.strip() for field in row]))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise LedgerError(f"invalid {feed} CSV: {exc}") from exc
    if feed == "interactions":
        if not rows or rows[0][1] != ["d1", "type", "d2"]:
            raise LedgerError("invalid interaction header")
        return rows[1:]
    return rows


def connect(state: Path):
    path = state / "ledger.sqlite3"
    if not path.is_file():
        raise LedgerError("ledger has not been bootstrapped")
    db = sqlite3.connect(path, timeout=30.0)
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS base (feed TEXT PRIMARY KEY, body BLOB NOT NULL, sha TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batch (
            number INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL UNIQUE,
            sha TEXT NOT NULL,
            body BLOB NOT NULL
        );
    """)


def bootstrap(args):
    paths = {"drugs": Path(args.drugs), "events": Path(args.events),
             "interactions": Path(args.interactions)}
    bodies = {feed: path.read_bytes() for feed, path in paths.items()}
    for feed, body in bodies.items():
        records(body, feed)
    state = Path(args.state_dir)
    state.mkdir(parents=True, exist_ok=True)
    path = state / "ledger.sqlite3"
    db = sqlite3.connect(path, timeout=30.0)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        initialize(db)
        db.execute("BEGIN IMMEDIATE")
        existing = dict(db.execute("SELECT feed, sha FROM base"))
        wanted = {feed: digest(body) for feed, body in bodies.items()}
        if existing and existing != wanted:
            raise LedgerError("bootstrap source conflict")
        if not existing:
            db.executemany("INSERT INTO base VALUES (?,?,?)",
                           [(feed, bodies[feed], wanted[feed]) for feed in FEEDS])
        db.commit()
    finally:
        db.close()


def apply(args):
    raw = Path(args.batch).read_bytes()
    batch_id, number, _ = parse_batch(raw)
    db = connect(Path(args.state_dir))
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM base").fetchone()[0] != 3:
            raise LedgerError("incomplete bootstrap")
        old = db.execute("SELECT sha FROM batch WHERE batch_id=?", (batch_id,)).fetchone()
        wanted = digest(raw)
        if old is not None:
            if old[0] != wanted:
                raise LedgerError("batch_id content conflict")
            db.commit()
            return
        last = db.execute("SELECT COALESCE(MAX(number),0) FROM batch").fetchone()[0]
        if number != last + 1:
            raise LedgerError("batch number must be next consecutive number")
        if args.crash == "after_prepare":
            os._exit(75)
        db.execute("INSERT INTO batch VALUES (?,?,?,?)", (number, batch_id, wanted, raw))
        db.commit()
        if args.crash == "after_commit":
            os._exit(75)
    finally:
        db.close()


def replay(base: dict[str, bytes], batches):
    drugs = records(base["drugs"], "drugs")
    events = records(base["events"], "events")
    interactions = records(base["interactions"], "interactions")
    next_line = max([line for rows in (drugs, events, interactions) for line, _ in rows] + [0]) + 1
    for _, _, _, raw in batches:
        _, _, operations = parse_batch(raw)
        for operation in operations:
            feed, action, *fields = operation
            if feed == "drug":
                key = fields[0]
                drugs = [(line, row) for line, row in drugs if not row or row[0] != key]
                if action == "UPSERT":
                    drugs.append((next_line, [key, fields[1]]))
                    next_line += 1
            elif feed == "event":
                key = int(fields[0])
                events = [(line, row) for line, row in events
                          if not row or parse_event_type(row[0]) != key]
                if action == "UPSERT":
                    events.append((next_line, [fields[0], fields[1]]))
                    next_line += 1
            elif action == "ADD":
                interactions.append((next_line, [fields[0], fields[1], fields[2]]))
                next_line += 1
            else:
                d1, typ, d2 = fields
                interactions = [(line, row) for line, row in interactions
                                if not (len(row) == 3 and row[0] == d1
                                        and parse_event_type(row[1]) == int(typ)
                                        and row[2] == d2)]
    return drugs, events, interactions


def barrier(ready, continue_path):
    if (ready is None) != (continue_path is None):
        raise LedgerError("both barrier paths are required")
    if ready is None:
        return
    Path(ready).write_text("ready\n", encoding="ascii")
    deadline = time.monotonic() + 30.0
    while not Path(continue_path).exists():
        if time.monotonic() >= deadline:
            raise LedgerError("operational barrier timed out")
        time.sleep(0.01)


def publish(args):
    if (args.ready is None) != (args.continue_path is None):
        raise LedgerError("both publish barriers are required")
    state = Path(args.state_dir)
    db = connect(state)
    try:
        db.execute("BEGIN IMMEDIATE")
        base_rows = list(db.execute("SELECT feed, body, sha FROM base"))
        if len(base_rows) != 3:
            raise LedgerError("incomplete bootstrap")
        base_bodies = {feed: body for feed, body, _ in base_rows}
        base_hashes = {feed: sha for feed, _, sha in base_rows}
        batch_rows = list(db.execute("SELECT number, batch_id, sha, body FROM batch ORDER BY number"))
        barrier(args.ready, args.continue_path)
        receipts = [{"batch_id": batch_id, "number": number, "sha256": sha}
                    for number, batch_id, sha, _ in batch_rows]
        state_id = digest(canonical({"base": base_hashes, "batches": receipts}))
        drugs, events, interactions = replay(base_bodies, batch_rows)
        counts, clean_drugs, clean_interactions, drug_report, event_report, interaction_report = (
            curate_snapshot(drugs, events, interactions))
        drug_csv = render_csv(("drug_id", "canonical_smiles", "aliases"), clean_drugs)
        interaction_csv = render_csv(("d1", "type", "d2"), clean_interactions)
        report = {
            "state_id": state_id,
            "batch_number": receipts[-1]["number"] if receipts else 0,
            "raw_rows": {"drugs": counts["drug_rows"], "events": counts["event_rows"],
                         "interactions": counts["interaction_rows"]},
            "drugs": {"valid_ids": drug_report["valid_ids"],
                      "unique_molecules": drug_report["unique_molecules"],
                      "invalid_rows": len(drug_report["invalid_rows"]),
                      "invalid_only_ids": drug_report["invalid_only_ids"],
                      "conflicting_ids": drug_report["conflicting_ids"]},
            "events": {"valid_types": event_report["valid_types"],
                       "invalid_rows": len(event_report["invalid_rows"]),
                       "conflicting_types": event_report["conflicting_types"]},
            "interactions": {"kept": interaction_report["kept"],
                             "dropped": {key: interaction_report["dropped"][key] for key in DROP_KEYS}},
            "files": {"drugs_clean.csv": digest(drug_csv),
                      "interactions_clean.csv": digest(interaction_csv)},
        }
        report_bytes = canonical(report)
        file_bodies = {"drugs_clean.csv": drug_csv,
                       "interactions_clean.csv": interaction_csv,
                       "report.json": report_bytes}
        hashes = {name: digest(body) for name, body in file_bodies.items()}
        generation_id = digest(canonical({"state_id": state_id, "files": hashes}))
        manifest = {"generation_id": generation_id, "state_id": state_id,
                    "base": base_hashes, "batches": receipts, "files": hashes}
        file_bodies["manifest.json"] = canonical(manifest)
        release_root = state / "releases"
        release_root.mkdir(parents=True, exist_ok=True)
        target = release_root / generation_id
        if target.exists():
            if not target.is_dir() or any((target / name).read_bytes() != body
                                          for name, body in file_bodies.items()):
                raise LedgerError("existing generation is incomplete or corrupt")
        else:
            staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=release_root))
            for name, body in file_bodies.items():
                with (staging / name).open("wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
            os.rename(staging, target)
        if args.crash == "after_generation":
            os._exit(75)
        with tempfile.NamedTemporaryFile(prefix=".CURRENT-", dir=state,
                                         delete=False) as stream:
            stream.write((generation_id + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        os.replace(temporary, state / "CURRENT")
        if args.crash == "after_current":
            os._exit(75)
        db.commit()
    finally:
        db.close()


def read(args):
    state = Path(args.state_dir)
    if args.generation == "CURRENT":
        generation_id = (state / "CURRENT").read_text(encoding="ascii").strip()
    else:
        generation_id = args.generation
    if GENERATION_ID.fullmatch(generation_id) is None:
        raise LedgerError("invalid generation ID")
    folder = state / "releases" / generation_id
    barrier(args.ready, args.continue_path)
    manifest_bytes = (folder / "manifest.json").read_bytes()
    manifest = strict_json(manifest_bytes)
    if manifest_bytes != canonical(manifest):
        raise LedgerError("noncanonical manifest")
    exact_keys(manifest, {"generation_id", "state_id", "base", "batches", "files"}, "manifest")
    if manifest["generation_id"] != generation_id:
        raise LedgerError("generation ID mismatch")
    state_id = digest(canonical({"base": manifest["base"], "batches": manifest["batches"]}))
    if manifest["state_id"] != state_id:
        raise LedgerError("state ID mismatch")
    hashes = manifest["files"]
    exact_keys(hashes, {"drugs_clean.csv", "interactions_clean.csv", "report.json"}, "files")
    for name, wanted in hashes.items():
        if digest((folder / name).read_bytes()) != wanted:
            raise LedgerError(f"corrupt published file: {name}")
    expected_id = digest(canonical({"state_id": state_id, "files": hashes}))
    if expected_id != generation_id:
        raise LedgerError("generation digest mismatch")
    report = strict_json((folder / "report.json").read_bytes())
    if report.get("state_id") != state_id:
        raise LedgerError("report state mismatch")
    number = manifest["batches"][-1]["number"] if manifest["batches"] else 0
    if report.get("batch_number") != number:
        raise LedgerError("report batch mismatch")
    sys.stdout.buffer.write(canonical({"generation_id": generation_id, "state_id": state_id,
                                       "batch_number": number, "files": hashes}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap_parser = commands.add_parser("bootstrap")
    bootstrap_parser.add_argument("--state-dir", required=True)
    bootstrap_parser.add_argument("--drugs", required=True)
    bootstrap_parser.add_argument("--events", required=True)
    bootstrap_parser.add_argument("--interactions", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--state-dir", required=True)
    apply_parser.add_argument("--batch", required=True)
    apply_parser.add_argument("--crash", choices=("after_prepare", "after_commit"))
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--state-dir", required=True)
    publish_parser.add_argument("--crash", choices=("after_generation", "after_current"))
    publish_parser.add_argument("--ready")
    publish_parser.add_argument("--continue", dest="continue_path")
    recover_parser = commands.add_parser("recover")
    recover_parser.add_argument("--state-dir", required=True)
    read_parser = commands.add_parser("read")
    read_parser.add_argument("--state-dir", required=True)
    read_parser.add_argument("--generation", required=True)
    read_parser.add_argument("--ready")
    read_parser.add_argument("--continue", dest="continue_path")
    args = parser.parse_args()
    try:
        if args.command == "bootstrap":
            bootstrap(args)
        elif args.command == "apply":
            apply(args)
        elif args.command in ("publish", "recover"):
            if args.command == "recover":
                args.crash = None
                args.ready = args.continue_path = None
            publish(args)
        else:
            read(args)
    except (LedgerError, CuratorError, OSError, sqlite3.Error, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
