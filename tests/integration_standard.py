"""Independent, deliberately slow standard for small DDI release graphs.

This is an author-side test oracle. It reads *curated* rows, assigns one
physical edge key per directed row, and decides bridges by deleting each key.
It does not import the candidate C++ engine or a production bridge algorithm.
"""

from __future__ import annotations

import csv
from io import StringIO


def _rows(source: str, fields: list[str]) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(source, newline=""))
    if reader.fieldnames != fields:
        raise ValueError(f"expected {fields}, got {reader.fieldnames}")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("malformed curated CSV")
    return rows


def _partition(n: int, edges: list[tuple[int, int]], excluded: set[int]) -> tuple[list[int], list[int], int]:
    adjacency = [[] for _ in range(n)]
    for index, (u, v) in enumerate(edges, start=1):
        if index not in excluded:
            adjacency[u].append(v)
            adjacency[v].append(u)
    group_min = [-1] * n
    group_size = [0] * n
    count = 0
    for start in range(n):
        if group_min[start] != -1:
            continue
        stack = [start]
        members = []
        group_min[start] = start
        while stack:
            vertex = stack.pop()
            members.append(vertex)
            for neighbor in adjacency[vertex]:
                if group_min[neighbor] == -1:
                    group_min[neighbor] = start
                    stack.append(neighbor)
        for vertex in members:
            group_size[vertex] = len(members)
        count += 1
    return group_min, group_size, count


def audit(drugs_csv: str, interactions_csv: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    drugs = _rows(drugs_csv, ["drug_id", "canonical_smiles", "aliases"])
    interactions = _rows(interactions_csv, ["d1", "type", "d2"])
    by_id = {row["drug_id"]: row["canonical_smiles"] for row in drugs}
    if len(by_id) != len(drugs):
        raise ValueError("duplicate representative")
    smiles = sorted(set(by_id.values()))
    if len(smiles) != len(drugs):
        raise ValueError("curated molecule rows must be unique")
    vertex = {value: index for index, value in enumerate(smiles)}
    edges = []
    for row in interactions:
        if row["d1"] not in by_id or row["d2"] not in by_id:
            raise ValueError("unknown curated representative")
        if not row["type"].isascii() or not row["type"].isdecimal():
            raise ValueError("non-numeric curated event type")
        edges.append((vertex[by_id[row["d1"]]], vertex[by_id[row["d2"]]]))

    cc_min, cc_size, cc_count = _partition(len(smiles), edges, set())
    bridge_keys = set()
    for key, (u, v) in enumerate(edges, start=1):
        removed_cc, _, _ = _partition(len(smiles), edges, {key})
        if removed_cc[u] != removed_cc[v]:
            bridge_keys.add(key)
    block_min, block_size, block_count = _partition(len(smiles), edges, bridge_keys)
    molecules = []
    for index, canonical in enumerate(smiles):
        molecules.append({
            "canonical_smiles": canonical,
            "cc_min_smiles": smiles[cc_min[index]],
            "cc_size": cc_size[index],
            "block_min_smiles": smiles[block_min[index]],
            "block_size": block_size[index],
            "cc_count": cc_count,
            "bridge_count": len(bridge_keys),
            "block_count": block_count,
        })
    bridges = [
        {"evidence_index": index, "d1": row["d1"],
         "type": int(row["type"]), "d2": row["d2"]}
        for index, row in enumerate(interactions, start=1)
        if index in bridge_keys
    ]
    return molecules, bridges
