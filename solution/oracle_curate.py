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

from publication import PublicationError, publish, valid_id

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


def load_drugs(records):
    rows = 0
    invalid_rows = []
    all_ids = set()
    valid_by_id = defaultdict(set)

    for line, row in records:
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


def load_events(records):
    rows = 0
    invalid_rows = []
    descriptions = defaultdict(set)

    for line, row in records:
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


def read_interactions(path: Path):
    records = iter(nonblank_rows(path))
    try:
        _, header = next(records)
    except StopIteration as exc:
        raise CuratorError(f"missing header in {path}") from exc
    if header != ["d1", "type", "d2"]:
        raise CuratorError(f"invalid interaction header in {path}; expected d1,type,d2")
    return list(records)


def load_interactions(
    records,
    all_ids,
    conflicting_ids,
    invalid_ids,
    id_to_rep,
    known_types,
    conflicting_types,
):
    dropped = {key: 0 for key in DROP_KEYS}
    kept = set()
    interaction_rows = 0
    for _, row in records:
        interaction_rows += 1
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


def read_changes(path: Path, header: list[str], operations: set[str]):
    records = iter(nonblank_rows(path))
    try:
        _, actual = next(records)
    except StopIteration as exc:
        raise CuratorError(f"missing change header in {path}") from exc
    if actual != header:
        raise CuratorError(f"invalid change header in {path}; expected {','.join(header)}")
    changes = []
    previous = 0
    for line, row in records:
        if len(row) != len(header):
            raise CuratorError(f"invalid change field count in {path}:{line}")
        seq = parse_event_type(row[0])
        if seq is None or seq <= previous or seq <= 0:
            raise CuratorError(f"invalid or non-increasing seq in {path}:{line}")
        previous = seq
        if row[1] not in operations:
            raise CuratorError(f"invalid change operation in {path}:{line}")
        if header[2] == "drug_id":
            if not row[2] or (row[1] == "DELETE" and row[3]):
                raise CuratorError(f"invalid drug change key/value in {path}:{line}")
            if row[1] == "UPSERT":
                if not row[3] or Chem.MolFromSmiles(row[3], sanitize=True) is None:
                    raise CuratorError(f"invalid drug change SMILES in {path}:{line}")
        elif header[2] == "event_type":
            event_type = parse_event_type(row[2])
            if event_type is None or (row[1] == "DELETE" and row[3]) or (row[1] == "UPSERT" and not row[3]):
                raise CuratorError(f"invalid event change key/value in {path}:{line}")
            row[2] = str(event_type)
        else:
            event_type = parse_event_type(row[3])
            if not row[2] or event_type is None or not row[4]:
                raise CuratorError(f"invalid interaction change key in {path}:{line}")
            row[3] = str(event_type)
        changes.append((line, row))
    return changes


def apply_dictionary_changes(records, changes, kind):
    result = list(records)
    for line, row in changes:
        _, operation, key, value = row
        if kind == "drug":
            matches = lambda candidate: bool(candidate) and candidate[0] == key
        else:
            matches = lambda candidate: bool(candidate) and parse_event_type(candidate[0]) == int(key)
        result = [(old_line, old_row) for old_line, old_row in result if not matches(old_row)]
        if operation == "UPSERT":
            result.append((line, [key, value]))
    return result


def apply_interaction_changes(records, changes):
    result = list(records)
    for line, row in changes:
        _, operation, d1, raw_type, d2 = row
        key = (d1, int(raw_type), d2)
        if operation == "ADD":
            result.append((line, [d1, raw_type, d2]))
        else:
            result = [
                (old_line, old_row)
                for old_line, old_row in result
                if not (
                    len(old_row) == 3
                    and old_row[0] == key[0]
                    and parse_event_type(old_row[1]) == key[1]
                    and old_row[2] == key[2]
                )
            ]
    return result


def curate_snapshot(drug_records, event_records, interaction_records):
    drug_rows, all_ids, conflicting_ids, invalid_ids, id_to_rep, clean_drugs, drug_report = load_drugs(drug_records)
    event_rows, known_types, conflicting_types, _, event_report = load_events(event_records)
    interaction_rows, clean_interactions, interaction_report = load_interactions(
        interaction_records, all_ids, conflicting_ids, invalid_ids, id_to_rep,
        known_types, conflicting_types,
    )
    counts = {"drug_rows": drug_rows, "event_rows": event_rows, "interaction_rows": interaction_rows}
    return counts, clean_drugs, clean_interactions, drug_report, event_report, interaction_report


