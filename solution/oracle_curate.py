#!/usr/bin/env python3
"""Curate baseline and changed DDI snapshots before writing any output."""

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from rdkit import Chem

import publication


_DECIMAL = re.compile(r"[0-9]+", re.ASCII)
_REASONS = (
    "malformed", "missing_drug", "conflicting_drug", "invalid_drug",
    "unknown_type", "conflicting_type", "self_interaction",
    "alias_self_interaction", "duplicate",
)
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


@dataclass(frozen=True)
class Record:
    fields: tuple
    line: int


def _number(value):
    if _DECIMAL.fullmatch(value) is None:
        return None
    return int(value, 10)


def _read_csv(path, header=None):
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        physical_lines = handle.readlines()
    reader = csv.reader(physical_lines, strict=True)
    records = []
    previous_line = 0
    found_header = header is None
    try:
        for fields in reader:
            line = reader.line_num
            occupied = physical_lines[previous_line:line]
            previous_line = line
            if all(not physical.strip() for physical in occupied):
                continue
            fields = tuple(field.strip() for field in fields)
            if not found_header:
                if fields != tuple(header):
                    raise ValueError(f"{path}:{line}: wrong CSV header")
                found_header = True
            else:
                records.append(Record(fields, line))
    except csv.Error as error:
        raise ValueError(f"{path}:{reader.line_num}: CSV syntax error: {error}") from error
    if not found_header:
        raise ValueError(f"{path}: missing CSV header")
    return records


def _canonical(smiles):
    try:
        molecule = Chem.MolFromSmiles(smiles, sanitize=False)
        if molecule is None:
            return None
        Chem.SanitizeMol(molecule)
        return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    except Exception:
        return None


def _validate_changes(records, kind):
    previous_seq = 0
    result = []
    width = 5 if kind == "interaction" else 4
    for record in records:
        fields = record.fields
        if len(fields) != width:
            raise ValueError(f"{kind} changes:{record.line}: wrong field count")
        seq = _number(fields[0])
        if seq is None or seq <= previous_seq:
            raise ValueError(f"{kind} changes:{record.line}: sequence must strictly increase")
        previous_seq = seq
        op = fields[1]
        if kind == "interaction":
            d1, event, d2 = fields[2:]
            event_type = _number(event)
            if op not in {"ADD", "DELETE"} or not d1 or not d2 or event_type is None:
                raise ValueError(f"interaction changes:{record.line}: invalid operation or key")
            result.append((op, (d1, event_type, d2), record))
        else:
            key, value = fields[2:]
            if kind == "event":
                key = _number(key)
                valid_key = key is not None
            else:
                valid_key = bool(key)
            if op not in {"UPSERT", "DELETE"} or not valid_key:
                raise ValueError(f"{kind} changes:{record.line}: invalid operation or key")
            if (op == "DELETE" and value) or (op == "UPSERT" and not value):
                raise ValueError(f"{kind} changes:{record.line}: invalid change value")
            if kind == "drug" and op == "UPSERT" and _canonical(value) is None:
                raise ValueError(f"drug changes:{record.line}: invalid SMILES")
            result.append((op, key, record))
    return result


def _raw_key(record, kind):
    fields = record.fields
    if kind == "drug":
        return fields[0] if fields else None
    if kind == "event":
        return _number(fields[0]) if fields else None
    if len(fields) >= 3:
        event = _number(fields[1])
        if event is not None:
            return fields[0], event, fields[2]
    return None


def _replay(original, changes, kind):
    rows = list(original)
    for op, key, record in changes:
        if op != "ADD":
            rows = [row for row in rows if _raw_key(row, kind) != key]
        if op in {"ADD", "UPSERT"}:
            rows.append(Record(record.fields[2:], record.line))
    return rows


