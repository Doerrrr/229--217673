#!/usr/bin/env python3
"""Weighted verifier for the DDI curation repair task."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from rdkit import Chem, RDLogger


RDLogger.DisableLog("rdApp.error")
COMMAND = "/usr/local/bin/ddi-curate"


def write_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8", newline="\n")


def make_inputs(root: Path, drugs: str, events: str, interactions: str):
    write_text(root / "drug_list.csv", drugs)
    write_text(root / "DDI_event.csv", events)
    write_text(root / "newddi.csv", interactions)


def run_curator(root: Path, out: Path, timeout=60):
    return subprocess.run(
        [
            COMMAND,
            "--drugs",
            str(root / "drug_list.csv"),
            "--events",
            str(root / "DDI_event.csv"),
            "--interactions",
            str(root / "newddi.csv"),
            "--out-dir",
            str(out),
        ],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def load_report(out: Path):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(smiles):
    molecule = Chem.MolFromSmiles(smiles)
    require(molecule is not None, f"invalid verifier SMILES: {smiles}")
    return Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)


def gate_artifacts():
    """Hard gate: the deployed command must run and create all required artifacts."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "A,CCO\nB,CC\n",
            "0,changes exposure\n",
            "d1,type,d2\nA,0,B\n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, f"command failed: {result.stderr.strip()}")
        for name in ("drugs_clean.csv", "interactions_clean.csv", "report.json"):
            require((out / name).is_file(), f"missing artifact: {name}")
        load_report(out)


# type: normal
# weight: 0.05
# maps_to: declared CSV dialects and required output schema
# failure_effect: normal deduction
# reason: basic parsing is necessary, but the harder domain rules carry more weight.
def check_basic_parsing():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "\n A , CCO \nB,CC\n",
            "\n 00 , changes exposure \n",
            "\nd1, type, d2\n A ,00, B \n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        require(
            (out / "drugs_clean.csv").read_text(encoding="utf-8")
            == "drug_id,canonical_smiles,aliases\nA,CCO,A\nB,CC,B\n",
            "headerless drug dictionary or deterministic CSV output is incorrect",
        )
        require(
            (out / "interactions_clean.csv").read_text(encoding="utf-8")
            == "d1,type,d2\nA,0,B\n",
            "interaction output is incorrect",
        )
        report = load_report(out)
        require(report["input"] == {"drug_rows": 2, "event_rows": 1, "interaction_rows": 1}, "input counts are incorrect")


# type: normal
# weight: 0.05
# maps_to: malformed dictionary rows, physical line numbers and stable reasons
# failure_effect: normal deduction
# reason: rejected source rows must remain auditable without invalidating sound IDs.
def check_malformed_reporting():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "\nA,CCO\n,CC\nB\nC,CC,extra\nD,not-smiles\nE,CC\n",
            "\n0,zero\nbad,bad type\n1,\n2,two,extra\n3,three\n",
            "d1,type,d2\nA,0,E\n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        report = load_report(out)
        require(
            report["input"] == {"drug_rows": 6, "event_rows": 5, "interaction_rows": 1},
            "blank physical lines or row counts were handled incorrectly",
        )
        require(
            report["drugs"]["invalid_rows"]
            == [
                {"line": 3, "drug_id": "", "reason": "malformed"},
                {"line": 4, "drug_id": "B", "reason": "malformed"},
                {"line": 5, "drug_id": "C", "reason": "malformed"},
                {"line": 6, "drug_id": "D", "reason": "invalid_smiles"},
            ],
            "drug invalid-row evidence is incorrect",
        )
        require(report["drugs"]["invalid_only_ids"] == ["B", "C", "D"], "invalid-only drug IDs are incorrect")
        require(report["drugs"]["valid_ids"] == 2, "malformed rows contaminated the valid drug set")
        require(
            report["events"]["invalid_rows"]
            == [
                {"line": 3, "event_type": "bad", "reason": "invalid_type"},
                {"line": 4, "event_type": "1", "reason": "empty_description"},
                {"line": 5, "event_type": "2", "reason": "malformed"},
            ],
            "event invalid-row evidence is incorrect",
        )
        require(report["events"]["valid_types"] == 2, "malformed events contaminated the valid type set")