def semantic_interactions(drugs, interactions):
    by_representative = {representative: smiles for representative, smiles, _ in drugs}
    return {
        (by_representative[d1], event_type, by_representative[d2]): (d1, event_type, d2)
        for d1, event_type, d2 in interactions
    }


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
    drug_change_path = Path(args.drug_changes)
    event_change_path = Path(args.event_changes)
    interaction_change_path = Path(args.interaction_changes)
    for path in (drug_path, event_path, interaction_path, drug_change_path, event_change_path, interaction_change_path):
        if not path.is_file():
            raise CuratorError(f"missing input file: {path}")

    drug_records = list(nonblank_rows(drug_path))
    event_records = list(nonblank_rows(event_path))
    interaction_records = read_interactions(interaction_path)
    drug_changes = read_changes(drug_change_path, ["seq", "op", "drug_id", "SMILES"], {"UPSERT", "DELETE"})
    event_changes = read_changes(event_change_path, ["seq", "op", "event_type", "description"], {"UPSERT", "DELETE"})
    interaction_changes = read_changes(interaction_change_path, ["seq", "op", "d1", "type", "d2"], {"ADD", "DELETE"})

    input_counts, baseline_drugs, baseline_interactions, _, _, _ = curate_snapshot(
        drug_records, event_records, interaction_records
    )
    final_drug_records = apply_dictionary_changes(drug_records, drug_changes, "drug")
    final_event_records = apply_dictionary_changes(event_records, event_changes, "event")
    final_interaction_records = apply_interaction_changes(interaction_records, interaction_changes)
    final_counts, clean_drugs, clean_interactions, drug_report, event_report, interaction_report = curate_snapshot(
        final_drug_records, final_event_records, final_interaction_records
    )
    baseline_semantic = semantic_interactions(baseline_drugs, baseline_interactions)
    final_semantic = semantic_interactions(clean_drugs, clean_interactions)
    removed_keys = baseline_semantic.keys() - final_semantic.keys()
    added_keys = final_semantic.keys() - baseline_semantic.keys()
    delta_rows = [
        ("REMOVE", *baseline_semantic[key]) for key in removed_keys
    ] + [
        ("ADD", *final_semantic[key]) for key in added_keys
    ]
    delta_rows.sort(key=lambda item: (0 if item[0] == "REMOVE" else 1, item[1], item[2], item[3]))

    drugs_bytes = render_csv(
        ("drug_id", "canonical_smiles", "aliases"), clean_drugs
    )
    interactions_bytes = render_csv(
        ("d1", "type", "d2"), clean_interactions
    )
    delta_bytes = render_csv(("action", "d1", "type", "d2"), delta_rows)
    report = {
        "input": input_counts,
        "final_input": final_counts,
        "changes": {
            "drug_rows": len(drug_changes),
            "event_rows": len(event_changes),
            "interaction_rows": len(interaction_changes),
            "delta_added": len(added_keys),
            "delta_removed": len(removed_keys),
        },
        "drugs": drug_report,
        "events": event_report,
        "interactions": interaction_report,
        "files": {
            "drugs_clean.csv": {"sha256": sha256(drugs_bytes)},
            "interactions_clean.csv": {"sha256": sha256(interactions_bytes)},
            "interaction_delta.csv": {"sha256": sha256(delta_bytes)},
        },
    }
    report_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    artifacts = {"drugs_clean.csv": drugs_bytes, "interactions_clean.csv": interactions_bytes,
                 "interaction_delta.csv": delta_bytes, "report.json": report_bytes}
    if args.release_id is not None:
        publish(args.out_dir, args.release_id,
                None if args.expected_parent == "NONE" else args.expected_parent, artifacts)
    else:
        output = Path(args.out_dir)
        for name, payload in artifacts.items():
            atomic_write(output / name, payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drugs", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--interactions", required=True)
    parser.add_argument("--drug-changes", required=True)
    parser.add_argument("--event-changes", required=True)
    parser.add_argument("--interaction-changes", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--release-id")
    parser.add_argument("--expected-parent")
    args = parser.parse_args()
    try:
        if (args.release_id is None) != (args.expected_parent is None):
            raise CuratorError("release-id and expected-parent must be paired")
        if args.release_id is not None and (not valid_id(args.release_id) or
                (args.expected_parent != "NONE" and not valid_id(args.expected_parent))):
            raise CuratorError("invalid release or parent ID")
        curate(args)
    except (CuratorError, PublicationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
