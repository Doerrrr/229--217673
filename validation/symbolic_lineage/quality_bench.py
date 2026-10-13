"""Pre-freeze quality controls, not a general candidate/reference solution.

Small graphs are checked by exhaustive BFS (<=8 sources). Large controls use
only hand-derived serial-family identities. This file is operator-only and is
not imported by the runtime grader or included in the candidate environment.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from math import prod
from pathlib import Path
import random
import time

from certificate_check import Diagram, canonical, check, check_part, fraction_object, parse_input
from fixtures import CHECKS, edge, graph, query, scored_cases, serial_fixture
from hand_checks import export, hand_small, rejected


def serial_control(raw):
    data = parse_input(canonical(raw))
    names = data["nodes"]
    assert all(name == f"DBL{i:03d}" for i, name in enumerate(names))
    k = len(names) - 1
    variables = [item["source_id"] for item in data["sources"]]
    assert variables == [f"e{i:02d}{letter}" for i in range(k) for letter in "ab"]
    manager = Diagram(variables)
    index = {name: i for i, name in enumerate(variables)}
    weights = {item["source_id"]: Fraction(item["numerator"], item["denominator"])
               for item in data["sources"]}
    grouped = [[] for _ in range(k)]
    for observation in data["edges"]:
        start = names.index(observation["d1"])
        assert observation["d2"] == names[start + 1]
        assert observation["source_id"] in (f"e{start:02d}a", f"e{start:02d}b")
        grouped[start].append(observation)
    certificates, results = [], []
    for q in data["queries"]:
        fixed = {item["source_id"]: item["value"] for item in q["condition"]}
        free = [name for name in variables if name not in fixed]
        selected = set(q["event_types"])
        guards, choices, probabilities, always = [], [], [], []
        for observations in grouped:
            relevant = [item for item in observations if not selected or item["type"] in selected]
            is_always = any(fixed.get(item["source_id"]) is True for item in relevant)
            options = sorted({item["source_id"] for item in relevant if item["source_id"] not in fixed})
            root = int(is_always)
            for name in options:
                root = manager.combine("or", root, manager.variable(index[name]))
            guards.append(root)
            always.append(is_always)
            choices.append([] if is_always else options)
            probabilities.append(Fraction(1) if is_always else 1 - prod((1 - weights[name] for name in options), start=Fraction(1)))
        start, end = names.index(q["start"]), names.index(q["end"])
        prefixes = [0] * (k + 1)
        prefixes[start] = 1
        for v in range(start + 1, k + 1):
            prefixes[v] = manager.combine("and", prefixes[v - 1], guards[v - 1])
        layers = [[prefixes[v] if v >= start and v - start <= layer else 0
                   for v in range(k + 1)] for layer in range(k + 1)]
        reachable = end >= start and all(always[i] or choices[i] for i in range(start, end))
        route = range(start, end) if reachable else ()
        required = [i for i in route if not always[i]]
        used = {name for i in required for name in choices[i]}
        family_count = prod(len(choices[i]) for i in required) if reachable else 0
        assignment_count = (1 << (len(free) - len(used))) * prod((1 << len(choices[i])) - 1 for i in required) if reachable else 0
        minimal = int(reachable)
        for i in required:
            exact_one = 0
            for selected_name in choices[i]:
                term = 1
                for name in choices[i]:
                    literal = manager.variable(index[name])
                    term = manager.combine("and", term, literal if name == selected_name else manager.negate(literal))
                exact_one = manager.combine("or", exact_one, term)
            minimal = manager.combine("and", minimal, exact_one)
        for name in variables:
            if name not in used:
                minimal = manager.combine("and", minimal, manager.negate(manager.variable(index[name])))

        def ranked(rank):
            if rank >= family_count:
                return None
            support = []
            for offset, stage in enumerate(required):
                suffix = prod(len(choices[j]) for j in required[offset + 1:])
                choice, rank = divmod(rank, suffix)
                support.append(choices[stage][choice])
            return support

        possible = all(weights[name] != (0 if value else 1) for name, value in fixed.items())
        probability = prod((probabilities[i] for i in route), start=Fraction(1)) if reachable else Fraction(0)
        sensitivities = {name: Fraction(0) for name in free}
        for stage in required:
            other_stages = prod((probabilities[i] for i in route if i != stage), start=Fraction(1))
            for name in choices[stage]:
                sensitivities[name] = other_stages * prod((1 - weights[other] for other in choices[stage] if other != name), start=Fraction(1))
        certificates.append({"query_id": q["query_id"], "layers": layers,
                             "root": prefixes[end], "minimal_root": minimal})
        results.append({
            "query_id": q["query_id"], "support_count": str(assignment_count),
            "minimal_support_count": str(family_count),
            "min_size": len(required) if reachable else None, "max_size": len(required) if reachable else None,
            "ranked_supports": [{"rank": rank, "sources": ranked(int(rank))} for rank in q["ranks"]],
            "critical_sources": sorted(name for i in required if len(choices[i]) == 1 for name in choices[i]),
            "probability_state": "DEFINED" if possible else "UNDEFINED",
            "probability": fraction_object(probability) if possible else None,
            "sensitivities": {name: fraction_object(sensitivities[name]) if possible else None for name in free},
        })
    proof = canonical(export(manager, certificates))
    report = canonical({"version": 1, "proof_sha256": hashlib.sha256(proof).hexdigest(), "results": results})
    return canonical(data), proof, report


def shared_guard_control(raw):
    data = parse_input(canonical(raw))
    k = len(data["nodes"]) - 1
    variables = [item["source_id"] for item in data["sources"]]
    assert variables == ["a"] + [f"b{i:02d}" for i in range(k)]
    assert len(data["queries"]) == 1 and not data["queries"][0]["condition"]
    assert all(item["numerator"] == 1 and item["denominator"] == 2 for item in data["sources"])
    manager = Diagram(variables)
    a = manager.variable(0)
    prefix, conjunction = [1], 1
    all_false, all_true = manager.negate(a), a
    for i in range(k):
        b = manager.variable(i + 1)
        conjunction = manager.combine("and", conjunction, b)
        prefix.append(manager.combine("or", a, conjunction))
        all_false = manager.combine("and", all_false, b)
        all_true = manager.combine("and", all_true, manager.negate(b))
    minimal = manager.combine("or", all_false, all_true)
    q = data["queries"][0]
    certificate = {"query_id": q["query_id"], "layers": [
        [prefix[v] if v <= layer else 0 for v in range(k + 1)] for layer in range(k + 1)],
        "root": prefix[-1], "minimal_root": minimal}
    supports = [["a"], variables[1:]]
    result = {
        "query_id": q["query_id"], "support_count": str(2**k + 1), "minimal_support_count": "2",
        "min_size": 1, "max_size": k,
        "ranked_supports": [{"rank": rank, "sources": supports[int(rank)] if int(rank) < 2 else None} for rank in q["ranks"]],
        "critical_sources": [], "probability_state": "DEFINED",
        "probability": fraction_object(Fraction(1, 2) + Fraction(1, 2**(k + 1))),
        "sensitivities": {name: fraction_object(1 - Fraction(1, 2**k) if name == "a" else Fraction(1, 2**k)) for name in variables},
    }
    proof = canonical(export(manager, [certificate]))
    report = canonical({"version": 1, "proof_sha256": hashlib.sha256(proof).hexdigest(), "results": [result]})
    return canonical(data), proof, report


def control(raw):
    if len(raw["sources"]) <= 8:
        return hand_small(raw)
    if raw["nodes"][0].startswith("DBL"):
        return serial_control(raw)
    return shared_guard_control(raw)


def boolean_primitive_checks():
    randomizer = random.Random(4317)
    manager = Diagram(["a", "b", "c", "d"])
    # Independent finite truth sets; the construction only uses make().
    from hand_checks import truth_root
    for _ in range(200):
        left = {mask for mask in range(16) if randomizer.randrange(2)}
        right = {mask for mask in range(16) if randomizer.randrange(2)}
        a, b = truth_root(manager, left), truth_root(manager, right)
        assert manager.combine("and", a, b) == truth_root(manager, left & right)
        assert manager.combine("or", a, b) == truth_root(manager, left | right)
        assert manager.negate(a) == truth_root(manager, set(range(16)) - left)
        assert manager.count(a) == len(left)
        for var in range(4):
            for value in (False, True):
                restricted = {mask for mask in range(16) if (mask | (1 << var) if value else mask & ~(1 << var)) in left}
                assert manager.restrict(a, var, value) == truth_root(manager, restricted)
    return 200


def small_graph_fuzz(count):
    randomizer = random.Random(20261013)
    probabilities = [Fraction(0), Fraction(1), Fraction(1, 2), Fraction(1, 3), Fraction(2, 7)]
    for _ in range(count):
        names = [f"DB{i}" for i in range(randomizer.randint(1, 6))]
        variables = [f"s{i}" for i in range(randomizer.randrange(7))]
        sources = [(name, randomizer.choice(probabilities)) for name in variables]
        edges = [edge(f"e{i}", randomizer.choice(names), randomizer.choice(names),
                      randomizer.choice(variables), randomizer.randrange(3))
                 for i in range(randomizer.randrange(13))] if variables else []
        qs = []
        for i in range(randomizer.randint(1, 3)):
            conditioned = randomizer.sample(variables, randomizer.randrange(len(variables) + 1))
            qs.append(query(f"q{i}", randomizer.choice(names), randomizer.choice(names),
                condition=[{"source_id": name, "value": bool(randomizer.randrange(2))} for name in conditioned],
                types=randomizer.sample(range(3), randomizer.randrange(4))))
        input_bytes, proof, report = hand_small(graph(names, sources, edges, qs))
        check(input_bytes, proof, report)
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--fuzz-count", type=int, default=500)
    args = parser.parse_args()
    assert not args.out_dir.exists()
    args.out_dir.mkdir(parents=True)
    started = time.monotonic()
    records = []
    for name, section, raw in scored_cases():
        input_bytes, proof, report = control(raw)
        check(input_bytes, proof, report)
        check_part(input_bytes, proof, report, section)
        folder = args.out_dir / name
        folder.mkdir()
        for filename, body in (("input.json", input_bytes), ("proof.json", proof), ("report.json", report)):
            (folder / filename).write_bytes(body)
        records.append({"name": name, "section": section, "status": "PASS",
                        "nodes": len(json.loads(proof)["nodes"]), "proof_bytes": len(proof)})
    raw = serial_fixture(48)
    input_bytes, proof, report = control(raw)
    check(input_bytes, proof, report)
    folder = args.out_dir / "boundary_96_sources"
    folder.mkdir()
    for filename, body in (("input.json", input_bytes), ("proof.json", proof), ("report.json", report)):
        (folder / filename).write_bytes(body)
    # An incorrect probability loses probability credit, not proof/family credit.
    input_bytes, proof, report = control(scored_cases()[1][2])
    bad = json.loads(report)
    bad["results"][0]["probability"] = fraction_object(Fraction(7, 16))
    check_part(input_bytes, proof, canonical(bad), "proof")
    check_part(input_bytes, proof, canonical(bad), "family")
    try:
        check_part(input_bytes, proof, canonical(bad), "probability")
    except AssertionError:
        pass
    else:
        raise AssertionError("incorrect probability received probability credit")
    # A wrong M can leave formerly reachable nodes orphaned. That violates
    # serialization/family, but must not erase independently valid F credit.
    bad_proof = json.loads(proof)
    bad_proof["queries"][0]["minimal_root"] = 0
    check_part(input_bytes, canonical(bad_proof), report, "proof")
    check_part(input_bytes, canonical(bad_proof), report, "probability")
    try:
        check_part(input_bytes, canonical(bad_proof), report, "family")
    except AssertionError:
        pass
    else:
        raise AssertionError("incorrect minimal root received family credit")
    primitives = boolean_primitive_checks()
    fuzz = small_graph_fuzz(args.fuzz_count)
    result = {"status": "PASS", "mapped_checks": CHECKS, "fixture_controls": records,
              "boundary_96_sources": "PASS", "partial_credit_independence": "PASS",
              "boolean_truth_table_trials": primitives, "small_graph_fuzz_cases": fuzz,
              "elapsed_sec": round(time.monotonic() - started, 3), "blind_score": None,
              "general_oracle_solution": False}
    (args.out_dir / "quality_result.json").write_bytes(canonical(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