# type: core
# weight: 0.20
# maps_to: RDKit sanitize/canonicalization, stereochemistry and molecular aliases
# failure_effect: reward <= 0.60
# reason: molecular identity is a central scientific requirement of the curation job.
def check_canonical_aliases():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        stereo_a = "F[C@H](Cl)Br"
        stereo_b = "F[C@@H](Cl)Br"
        make_inputs(
            root,
            f"B,OCC\nA,CCO\n\nS1,{stereo_a}\nS2,{stereo_b}\nBAD,not-smiles\n",
            "0,changes exposure\n",
            "d1,type,d2\nA,0,S1\n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        rows = read_csv(out / "drugs_clean.csv")
        by_id = {row["drug_id"]: row for row in rows}
        require(by_id["A"]["canonical_smiles"] == canonical("CCO"), "equivalent SMILES were not canonicalized")
        require(by_id["A"]["aliases"] == "A;B", "canonical aliases were not merged deterministically")
        require("S1" in by_id and "S2" in by_id, "stereoisomers were incorrectly collapsed")
        require(by_id["S1"]["canonical_smiles"] != by_id["S2"]["canonical_smiles"], "isomeric information was lost")
        report = load_report(out)
        require(report["drugs"]["valid_ids"] == 4, "valid ID count is incorrect")
        require(report["drugs"]["unique_molecules"] == 3, "unique molecule count is incorrect")
        require(report["drugs"]["invalid_only_ids"] == ["BAD"], "invalid-only ID was not reported")
        require(report["drugs"]["invalid_rows"] == [{"line": 6, "drug_id": "BAD", "reason": "invalid_smiles"}], "invalid SMILES evidence is incorrect")


# type: core
# weight: 0.15
# maps_to: repeated IDs, conflicting structures and invalid-only drug IDs
# failure_effect: normal deduction
# reason: conflicting molecular identity must be quarantined before training data is produced.
def check_drug_conflicts():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "A,CCO\nA,CCC\nB,not-smiles\nC,CC\nC,CC\n",
            "0,changes exposure\n",
            "d1,type,d2\nA,0,C\nB,0,C\nD,0,C\nC,0,C\n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        report = load_report(out)
        require(report["drugs"]["conflicting_ids"] == ["A"], "conflicting ID was not quarantined")
        require(report["drugs"]["invalid_only_ids"] == ["B"], "invalid-only ID is wrong")
        require(read_csv(out / "drugs_clean.csv") == [{"drug_id": "C", "canonical_smiles": "CC", "aliases": "C"}], "clean drug table is wrong")
        dropped = report["interactions"]["dropped"]
        require(dropped["conflicting_drug"] == 1, "conflicting-drug drop count is wrong")
        require(dropped["invalid_drug"] == 1, "invalid-drug drop count is wrong")
        require(dropped["missing_drug"] == 1, "missing-drug drop count is wrong")
        require(dropped["self_interaction"] == 1, "self interaction drop count is wrong")


# type: core
# weight: 0.10
# maps_to: event dictionary validation and conflict handling
# failure_effect: normal deduction
# reason: labels with ambiguous meanings cannot be used as training targets.
def check_event_validation():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "A,CCO\nB,CC\n",
            "0,zero\n0,zero\n1,one\n1,one conflict\nbad,bad type\n2,\n3,three\n",
            "d1,type,d2\nA,0,B\nA,1,B\nA,9,B\n",
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        report = load_report(out)
        require(report["events"]["valid_types"] == 2, "valid event type count is wrong")
        require(report["events"]["conflicting_types"] == [1], "conflicting type was not reported")
        require([item["reason"] for item in report["events"]["invalid_rows"]] == ["invalid_type", "empty_description"], "invalid event rows are wrong")
        dropped = report["interactions"]["dropped"]
        require(dropped["conflicting_type"] == 1 and dropped["unknown_type"] == 1, "event rejection categories are wrong")


# type: core
# weight: 0.20
# maps_to: directed DDI semantics, rejection precedence, alias mapping and exact deduplication
# failure_effect: reward <= 0.60
# reason: preserving directed interactions is the primary usable output of the pipeline.
def check_directed_filtering():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        make_inputs(
            root,
            "A,CCO\nA2,OCC\nB,CC\nC,CCC\nD,not-smiles\nQ,CCN\nQ,CCCC\n",
            "0,changes exposure\n1,first meaning\n1,other meaning\n",
            (
                "d1,type,d2\n"
                "A,0,B\nB,0,A\nA2,0,B\n"
                "A,0,A2\nA2,0,A\nC,0,C\nA,0,A\n"
                "Z,0,B\nZ,9,B\nD,0,B\nD,9,B\n"
                "A,9,B\nA,x,B\nZ,x,B\nA,-1,B\nA,0,\nA,٣,B\n"
                "Q,9,B\nQ,1,B\nQ,0,D\nA,1,A\nA,1,B\n"
            ),
        )
        result = run_curator(root, out)
        require(result.returncode == 0, result.stderr)
        require(
            read_csv(out / "interactions_clean.csv")
            == [
                {"d1": "A", "type": "0", "d2": "B"},
                {"d1": "B", "type": "0", "d2": "A"},
            ],
            "directed interactions were collapsed or sorted incorrectly",
        )
        report = load_report(out)
        require(report["input"]["interaction_rows"] == 22, "interaction row count is incorrect")
        require(report["drugs"]["conflicting_ids"] == ["Q"], "conflicting drug fixture did not apply")
        require(report["events"]["conflicting_types"] == [1], "conflicting event fixture did not apply")
        dropped = report["interactions"]["dropped"]
        expected = {
            "malformed": 5,
            "missing_drug": 2,
            "conflicting_drug": 3,
            "invalid_drug": 2,
            "unknown_type": 1,
            "conflicting_type": 2,
            "self_interaction": 2,
            "alias_self_interaction": 2,
            "duplicate": 1,
        }
        require(dropped == expected, f"rejection precedence/counts differ: {dropped}")


# type: normal
# weight: 0.10
# maps_to: deterministic ordering and report hashes
# failure_effect: normal deduction
# reason: reproducible preprocessing is required for traceable model-training inputs.
def check_determinism_and_hashes():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        first = base / "first"
        second = base / "second"
        first.mkdir()
        second.mkdir()
        make_inputs(
            first,
            "B,CC\nA,CCO\nC,CCC\n",
            "10,ten\n2,two\n0,zero\n",
            "d1,type,d2\nB,10,A\nC,2,A\nA,0,B\nB,2,A\n",
        )
        make_inputs(
            second,
            "C,CCC\nA,CCO\nB,CC\n",
            "0,zero\n2,two\n10,ten\n",
            "d1,type,d2\nA,0,B\nB,2,A\nB,10,A\nC,2,A\n",
        )
        out1, out2 = first / "out", second / "out"
        require(run_curator(first, out1).returncode == 0, "first deterministic run failed")
        require(run_curator(second, out2).returncode == 0, "second deterministic run failed")
        for name in ("drugs_clean.csv", "interactions_clean.csv"):
            data = (out1 / name).read_bytes()
            require(data == (out2 / name).read_bytes(), f"{name} depends on input row order")
            require(data.endswith(b"\n") and b"\r" not in data, f"{name} is not LF-terminated")
        require(
            (out1 / "interactions_clean.csv").read_bytes()
            == b"d1,type,d2\nA,0,B\nB,2,A\nB,10,A\nC,2,A\n",
            "interactions are not sorted by ID and numeric event type",
        )
        report_bytes = (out1 / "report.json").read_bytes()
        require(report_bytes == (out2 / "report.json").read_bytes(), "report depends on input row order")
        require(report_bytes.endswith(b"\n") and b"\r" not in report_bytes, "report is not LF-terminated")
        report = load_report(out1)
        require(report["files"]["drugs_clean.csv"]["sha256"] == sha256(out1 / "drugs_clean.csv"), "drug output hash is wrong")
        require(report["files"]["interactions_clean.csv"]["sha256"] == sha256(out1 / "interactions_clean.csv"), "interaction output hash is wrong")


# type: normal
# weight: 0.10
# maps_to: fatal validation and non-clobber reliability contract
# failure_effect: normal deduction
# reason: a failed nightly job must not replace the last known-good curated dataset.
def check_failure_no_clobber():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        out.mkdir()
        sentinels = {
            "drugs_clean.csv": b"old-drugs\n",
            "interactions_clean.csv": b"old-interactions\n",
            "report.json": b"old-report\n",
        }
        for name, data in sentinels.items():
            (out / name).write_bytes(data)
        make_inputs(root, "A,CCO\nB,CC\n", "0,zero\n", "wrong,type,d2\nA,0,B\n")
        result = run_curator(root, out)
        require(result.returncode != 0, "fatal header error returned success")
        require("ERROR:" in result.stderr, "fatal error was not reported on stderr")
        for name, data in sentinels.items():
            require((out / name).read_bytes() == data, f"{name} was clobbered after fatal validation")

        (root / "DDI_event.csv").unlink()
        result = run_curator(root, out)
        require(result.returncode != 0, "missing input returned success")
        for name, data in sentinels.items():
            require((out / name).read_bytes() == data, f"{name} was clobbered after missing input")

        write_text(root / "DDI_event.csv", "0,zero\n")
        write_text(root / "newddi.csv", 'd1,type,d2\n"A,0,B\n')
        result = run_curator(root, out)
        require(result.returncode != 0, "fatal CSV syntax error returned success")
        require("ERROR:" in result.stderr, "fatal CSV syntax error was not reported on stderr")
        for name, data in sentinels.items():
            require((out / name).read_bytes() == data, f"{name} was clobbered after invalid CSV")


# type: boundary
# weight: 0.05
# maps_to: full real-data execution and accounting conservation
# failure_effect: normal deduction
# reason: this checks production-scale integration without overweighting one large fixture.
def check_real_dataset_smoke():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        out = root / "out"
        result = subprocess.run(
            [
                COMMAND,
                "--drugs",
                "/data/drug_list.csv",
                "--events",
                "/data/DDI_event.csv",
                "--interactions",
                "/data/newddi.csv",
                "--out-dir",
                str(out),
            ],
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        require(result.returncode == 0, result.stderr)
        report = load_report(out)
        require(report["input"] == {"drug_rows": 1700, "event_rows": 86, "interaction_rows": 191570}, "real input counts changed")
        require(report["drugs"]["valid_ids"] == 1700 and report["drugs"]["unique_molecules"] == 1700, "real drug counts are wrong")
        require(report["events"]["valid_types"] == 86, "real event count is wrong")
        require(report["interactions"]["kept"] == 191570, "real interaction count is wrong")
        accounted = report["interactions"]["kept"] + sum(report["interactions"]["dropped"].values())
        require(accounted == 191570, "real interaction accounting is not conserved")
        require(report["files"]["drugs_clean.csv"]["sha256"] == sha256(out / "drugs_clean.csv"), "real drug hash mismatch")
        require(report["files"]["interactions_clean.csv"]["sha256"] == sha256(out / "interactions_clean.csv"), "real interaction hash mismatch")
        require(
            sha256(out / "drugs_clean.csv") == "688fa8cf824c06db44209b0a279fd72a9ba9d78f28001585de8c2a7aa933551f",
            "real drug output differs from the pinned full-data result",
        )
        require(
            sha256(out / "interactions_clean.csv") == "9c8e31e6fbc598939d61cfe74215d4b168eeb55a3d8d5b492d2573d51818f541",
            "real interaction output differs from the pinned full-data result",
        )


CHECKS = [
    ("basic_parsing", 0.05, check_basic_parsing),
    ("malformed_reporting", 0.05, check_malformed_reporting),
    ("canonical_aliases", 0.20, check_canonical_aliases),
    ("drug_conflicts", 0.15, check_drug_conflicts),
    ("event_validation", 0.10, check_event_validation),
    ("directed_filtering", 0.20, check_directed_filtering),
    ("determinism_and_hashes", 0.10, check_determinism_and_hashes),
    ("failure_no_clobber", 0.10, check_failure_no_clobber),
    ("real_dataset_smoke", 0.05, check_real_dataset_smoke),
]


def atomic_reward(path: Path, value: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text(f"{value:.6f}".rstrip("0").rstrip("."), encoding="ascii")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reward-file", required=True)
    parser.add_argument("--details-file", required=True)
    args = parser.parse_args()
    reward_file = Path(args.reward_file)
    details_file = Path(args.details_file)
    details = {"hard_gate": False, "checks": []}

    try:
        gate_artifacts()
        details["hard_gate"] = True
    except BaseException as exc:
        details["gate_error"] = f"{type(exc).__name__}: {exc}"
        details_file.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        atomic_reward(reward_file, 0.0)
        print(json.dumps(details))
        return 0

    raw_reward = 0.0
    passed = {}
    for name, weight, function in CHECKS:
        item = {"name": name, "weight": weight, "passed": False}
        try:
            function()
            item["passed"] = True
            raw_reward += weight
        except BaseException as exc:
            item["error"] = f"{type(exc).__name__}: {exc}"
        details["checks"].append(item)
        passed[name] = item["passed"]

    cap = 1.0
    if not passed.get("canonical_aliases", False):
        cap = min(cap, 0.60)
    if not passed.get("directed_filtering", False):
        cap = min(cap, 0.60)
    reward = min(raw_reward, cap, 1.0)
    reward = round(reward + 1e-12, 6)
    details.update({"raw_reward": round(raw_reward, 6), "cap": cap, "reward": reward})
    details_file.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    atomic_reward(reward_file, reward)
    print(json.dumps(details))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
