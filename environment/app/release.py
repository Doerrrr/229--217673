#!/usr/bin/env python3
"""Legacy draft: repair the release pipeline according to instruction.md."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    for flag in ("drugs", "events", "interactions", "out-dir"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    # This draft assumes IDs are molecular identities, loses directions and
    # publishes everything to train; the candidate assignment stage is absent.
    with open(args.drugs, encoding="utf-8") as handle:
        drugs = list(csv.reader(handle))
    with open(args.interactions, encoding="utf-8") as handle:
        interactions = list(csv.reader(handle))[1:]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "molecules.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["drug_id", "canonical_smiles", "aliases", "cluster_id", "fold"])
        writer.writerows((row[0], row[1], row[0], row[0], "train") for row in drugs)
    with (out / "positives.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "d1", "type", "d2"])
        writer.writerows(("train", min(row[0], row[2]), row[1], max(row[0], row[2])) for row in interactions)
    (out / "unobserved_pairs.csv").write_text("fold,target_index,d1,type,positive_d2,candidate_d2,score,state\n", encoding="utf-8")
    (out / "report.json").write_text(json.dumps({"input": {"drug_rows": len(drugs)}}), encoding="utf-8")


if __name__ == "__main__":
    main()
