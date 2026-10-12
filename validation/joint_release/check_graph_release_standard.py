"""Hand-enumerated checks for the independent release-graph standard."""

from graph_release_standard import audit


DRUGS = "drug_id,canonical_smiles,aliases\nA,C,A\nB,CC,B\nC,CCC,C\n"
WITH_PARALLEL = "d1,type,d2\nA,1,B\nB,1,A\nB,2,C\n"
WITHOUT_PARALLEL = "d1,type,d2\nA,1,B\nB,2,C\n"


def main() -> None:
    molecules, bridges = audit(DRUGS, WITH_PARALLEL)
    assert [row["canonical_smiles"] for row in molecules] == ["C", "CC", "CCC"]
    assert [row["cc_count"] for row in molecules] == [1, 1, 1]
    assert [row["bridge_count"] for row in molecules] == [1, 1, 1]
    assert [row["block_count"] for row in molecules] == [2, 2, 2]
    assert [(row["block_min_smiles"], row["block_size"]) for row in molecules] == [
        ("C", 2), ("C", 2), ("CCC", 1),
    ]
    assert bridges == [{"evidence_index": 3, "d1": "B", "type": 2, "d2": "C"}]

    molecules, bridges = audit(DRUGS, WITHOUT_PARALLEL)
    assert [row["bridge_count"] for row in molecules] == [2, 2, 2]
    assert [row["block_count"] for row in molecules] == [3, 3, 3]
    assert [row["block_size"] for row in molecules] == [1, 1, 1]
    assert [row["evidence_index"] for row in bridges] == [1, 2]

    # A different representative for the same molecule changes labels in
    # evidence rows but must not change the canonical molecule partition.
    renamed = DRUGS.replace("B,CC,B", "AA,CC,AA;B")
    renamed_edges = WITH_PARALLEL.replace("B", "AA")
    renamed_molecules, renamed_bridges = audit(renamed, renamed_edges)
    assert renamed_molecules == audit(DRUGS, WITH_PARALLEL)[0]
    assert renamed_bridges[0] == {"evidence_index": 3, "d1": "AA", "type": 2, "d2": "C"}

    isolated, no_bridges = audit(DRUGS, "d1,type,d2\n")
    assert [row["cc_count"] for row in isolated] == [3, 3, 3]
    assert [row["bridge_count"] for row in isolated] == [0, 0, 0]
    assert [row["block_count"] for row in isolated] == [3, 3, 3]
    assert no_bridges == []
    print("HAND_CHECKS_PASS: parallel direction, bridge deletion, alias stability, isolated molecules")


if __name__ == "__main__":
    main()
