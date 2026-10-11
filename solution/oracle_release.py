#!/usr/bin/env python3
"""Reference implementation for leakage-safe DDI dataset release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import math
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path

from rdkit import Chem, RDLogger, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from rdkit.Chem.Scaffolds import MurckoScaffold


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
                if not row or (len(row) == 1 and not row[0].strip()):
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


FOLDS = ("train", "validation", "test")
OUTPUTS = ("molecules.csv", "positives.csv", "unobserved_pairs.csv", "report.json")


def chemistry(drugs):
    """Union scaffold and similarity edges, not two independent partitions."""
    molecules = [Chem.MolFromSmiles(row[1]) for row in drugs]
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=2, fpSize=2048, includeChirality=True
    )
    fps = [generator.GetFingerprint(mol) for mol in molecules]
    keys = [
        MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True) or row[1]
        for mol, row in zip(molecules, drugs)
    ]
    parent = list(range(len(drugs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    first = {}
    for i, key in enumerate(keys):
        if key in first:
            union(i, first[key])
        else:
            first[key] = i
    for i, fp in enumerate(fps):
        for j, similarity in enumerate(DataStructs.BulkTanimotoSimilarity(fp, fps[:i])):
            if similarity >= 0.80:
                union(i, j)
    groups = defaultdict(list)
    for i in range(len(drugs)):
        groups[find(i)].append(i)
    metadata = {}
    for members in groups.values():
        digest = sha256(min(drugs[i][1] for i in members).encode("utf-8"))
        bucket = int(digest, 16) % 20
        fold = "train" if bucket < 14 else "validation" if bucket < 17 else "test"
        for i in members:
            metadata[drugs[i][0]] = (digest, fold, fps[i])
    return metadata


def select_targets(positives):
    by_anchor = defaultdict(list)
    for d1, event_type, d2 in positives:
        by_anchor[d1].append((d1, event_type, d2))
    for rows in by_anchor.values():
        rows.sort(key=lambda row: (row[1], row[2]))
    targets = []
    offset = 0
    anchors = sorted(by_anchor)
    while len(targets) < 48:
        batch = [by_anchor[d1][offset] for d1 in anchors if offset < len(by_anchor[d1])]
        if not batch:
            break
        targets.extend(batch[:48 - len(targets)])
        offset += 1
    return targets


def candidate_edges(targets, fold, metadata, interactions):
    known = {frozenset((d1, d2)) for d1, _, d2 in interactions}
    edges = []
    candidates = sorted(key for key, value in metadata.items() if value[1] == fold)
    for d1, _, positive_d2 in targets:
        ranked = []
        for candidate in candidates:
            if candidate in (d1, positive_d2):
                continue
            if metadata[candidate][0] == metadata[positive_d2][0]:
                continue
            if frozenset((d1, candidate)) in known:
                continue
            similarity = DataStructs.TanimotoSimilarity(
                metadata[positive_d2][2], metadata[candidate][2]
            )
            if similarity >= 0.15:
                ranked.append((candidate, math.floor(10000 * similarity + 0.5)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        edges.append(ranked[:8])
    return edges


def exact_matching(options):
    """Min-cost flow with an exact integer encoding of all three objectives.

    One unit per target also permits an unmatched edge. Cardinality dominates
    every possible score difference; score dominates the entire lex vector.
    Successive shortest residual paths can reassign previously matched targets.
    """
    count = len(options)
    ids = sorted({candidate for edges in options for candidate, _ in edges})
    rank = {candidate: i for i, candidate in enumerate(ids)}
    base = len(ids) + 1
    lex_scale = base ** count
    unmatched_penalty = (count * 10000 + 1) * lex_scale
    source = 0
    candidate_start = 1 + count
    sink = candidate_start + len(ids)
    graph = [[] for _ in range(sink + 1)]

    def edge(u, v, cost):
        forward = [v, len(graph[v]), 1, cost]
        backward = [u, len(graph[u]), 0, -cost]
        graph[u].append(forward)
        graph[v].append(backward)
        return forward

    refs = []
    for i, choices in enumerate(options):
        node = 1 + i
        edge(source, node, 0)
        positional = base ** (count - i - 1)
        edge(node, sink, unmatched_penalty + len(ids) * positional)
        refs.append([
            (candidate, score, edge(
                node, candidate_start + rank[candidate],
                -score * lex_scale + rank[candidate] * positional
            ))
            for candidate, score in choices
        ])
    for j in range(len(ids)):
        edge(candidate_start + j, sink, 0)

    for _ in range(count):
        distances = [None] * len(graph)
        distances[source] = 0
        previous = [None] * len(graph)
        pending = deque([source])
        queued = {source}
        while pending:
            u = pending.popleft()
            queued.remove(u)
            for index, item in enumerate(graph[u]):
                v, _, capacity, cost = item
                if capacity and (distances[v] is None or distances[u] + cost < distances[v]):
                    distances[v] = distances[u] + cost
                    previous[v] = (u, index)
                    if v not in queued:
                        pending.append(v)
                        queued.add(v)
        if previous[sink] is None:
            raise CuratorError("internal matching failure")
        v = sink
        while v != source:
            u, index = previous[v]
            item = graph[u][index]
            item[2] -= 1
            graph[v][item[1]][2] += 1
            v = u
    return [
        next(((candidate, score) for candidate, score, item in choices if item[2] == 0), None)
        for choices in refs
    ]


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def release(args):
    paths = [Path(args.drugs), Path(args.events), Path(args.interactions)]
    for path in paths:
        if not path.is_file():
            raise CuratorError(f"missing input file: {path}")
    # Parse every CSV before doing any publication, including Unicode errors.
    drug_records = list(nonblank_rows(paths[0]))
    event_records = list(nonblank_rows(paths[1]))
    interaction_records = read_interactions(paths[2])
    drug_rows, all_ids, conflicts, invalid_ids, aliases, drugs, drug_report = load_drugs(drug_records)
    event_rows, known_types, type_conflicts, _, event_report = load_events(event_records)
    interaction_rows, interactions, interaction_report = load_interactions(
        interaction_records, all_ids, conflicts, invalid_ids, aliases, known_types, type_conflicts
    )
    metadata = chemistry(drugs)
    molecule_rows = [(*row, *metadata[row[0]][:2]) for row in drugs]
    by_fold = {fold: [] for fold in FOLDS}
    cross_fold = 0
    for triple in interactions:
        left, right = metadata[triple[0]][1], metadata[triple[2]][1]
        if left == right:
            by_fold[left].append(triple)
        else:
            cross_fold += 1
    positive_rows = [(fold, *triple) for fold in FOLDS for triple in by_fold[fold]]
    unobserved = []
    matching_report = {}
    for fold in FOLDS[1:]:
        targets = select_targets(by_fold[fold])
        options = candidate_edges(targets, fold, metadata, interactions)
        assigned = exact_matching(options)
        for index, (target, match) in enumerate(zip(targets, assigned), 1):
            candidate, score = match if match else ("", 0)
            unobserved.append((fold, index, *target, candidate, score, "MATCHED" if match else "UNMATCHED"))
        matched = sum(match is not None for match in assigned)
        matching_report[fold] = {"targets": len(targets), "matched": matched, "unmatched": len(targets) - matched}
    rendered = {
        "molecules.csv": render_csv(("drug_id", "canonical_smiles", "aliases", "cluster_id", "fold"), molecule_rows),
        "positives.csv": render_csv(("fold", "d1", "type", "d2"), positive_rows),
        "unobserved_pairs.csv": render_csv(
            ("fold", "target_index", "d1", "type", "positive_d2", "candidate_d2", "score", "state"),
            unobserved
        ),
    }
    report = {
        "input": {"drug_rows": drug_rows, "event_rows": event_rows, "interaction_rows": interaction_rows},
        "drugs": drug_report,
        "events": event_report,
        "interactions": interaction_report,
        "release": {
            "clusters": len({item[0] for item in metadata.values()}),
            "cross_fold_withheld": cross_fold,
            "folds": {
                fold: {
                    "molecules": sum(item[1] == fold for item in metadata.values()),
                    "positives": len(by_fold[fold])
                } for fold in FOLDS
            },
            "matching": matching_report,
        },
        "files": {name: {"sha256": sha256(data)} for name, data in rendered.items()},
    }
    rendered["report.json"] = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    # All fatal input errors have already been detected; no old output is touched earlier.
    output = Path(args.out_dir)
    for name, data in rendered.items():
        atomic_write(output / name, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("drugs", "events", "interactions", "out-dir"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    try:
        release(args)
    except (CuratorError, OSError, UnicodeError, ValueError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
