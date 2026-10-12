"""Compare production-style Tarjan audit with deletion/BFS on small cases."""

import csv
from pathlib import Path
import random
import tempfile

from graph_release_standard import audit
from runtime_task_r2.solution.release_reference import write_audits


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check(drugs: str, interactions: str) -> int:
    expected_molecules, expected_bridges = audit(drugs, interactions)
    with tempfile.TemporaryDirectory(prefix="ddi-joint-standard-") as name:
        root = Path(name)
        (root / "drugs_clean.csv").write_text(drugs, encoding="utf-8", newline="\n")
        (root / "interactions_clean.csv").write_text(interactions, encoding="utf-8", newline="\n")
        write_audits(root)
        actual_molecules = rows(root / "molecule_audit.csv")
        actual_bridges = rows(root / "bridge_evidence.csv")
    assert actual_molecules == [
        {key: str(value) for key, value in row.items()} for row in expected_molecules
    ], (actual_molecules, expected_molecules)
    assert actual_bridges == [
        {key: str(value) for key, value in row.items()} for row in expected_bridges
    ], (actual_bridges, expected_bridges)
    return len(actual_bridges)


def main() -> None:
    rng = random.Random(20261013)
    bridge_rows = 0
    for seed in range(500):
        n = rng.randrange(1, 11)
        drugs = "drug_id,canonical_smiles,aliases\n" + "".join(
            f"D{i},{'C' * (i + 1)},D{i}\n" for i in range(n)
        )
        edges = rng.randrange(0, 26)
        interactions = "d1,type,d2\n" + "".join(
            f"D{rng.randrange(n)},{i},D{rng.randrange(n)}\n" for i in range(edges)
        )
        bridge_rows += check(drugs, interactions)
    print(f"REFERENCE_GRAPH_PASS: 500 small graphs; bridge rows={bridge_rows}")


if __name__ == "__main__":
    main()
