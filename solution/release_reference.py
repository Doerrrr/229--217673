#!/usr/bin/env python3
"""Reference DDI release publisher; the candidate receives a different starter."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


CONTENT_NAMES = (
    "bridge_evidence.csv", "drugs_clean.csv", "interaction_delta.csv",
    "interactions_clean.csv", "molecule_audit.csv", "report.json",
)


def read_rows(path: Path, fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != fields:
            raise ValueError(f"wrong header in {path.name}")
        result = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in result):
        raise ValueError(f"malformed curated CSV: {path.name}")
    return result


def partitions(adjacency: list[list[tuple[int, int]]], blocked: set[int]) -> tuple[list[int], list[int], int]:
    n = len(adjacency)
    minimum = [-1] * n
    size = [0] * n
    count = 0
    for start in range(n):
        if minimum[start] != -1:
            continue
        stack = [start]
        members = []
        minimum[start] = start
        while stack:
            u = stack.pop()
            members.append(u)
            for v, key in adjacency[u]:
                if key not in blocked and minimum[v] == -1:
                    minimum[v] = start
                    stack.append(v)
        for u in members:
            size[u] = len(members)
        count += 1
    return minimum, size, count


def bridge_keys(adjacency: list[list[tuple[int, int]]]) -> set[int]:
    n = len(adjacency)
    discovery = [-1] * n
    low = [0] * n
    parent = [-1] * n
    parent_key = [-1] * n
    cursor = [0] * n
    timer = 0
    bridges: set[int] = set()
    for start in range(n):
        if discovery[start] != -1:
            continue
        discovery[start] = low[start] = timer
        timer += 1
        stack = [start]
        while stack:
            u = stack[-1]
            if cursor[u] == len(adjacency[u]):
                stack.pop()
                if parent[u] != -1:
                    p = parent[u]
                    if low[u] > discovery[p]:
                        bridges.add(parent_key[u])
                    low[p] = min(low[p], low[u])
                continue
            v, key = adjacency[u][cursor[u]]
            cursor[u] += 1
            if key == parent_key[u]:
                continue
            if discovery[v] == -1:
                parent[v], parent_key[v] = u, key
                discovery[v] = low[v] = timer
                timer += 1
                stack.append(v)
            else:
                low[u] = min(low[u], discovery[v])
    return bridges


def write_audits(stage: Path) -> None:
    drugs = read_rows(stage / "drugs_clean.csv", ["drug_id", "canonical_smiles", "aliases"])
    interactions = read_rows(stage / "interactions_clean.csv", ["d1", "type", "d2"])
    id_to_smiles = {row["drug_id"]: row["canonical_smiles"] for row in drugs}
    smiles = sorted(id_to_smiles.values())
    if len(smiles) != len(drugs) or len(set(smiles)) != len(smiles):
        raise ValueError("non-unique curated molecule")
    vertex = {value: i for i, value in enumerate(smiles)}
    adjacency: list[list[tuple[int, int]]] = [[] for _ in smiles]
    for key, row in enumerate(interactions, start=1):
        u = vertex[id_to_smiles[row["d1"]]]
        v = vertex[id_to_smiles[row["d2"]]]
        adjacency[u].append((v, key))
        adjacency[v].append((u, key))
    cc_min, cc_size, cc_count = partitions(adjacency, set())
    bridges = bridge_keys(adjacency)
    block_min, block_size, block_count = partitions(adjacency, bridges)

    with (stage / "molecule_audit.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("canonical_smiles", "cc_min_smiles", "cc_size", "block_min_smiles",
                         "block_size", "cc_count", "bridge_count", "block_count"))
        for i, canonical in enumerate(smiles):
            writer.writerow((canonical, smiles[cc_min[i]], cc_size[i], smiles[block_min[i]],
                             block_size[i], cc_count, len(bridges), block_count))
    with (stage / "bridge_evidence.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("evidence_index", "d1", "type", "d2"))
        for key, row in enumerate(interactions, start=1):
            if key in bridges:
                writer.writerow((key, row["d1"], int(row["type"]), row["d2"]))


def publish(inputs: dict[str, str], output: Path) -> str:
    generations = output / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=generations))
    try:
        command = ["/usr/local/bin/ddi-curate"]
        for name in ("drugs", "events", "interactions", "drug-changes",
                     "event-changes", "interaction-changes"):
            command.extend(("--" + name, inputs[name]))
        command.extend(("--out-dir", str(stage)))
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "curation failed")
        write_audits(stage)
        file_hashes = {
            name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
            for name in CONTENT_NAMES
        }
        identity = hashlib.sha256(json.dumps(
            file_hashes, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        manifest = {"generation": identity, "files": file_hashes}
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        final = generations / identity
        if final.exists():
            if not final.is_dir() or any(
                not (final / name).is_file() or
                hashlib.sha256((final / name).read_bytes()).hexdigest() != file_hashes[name]
                for name in CONTENT_NAMES
            ) or (final / "manifest.json").read_bytes() != (stage / "manifest.json").read_bytes():
                raise ValueError("existing generation content conflicts with identity")
        else:
            os.rename(stage, final)
        marker = output / (".CURRENT-" + uuid.uuid4().hex)
        try:
            marker.write_text(identity + "\n", encoding="ascii", newline="\n")
            os.replace(marker, output / "CURRENT")
        finally:
            marker.unlink(missing_ok=True)
        return identity
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser()
    names = ("drugs", "events", "interactions", "drug-changes", "event-changes",
             "interaction-changes")
    for name in names:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    try:
        inputs = {name: getattr(args, name.replace("-", "_")) for name in names}
        publish(inputs, Path(args.out_dir))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
