"""Independent end-to-end checks for the joined release boundary."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from integration_standard import audit


COMMAND = "/usr/local/bin/ddi-release-audit"
SIX = (
    "bridge_evidence.csv", "drugs_clean.csv", "interaction_delta.csv",
    "interactions_clean.csv", "molecule_audit.csv", "report.json",
)
DRUGS = "A,C\nB,CC\nC,CCC\n"
EVENTS = "1,one\n2,two\n"
INTERACTIONS = "d1,type,d2\nA,1,B\nB,1,A\nB,2,C\n"
DRUG_CHANGES = "seq,op,drug_id,SMILES\n"
EVENT_CHANGES = "seq,op,event_type,description\n"
INTERACTION_CHANGES = "seq,op,d1,type,d2\n"


def write_inputs(root: Path, *, drugs: str = DRUGS, events: str = EVENTS,
                 interactions: str = INTERACTIONS, drug_changes: str = DRUG_CHANGES,
                 event_changes: str = EVENT_CHANGES,
                 interaction_changes: str = INTERACTION_CHANGES) -> None:
    for name, body in (
        ("drug_list.csv", drugs), ("DDI_event.csv", events),
        ("newddi.csv", interactions), ("drug_changes.csv", drug_changes),
        ("event_changes.csv", event_changes),
        ("interaction_changes.csv", interaction_changes),
    ):
        (root / name).write_text(body, encoding="utf-8", newline="\n")


def run(root: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([
        COMMAND,
        "--drugs", str(root / "drug_list.csv"),
        "--events", str(root / "DDI_event.csv"),
        "--interactions", str(root / "newddi.csv"),
        "--drug-changes", str(root / "drug_changes.csv"),
        "--event-changes", str(root / "event_changes.csv"),
        "--interaction-changes", str(root / "interaction_changes.csv"),
        "--out-dir", str(output),
    ], text=True, capture_output=True, timeout=180, check=False)


def current(output: Path) -> tuple[str, Path]:
    raw = (output / "CURRENT").read_bytes()
    assert len(raw) == 65 and raw.endswith(b"\n"), "invalid CURRENT format"
    identity = raw[:-1].decode("ascii")
    assert len(identity) == 64 and all(char in "0123456789abcdef" for char in identity)
    generation = output / "generations" / identity
    assert generation.is_dir(), "CURRENT points to no generation"
    return identity, generation


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def exact_generation(identity: str, generation: Path) -> None:
    manifest_path = generation / "manifest.json"
    assert manifest_path.read_bytes().endswith(b"\n")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest) == {"generation", "files"}
    hashes = {name: hashlib.sha256((generation / name).read_bytes()).hexdigest()
              for name in SIX}
    assert manifest == {"generation": identity, "files": hashes}
    digest = hashlib.sha256(json.dumps(
        hashes, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    assert digest == identity
    assert set(p.name for p in generation.iterdir()) == set(SIX) | {"manifest.json"}


def check_parallel_and_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="ddi-joint-a-") as name:
        root = Path(name)
        write_inputs(root)
        output = root / "out"
        result = run(root, output)
        assert result.returncode == 0, result.stderr
        identity, generation = current(output)
        exact_generation(identity, generation)
        assert (generation / "drugs_clean.csv").read_text(encoding="utf-8") == (
            "drug_id,canonical_smiles,aliases\nA,C,A\nB,CC,B\nC,CCC,C\n"
        )
        assert (generation / "interactions_clean.csv").read_text(encoding="utf-8") == INTERACTIONS
        molecules = csv_rows(generation / "molecule_audit.csv")
        bridges = csv_rows(generation / "bridge_evidence.csv")
        standard_molecules, standard_bridges = audit(
            (generation / "drugs_clean.csv").read_text(encoding="utf-8"),
            (generation / "interactions_clean.csv").read_text(encoding="utf-8"),
        )
        assert molecules == [{key: str(value) for key, value in row.items()}
                             for row in standard_molecules]
        assert bridges == [{key: str(value) for key, value in row.items()}
                           for row in standard_bridges]
        assert [row["bridge_count"] for row in molecules] == ["1", "1", "1"]
        assert bridges == [{"evidence_index": "3", "d1": "B", "type": "2", "d2": "C"}]

        # Add a lower-sorting alias. The representative IDs in clean CSV may
        # change, but canonical molecule partitions cannot.
        write_inputs(root, drug_changes=DRUG_CHANGES + "1,UPSERT,AA,CC\n")
        result = run(root, output)
        assert result.returncode == 0, result.stderr
        renamed_id, renamed = current(output)
        assert renamed_id != identity
        exact_generation(renamed_id, renamed)
        assert csv_rows(renamed / "molecule_audit.csv") == molecules
        assert csv_rows(renamed / "bridge_evidence.csv") == [
            {"evidence_index": "3", "d1": "AA", "type": "2", "d2": "C"}
        ]
        assert (generation / "bridge_evidence.csv").read_bytes() == (
            b"evidence_index,d1,type,d2\n3,B,2,C\n"
        ), "earlier immutable generation changed"


def check_replay_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="ddi-joint-b-") as name:
        root = Path(name)
        write_inputs(root, interaction_changes=INTERACTION_CHANGES + "1,DELETE,B,1,A\n")
        output = root / "out"
        result = run(root, output)
        assert result.returncode == 0, result.stderr
        identity, generation = current(output)
        exact_generation(identity, generation)
        assert (generation / "interactions_clean.csv").read_text(encoding="utf-8") == (
            "d1,type,d2\nA,1,B\nB,2,C\n"
        )
        assert csv_rows(generation / "bridge_evidence.csv") == [
            {"evidence_index": "1", "d1": "A", "type": "1", "d2": "B"},
            {"evidence_index": "2", "d1": "B", "type": "2", "d2": "C"},
        ]
        assert [row["block_size"] for row in csv_rows(generation / "molecule_audit.csv")] == [
            "1", "1", "1",
        ]

        write_inputs(root, event_changes=EVENT_CHANGES + "1,DELETE,2,\n")
        result = run(root, output)
        assert result.returncode == 0, result.stderr
        _, without_event = current(output)
        assert (without_event / "interactions_clean.csv").read_text(encoding="utf-8") == (
            "d1,type,d2\nA,1,B\nB,1,A\n"
        )
        assert csv_rows(without_event / "bridge_evidence.csv") == []
        assert [row["cc_size"] for row in csv_rows(without_event / "molecule_audit.csv")] == [
            "2", "2", "1",
        ]


def check_deterministic_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="ddi-joint-c-") as name:
        root = Path(name)
        write_inputs(root)
        output = root / "nested" / "out"
        assert not output.exists()
        first = run(root, output)
        assert first.returncode == 0, first.stderr
        identity, generation = current(output)
        exact_generation(identity, generation)
        before = {path.name: path.read_bytes() for path in generation.iterdir()}
        second = run(root, output)
        assert second.returncode == 0, second.stderr
        assert current(output)[0] == identity
        assert {path.name: path.read_bytes() for path in generation.iterdir()} == before
        assert len([p for p in (output / "generations").iterdir() if p.is_dir() and not p.name.startswith(".stage-")]) == 1


def check_fatal_no_clobber() -> None:
    with tempfile.TemporaryDirectory(prefix="ddi-joint-d-") as name:
        root = Path(name)
        write_inputs(root)
        output = root / "out"
        first = run(root, output)
        assert first.returncode == 0, first.stderr
        identity, generation = current(output)
        before = {path.name: path.read_bytes() for path in generation.iterdir()}
        marker = (output / "CURRENT").read_bytes()
        write_inputs(root, drug_changes=(
            DRUG_CHANGES + "1,UPSERT,A,CCO\n1,DELETE,A,\n"
        ))
        failed = run(root, output)
        assert failed.returncode != 0 and failed.stderr.strip(), "fatal change was accepted"
        assert (output / "CURRENT").read_bytes() == marker
        assert current(output)[0] == identity
        assert {path.name: path.read_bytes() for path in generation.iterdir()} == before


CHECKS = [
    ("parallel_alias_bridge", check_parallel_and_alias),
    ("replay_cross_file_graph", check_replay_changes),
    ("deterministic_generation", check_deterministic_manifest),
    ("fatal_input_preserves_release", check_fatal_no_clobber),
]
