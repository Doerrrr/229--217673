#!/usr/bin/env python3
"""Reference implementation for deterministic DDI dataset curation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from rdkit import Chem, RDLogger


RDLogger.DisableLog("rdApp.error")


class CuratorError(Exception):
    """Fatal input-contract error."""


def nonblank_rows(path: Path):
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise CuratorError(f"cannot open {path}: {exc.strerror or exc}") from exc
    with handle:
        try:
            reader = csv.reader(handle, strict=True)
            for row in reader:
                if not row or all(not field.strip() for field in row):
                    continue
                yield reader.line_num, [field.strip() for field in row]
        except csv.Error as exc:
            raise CuratorError(f"invalid CSV in {path}: {exc}") from exc


def load_drugs(path: Path):
    rows = 0
    invalid_rows = []
    all_ids = set()
    valid_by_id = defaultdict(set)

    for line, row in nonblank_rows(path):
        rows += 1
        drug_id = row[0].strip() if row else ""
        if len(row) != 2 or not drug_id or not row[1]:
            invalid_rows.append(
                {"line": line, "drug_id": drug_id, "reason": "malformed"}
            )
            if drug_id:
                all_ids.add(drug_id)
            continue

        all_ids.add(drug_id)
        molecule = Chem.MolFromSmiles(row[1], sanitize=True)
        if molecule is None:
            invalid_rows.append(
                {"line": line, "drug_id": drug_id, "reason": "invalid_smiles"}
            )
            continue
        canonical = Chem.MolToSmiles(
            molecule, canonical=True, isomericSmiles=True
        )
        valid_by_id[drug_id].add(canonical)

    conflicting_ids = sorted(
        drug_id for drug_id, values in valid_by_id.items() if len(values) > 1
    )
    conflicting = set(conflicting_ids)
    canonical_by_id = {
        drug_id: next(iter(values))
        for drug_id, values in valid_by_id.items()
        if len(values) == 1 and drug_id not in conflicting
    }
    invalid_only_ids = sorted(all_ids - set(valid_by_id))

    ids_by_canonical = defaultdict(list)
    for drug_id, canonical in canonical_by_id.items():
        ids_by_canonical[canonical].append(drug_id)

    id_to_rep = {}
    clean_rows = []
    for canonical, aliases in ids_by_canonical.items():
        aliases = sorted(aliases)
        representative = aliases[0]
        for alias in aliases:
            id_to_rep[alias] = representative
        clean_rows.append((representative, canonical, ";".join(aliases)))
    clean_rows.sort(key=lambda item: item[0])

    report = {
        "valid_ids": len(canonical_by_id),
        "unique_molecules": len(clean_rows),
        "invalid_rows": sorted(invalid_rows, key=lambda item: item["line"]),
        "invalid_only_ids": invalid_only_ids,
        "conflicting_ids": conflicting_ids,
    }
    return rows, all_ids, conflicting, set(invalid_only_ids), id_to_rep, clean_rows, report


def parse_event_type(value: str):
    value = value.strip()
    if not value or not value.isascii() or not value.isdigit():
        return None
    return int(value)


def load_events(path: Path):
    rows = 0
    invalid_rows = []
    descriptions = defaultdict(set)

    for line, row in nonblank_rows(path):
        rows += 1
        raw_type = row[0].strip() if row else ""
        if len(row) != 2:
            invalid_rows.append(
                {"line": line, "event_type": raw_type, "reason": "malformed"}
            )
            continue
        event_type = parse_event_type(raw_type)
        if event_type is None:
            invalid_rows.append(
                {"line": line, "event_type": raw_type, "reason": "invalid_type"}
            )
            continue
        description = row[1].strip()
        if not description:
            invalid_rows.append(
                {
                    "line": line,
                    "event_type": str(event_type),
                    "reason": "empty_description",
                }
            )
            continue
        descriptions[event_type].add(description)

    conflicting_types = sorted(
        event_type
        for event_type, values in descriptions.items()
        if len(values) > 1
    )
    conflicting = set(conflicting_types)
    valid_types = set(descriptions) - conflicting
    report = {
        "valid_types": len(valid_types),
        "invalid_rows": sorted(invalid_rows, key=lambda item: item["line"]),
        "conflicting_types": conflicting_types,
    }
    return rows, set(descriptions), conflicting, valid_types, report


DROP_KEYS = (
    "malformed",
    "missing_drug",
    "conflicting_drug",
    "invalid_drug",
    "unknown_type",
    "conflicting_type",
    "self_interaction",
    "alias_self_interaction",
    "duplicate",
)


def load_interactions(
    path: Path,
    all_ids,
    conflicting_ids,
    invalid_ids,
    id_to_rep,
    known_types,
    conflicting_types,
):
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise CuratorError(f"cannot open {path}: {exc.strerror or exc}") from exc

    dropped = {key: 0 for key in DROP_KEYS}
    kept = set()
    interaction_rows = 0
    with handle:
        try:
            reader = csv.reader(handle, strict=True)
            header = None
            for row in reader:
                if row and any(field.strip() for field in row):
                    header = row
                    break
            if header is None:
                raise CuratorError(f"missing header in {path}")
            normalized_header = [field.strip() for field in header]
            if normalized_header != ["d1", "type", "d2"]:
                raise CuratorError(
                    f"invalid interaction header in {path}; expected d1,type,d2"
                )

            for row in reader:
                if not row or all(not field.strip() for field in row):
                    continue
                interaction_rows += 1
                row = [field.strip() for field in row]
                if len(row) != 3 or not row[0] or not row[2]:
                    dropped["malformed"] += 1
                    continue
                d1, raw_type, d2 = row
                event_type = parse_event_type(raw_type)
                if event_type is None:
                    dropped["malformed"] += 1
                    continue
                if d1 not in all_ids or d2 not in all_ids:
                    dropped["missing_drug"] += 1
                    continue
                if d1 in conflicting_ids or d2 in conflicting_ids:
                    dropped["conflicting_drug"] += 1
                    continue
                if d1 in invalid_ids or d2 in invalid_ids:
                    dropped["invalid_drug"] += 1
                    continue
                if event_type not in known_types:
                    dropped["unknown_type"] += 1
                    continue
                if event_type in conflicting_types:
                    dropped["conflicting_type"] += 1
                    continue
                if d1 == d2:
                    dropped["self_interaction"] += 1
                    continue

                representative_1 = id_to_rep[d1]
                representative_2 = id_to_rep[d2]
                if representative_1 == representative_2:
                    dropped["alias_self_interaction"] += 1
                    continue
                triple = (representative_1, event_type, representative_2)
                if triple in kept:
                    dropped["duplicate"] += 1
                    continue
                kept.add(triple)
        except csv.Error as exc:
            raise CuratorError(f"invalid CSV in {path}: {exc}") from exc

    clean_rows = sorted(kept, key=lambda item: (item[0], item[1], item[2]))
    report = {"kept": len(clean_rows), "dropped": dropped}
    return interaction_rows, clean_rows, report


def render_csv(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sha256(data: bytes):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def curate(args):
    drug_path = Path(args.drugs)
    event_path = Path(args.events)
    interaction_path = Path(args.interactions)
    for path in (drug_path, event_path, interaction_path):
        if not path.is_file():
            raise CuratorError(f"missing input file: {path}")

    (
        drug_rows,
        all_ids,
        conflicting_ids,
        invalid_ids,
        id_to_rep,
        clean_drugs,
        drug_report,
    ) = load_drugs(drug_path)
    (
        event_rows,
        known_types,
        conflicting_types,
        _valid_types,
        event_report,
    ) = load_events(event_path)
    interaction_rows, clean_interactions, interaction_report = load_interactions(
        interaction_path,
        all_ids,
        conflicting_ids,
        invalid_ids,
        id_to_rep,
        known_types,
        conflicting_types,
    )

    drugs_bytes = render_csv(
        ("drug_id", "canonical_smiles", "aliases"), clean_drugs
    )
    interactions_bytes = render_csv(
        ("d1", "type", "d2"), clean_interactions
    )
    report = {
        "input": {
            "drug_rows": drug_rows,
            "event_rows": event_rows,
            "interaction_rows": interaction_rows,
        },
        "drugs": drug_report,
        "events": event_report,
        "interactions": interaction_report,
        "files": {
            "drugs_clean.csv": {"sha256": sha256(drugs_bytes)},
            "interactions_clean.csv": {"sha256": sha256(interactions_bytes)},
        },
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    output = Path(args.out_dir)
    atomic_write(output / "drugs_clean.csv", drugs_bytes)
    atomic_write(output / "interactions_clean.csv", interactions_bytes)
    atomic_write(output / "report.json", report_bytes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drugs", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--interactions", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    try:
        curate(args)
    except CuratorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
