#!/usr/bin/env python3
"""Legacy DDI export cleaner. This implementation predates the current export."""

import argparse
import csv
import json
from pathlib import Path

from rdkit import Chem


def load_drugs(path: Path):
    drugs = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            molecule = Chem.MolFromSmiles(row["SMILES"])
            if molecule is None:
                continue
            drugs[row["drug_id"]] = Chem.MolToSmiles(
                molecule, canonical=False, isomericSmiles=False
            )
    return drugs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drugs", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--interactions", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    drugs = load_drugs(Path(args.drugs))
    pairs = set()
    with Path(args.interactions).open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["d1"] not in drugs or row["d2"] not in drugs:
                continue
            d1, d2 = sorted((row["d1"], row["d2"]))
            pairs.add((d1, row["type"], d2))

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps({"drug_count": len(drugs), "interaction_count": len(pairs)}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
