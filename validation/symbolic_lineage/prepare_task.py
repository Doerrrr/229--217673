"""Prepare inputs/contract/checker copies, never compute production answers."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil

from certificate_check import canonical, parse_input
from fixtures import CHECKS, serial_fixture

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
TASK = ROOT / "runtime_task_v01"


def main():
    data_folder = TASK / "environment/data"
    data_folder.mkdir(parents=True, exist_ok=True)
    source = REPO / "environment/data/newddi.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        observations = list(zip(range(2, 12), (next(reader) for _ in range(10))))
    # Source labels and activation weights are task parameters, not clinical
    # claims or provenance assertions about the original DDI observations.
    edges = [{"edge_id": f"observation_{i:02d}", "d1": row["d1"], "d2": row["d2"],
              "type": int(row["type"]), "source_id": f"evidence_{i % 4}"}
             for i, (_, row) in enumerate(observations)]
    sample = {"version": 1, "nodes": sorted({e[key] for e in edges for key in ("d1", "d2")}),
              "sources": [{"source_id": f"evidence_{i}", "numerator": i + 1, "denominator": 6}
                          for i in range(4)], "edges": edges,
              "queries": [{"query_id": "release_query", "start": edges[0]["d1"],
                           "end": edges[0]["d2"], "event_types": [], "condition": [],
                           "ranks": ["0", "1", "100"]}]}
    parse_input(canonical(sample))
    (data_folder / "evidence_graph.json").write_bytes(canonical(sample))
    (data_folder / "stress_graph.json").write_bytes(canonical(serial_fixture(48)))
    receipt = {"source_file": "environment/data/newddi.csv",
               "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "source_csv_record_lines": [line for line, _ in observations],
               "labels_and_probabilities": "task-defined activation parameters, not clinical probabilities",
               "original_assets_modified": False, "production_answer_computed": False}
    (ROOT / "input_receipt.json").write_bytes(canonical(receipt))
    standard = (ROOT / "standard.md").read_text(encoding="utf-8")
    body = standard.split("## Input and command", 1)[1].split("## Precommitment", 1)[0]
    prefix = ("# DDI-008: shared-evidence lineage release\n\n"
              "Repair ddi-lineage to analyze directed observation paths with shared evidence sources.\n"
              "A source can activate multiple observations, so observations need not be independent.\n"
              "Publish compact logical support certificates and exact research-data reliability metrics.\n"
              "This is not a clinical-risk predictor: a graph path is not a proven biological DDI,\n"
              "and the given activation weights are not adverse-event probabilities.\n\n"
              "## Input and command")
    suffix = ("\n## Runtime and deliverable\n\n"
              "The environment provides Python 3.11 standard library, 2 CPUs and 4 GiB RAM.\n"
              "Edit only environment/app/*.py (nested Python helpers are allowed). Do not change\n"
              "the Dockerfile, launcher, task inputs or contract. No additional packages are required.\n"
              "You may choose any internal algorithm that satisfies the public certificate rules.\n"
              "A fresh output directory must work. Each valid command is allowed 120 seconds;\n"
              "an invalid-input/CLI command is allowed 10 seconds for diagnosis.\n"
              "Each output file and captured log may use at most 32 MiB; this exceeds the\n"
              "maximum expected certificate size under the published bounds.\n"
              "The overall coding budget is 3600 seconds, excluding separately recorded environment\n"
              "setup failures. Do not modify host Docker/WSL services.\n\n"
              "Read start_here.md, complete answer_notes.md, then run\n"
              "`python pack_answer.py --out answer.zip`. Return the first frozen source ZIP and\n"
              "actual model/version, elapsed time, tests run and omissions. Outputs alone are not\n"
              "a code answer. Do not access unrelated projects, hidden evaluators or prior answers.\n\n"
              "## Behavior checks\n\n"
              "Twenty independently scored checks each carry 0.05, with no score cap.\n"
              "Proof, support-family and probability checks verify their corresponding behavior\n"
              "independently; an incorrect unrelated report metric does not erase proof credit.\n"
              "Structural validity of the relevant supplied BDD is still required.\n\n")
    lines = [f"- {name} ({section}): {weight:.2f}" for name, section, weight in CHECKS]
    (TASK / "instruction.md").write_text(prefix + body + suffix + "\n".join(lines) + "\n",
                                         encoding="utf-8", newline="\n")
    for name in ("certificate_check.py", "fixtures.py"):
        shutil.copyfile(ROOT / name, TASK / "tests" / name)
    print(json.dumps({"status": "PREPARED", "checks": len(CHECKS), "computed_answer": False}))


if __name__ == "__main__":
    main()