def _curate(drug_records, event_records, interaction_records):
    known_ids = set()
    molecules_by_id = {}
    drug_invalid = []
    for record in drug_records:
        fields = record.fields
        drug_id = fields[0] if fields else ""
        if drug_id:
            known_ids.add(drug_id)
        reason = None
        if len(fields) != 2 or not drug_id or not fields[1]:
            reason = "malformed"
        else:
            smiles = _canonical(fields[1])
            if smiles is None:
                reason = "invalid_smiles"
            else:
                molecules_by_id.setdefault(drug_id, set()).add(smiles)
        if reason is not None:
            drug_invalid.append({"line": record.line, "drug_id": drug_id, "reason": reason})

    conflicting_ids = {key for key, values in molecules_by_id.items() if len(values) > 1}
    invalid_ids = known_ids - set(molecules_by_id)
    id_smiles = {
        key: next(iter(values)) for key, values in molecules_by_id.items() if len(values) == 1
    }
    ids_by_smiles = {}
    for drug_id, smiles in id_smiles.items():
        ids_by_smiles.setdefault(smiles, []).append(drug_id)
    representatives = {}
    representative_smiles = {}
    clean_drugs = []
    for smiles, ids in ids_by_smiles.items():
        ids.sort()
        representative = ids[0]
        representative_smiles[representative] = smiles
        for drug_id in ids:
            representatives[drug_id] = representative
        clean_drugs.append((representative, smiles, ";".join(ids)))
    clean_drugs.sort()

    descriptions = {}
    event_invalid = []
    for record in event_records:
        fields = record.fields
        raw_type = fields[0] if fields else ""
        reason = None
        if len(fields) != 2:
            reason = "malformed"
        else:
            event_type = _number(raw_type)
            if event_type is None:
                reason = "invalid_type"
            elif not fields[1]:
                reason = "empty_description"
            else:
                descriptions.setdefault(event_type, set()).add(fields[1])
        if reason is not None:
            event_invalid.append({"line": record.line, "event_type": raw_type, "reason": reason})
    conflicting_types = {key for key, values in descriptions.items() if len(values) > 1}

    kept = set()
    dropped = dict.fromkeys(_REASONS, 0)
    for record in interaction_records:
        fields = record.fields
        reason = None
        if len(fields) != 3 or not fields[0] or not fields[2]:
            reason = "malformed"
        else:
            d1, raw_type, d2 = fields
            event_type = _number(raw_type)
            if event_type is None:
                reason = "malformed"
            elif d1 not in known_ids or d2 not in known_ids:
                reason = "missing_drug"
            elif d1 in conflicting_ids or d2 in conflicting_ids:
                reason = "conflicting_drug"
            elif d1 in invalid_ids or d2 in invalid_ids:
                reason = "invalid_drug"
            elif event_type not in descriptions:
                reason = "unknown_type"
            elif event_type in conflicting_types:
                reason = "conflicting_type"
            elif d1 == d2:
                reason = "self_interaction"
            elif representatives[d1] == representatives[d2]:
                reason = "alias_self_interaction"
            else:
                mapped = (representatives[d1], event_type, representatives[d2])
                if mapped in kept:
                    reason = "duplicate"
                else:
                    kept.add(mapped)
        if reason is not None:
            dropped[reason] += 1

    stats = {
        "drugs": {
            "valid_ids": len(id_smiles), "unique_molecules": len(clean_drugs),
            "invalid_rows": sorted(drug_invalid, key=lambda row: row["line"]),
            "invalid_only_ids": sorted(invalid_ids), "conflicting_ids": sorted(conflicting_ids),
        },
        "events": {
            "valid_types": len(descriptions) - len(conflicting_types),
            "invalid_rows": sorted(event_invalid, key=lambda row: row["line"]),
            "conflicting_types": sorted(conflicting_types),
        },
        "interactions": {"kept": len(kept), "dropped": dropped},
    }
    semantic = {
        (representative_smiles[d1], event, representative_smiles[d2]): (d1, event, d2)
        for d1, event, d2 in kept
    }
    return clean_drugs, sorted(kept), semantic, stats


def _csv_bytes(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build_artifacts(args):
    drugs = _read_csv(args.drugs)
    events = _read_csv(args.events)
    interactions = _read_csv(args.interactions, ("d1", "type", "d2"))
    drug_changes = _read_csv(args.drug_changes, ("seq", "op", "drug_id", "SMILES"))
    event_changes = _read_csv(args.event_changes, ("seq", "op", "event_type", "description"))
    interaction_changes = _read_csv(
        args.interaction_changes, ("seq", "op", "d1", "type", "d2")
    )
    parsed_drugs = _validate_changes(drug_changes, "drug")
    parsed_events = _validate_changes(event_changes, "event")
    parsed_interactions = _validate_changes(interaction_changes, "interaction")
    baseline = _curate(drugs, events, interactions)
    final_drugs = _replay(drugs, parsed_drugs, "drug")
    final_events = _replay(events, parsed_events, "event")
    final_interactions = _replay(interactions, parsed_interactions, "interaction")
    clean_drugs, clean_interactions, semantic, stats = _curate(
        final_drugs, final_events, final_interactions
    )
    baseline_semantic = baseline[2]
    removed = sorted(baseline_semantic[key] for key in baseline_semantic.keys() - semantic.keys())
    added = sorted(semantic[key] for key in semantic.keys() - baseline_semantic.keys())
    delta = [("REMOVE", *row) for row in removed] + [("ADD", *row) for row in added]
    artifacts = {
        "drugs_clean.csv": _csv_bytes(("drug_id", "canonical_smiles", "aliases"), clean_drugs),
        "interactions_clean.csv": _csv_bytes(("d1", "type", "d2"), clean_interactions),
        "interaction_delta.csv": _csv_bytes(("action", "d1", "type", "d2"), delta),
    }
    report = {
        "input": {"drug_rows": len(drugs), "event_rows": len(events), "interaction_rows": len(interactions)},
        "final_input": {
            "drug_rows": len(final_drugs), "event_rows": len(final_events),
            "interaction_rows": len(final_interactions),
        },
        "changes": {
            "drug_rows": len(drug_changes), "event_rows": len(event_changes),
            "interaction_rows": len(interaction_changes),
            "delta_added": len(added), "delta_removed": len(removed),
        },
        **stats,
        "files": {
            name: {"sha256": hashlib.sha256(payload).hexdigest()}
            for name, payload in artifacts.items()
        },
    }
    artifacts["report.json"] = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    return artifacts


def _write_legacy(output, artifacts):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ddi-curate-", dir=output) as temporary:
        staged = Path(temporary)
        for name, payload in artifacts.items():
            with (staged / name).open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for name in sorted(artifacts):
            os.replace(staged / name, output / name)


def main():
    parser = argparse.ArgumentParser()
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
        publishing = args.release_id is not None or args.expected_parent is not None
        if publishing:
            if args.release_id is None or args.expected_parent is None:
                raise ValueError("--release-id and --expected-parent must be supplied together")
            publication._check_id(args.release_id)
            parent = None if args.expected_parent == "NONE" else args.expected_parent
            if parent is not None:
                publication._check_id(parent)
        artifacts = build_artifacts(args)
        if publishing:
            publication.publish(args.out_dir, args.release_id, parent, artifacts)
        else:
            _write_legacy(args.out_dir, artifacts)
        return 0
    except Exception as error:
        print(f"ddi-curate: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
