"""Checker quality controls from BFS truth tables and a closed-form family.

The small oracle is deliberately limited to eight sources. It cannot answer
the 80-source release fixture. The large certificate is a hand-derived serial
parallel-evidence identity, not output from a general DDI answer engine.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import time

from certificate_check import Diagram, canonical, check, fraction_object, parse_input


def edge(name, d1, d2, source, event_type=5):
    return {"edge_id": name, "d1": d1, "d2": d2, "source_id": source, "type": event_type}


def query(name, start, end, condition=(), types=(), ranks=("0", "1", "99")):
    return {"query_id": name, "start": start, "end": end, "condition": list(condition),
            "event_types": list(types), "ranks": list(ranks)}


def graph(nodes, sources, edges, queries):
    return {"version": 1, "nodes": nodes,
            "sources": [{"source_id": name, "numerator": p.numerator, "denominator": p.denominator}
                        for name, p in sources], "edges": edges, "queries": queries}


def bfs_layers(data, q, mask):
    variables = [item["source_id"] for item in data["sources"]]
    position = {name: i for i, name in enumerate(variables)}
    fixed = {item["source_id"]: item["value"] for item in q["condition"]}
    active = {name for name in variables if fixed.get(name, bool(mask & (1 << position[name])))}
    selected = set(q["event_types"])
    edges = [item for item in data["edges"] if item["source_id"] in active
             and (not selected or item["type"] in selected)]
    reached = {q["start"]}
    result = [set(reached)]
    for _ in range(len(data["nodes"]) - 1):
        reached = reached | {item["d2"] for item in edges if item["d1"] in reached}
        result.append(set(reached))
    return result


def truth_root(manager, masks):
    masks = frozenset(masks)

    def build(level, possibilities):
        if not possibilities:
            return 0
        if level == manager.n:
            return 1
        low = [mask for mask in possibilities if not mask & (1 << level)]
        high = [mask for mask in possibilities if mask & (1 << level)]
        return manager.make(level, build(level + 1, low), build(level + 1, high))
    return build(0, masks)


def export(manager, certificates):
    roots = [root for item in certificates for row in item["layers"] for root in row]
    roots += [root for item in certificates for root in (item["root"], item["minimal_root"])]
    seen = set()
    pending = list(roots)
    while pending:
        root = pending.pop()
        if root < 2 or root in seen:
            continue
        seen.add(root)
        pending.extend(manager.nodes[root][1:])
    remap = {0: 0, 1: 1}
    nodes = []
    for var in reversed(range(manager.n)):
        group = [root for root in seen if manager.nodes[root][0] == var]
        group.sort(key=lambda root: tuple(remap[child] for child in manager.nodes[root][1:]))
        for root in group:
            _, low, high = manager.nodes[root]
            new = len(nodes) + 2
            remap[root] = new
            nodes.append({"id": new, "var": var, "low": remap[low], "high": remap[high]})
    result = []
    for item in certificates:
        result.append({"query_id": item["query_id"],
                       "layers": [[remap[root] for root in row] for row in item["layers"]],
                       "root": remap[item["root"]], "minimal_root": remap[item["minimal_root"]]})
    return {"version": 1, "variables": list(manager.variables), "nodes": nodes, "queries": result}


def hand_small(raw):
    data = parse_input(canonical(raw))
    variables = [item["source_id"] for item in data["sources"]]
    assert len(variables) <= 8, "This tiny quality oracle is not a general answer engine"
    manager = Diagram(variables)
    probabilities = [Fraction(item["numerator"], item["denominator"]) for item in data["sources"]]
    certificates, results = [], []
    all_masks = range(1 << len(variables))
    for q in data["queries"]:
        truth_layers = {mask: bfs_layers(data, q, mask) for mask in all_masks}
        reachable = {mask for mask in all_masks if q["end"] in truth_layers[mask][-1]}
        fixed = {variables.index(item["source_id"]): item["value"] for item in q["condition"]}
        free = [i for i in range(len(variables)) if i not in fixed]
        free_masks = [mask for mask in all_masks if not any(mask & (1 << i) for i in fixed)]
        successes = [mask for mask in free_masks if mask in reachable]
        minimal_masks = [mask for mask in successes
                         if all(mask ^ (1 << i) not in reachable for i in free if mask & (1 << i))]
        supports = sorted(tuple(variables[i] for i in free if mask & (1 << i)) for mask in minimal_masks)
        layers = [[truth_root(manager, {mask for mask in all_masks if node in truth_layers[mask][k]})
                   for node in data["nodes"]] for k in range(len(data["nodes"]))]
        certificates.append({"query_id": q["query_id"], "layers": layers,
                             "root": truth_root(manager, reachable),
                             "minimal_root": truth_root(manager, minimal_masks)})

        def probability(extra=None):
            total = Fraction(0)
            for mask in free_masks:
                if extra is not None and bool(mask & (1 << extra[0])) != extra[1]:
                    continue
                if mask not in reachable:
                    continue
                weight = Fraction(1)
                for i in free:
                    if extra is not None and i == extra[0]:
                        continue
                    weight *= probabilities[i] if mask & (1 << i) else 1 - probabilities[i]
                total += weight
            return total

        possible = all(probabilities[i] != (0 if value else 1) for i, value in fixed.items())
        results.append({
            "query_id": q["query_id"], "support_count": str(len(successes)),
            "minimal_support_count": str(len(supports)),
            "min_size": min(map(len, supports)) if supports else None,
            "max_size": max(map(len, supports)) if supports else None,
            "ranked_supports": [{"rank": rank, "sources": list(supports[int(rank)])
                                 if int(rank) < len(supports) else None} for rank in q["ranks"]],
            "critical_sources": sorted(set.intersection(*(set(s) for s in supports))) if supports else [],
            "probability_state": "DEFINED" if possible else "UNDEFINED",
            "probability": fraction_object(probability()) if possible else None,
            "sensitivities": {variables[i]: fraction_object(probability((i, True)) - probability((i, False)))
                              if possible else None for i in free},
        })
    proof = export(manager, certificates)
    proof_bytes = canonical(proof)
    report = {"version": 1, "proof_sha256": hashlib.sha256(proof_bytes).hexdigest(), "results": results}
    return canonical(data), proof_bytes, canonical(report)


def serial_pairs(k):
    variables = [f"e{i:02d}{letter}" for i in range(k) for letter in ("a", "b")]
    names = [f"DBL{i:03d}" for i in range(k + 1)]
    raw = graph(names, [(name, Fraction(1, 2)) for name in variables],
                [edge(f"obs{i:02d}{letter}", names[i], names[i + 1], f"e{i:02d}{letter}")
                 for i in range(k) for letter in ("a", "b")],
                [query("serial", names[0], names[-1],
                       ranks=tuple(dict.fromkeys(("0", "1", str(2**k - 1), str(2**k)))))])
    manager = Diagram(variables)
    prefixes, minimal = [1], 1
    for i in range(k):
        a, b = manager.variable(2 * i), manager.variable(2 * i + 1)
        prefixes.append(manager.combine("and", prefixes[-1], manager.combine("or", a, b)))
        exact_one = manager.combine("or", manager.combine("and", a, manager.negate(b)),
                                    manager.combine("and", manager.negate(a), b))
        minimal = manager.combine("and", minimal, exact_one)
    certificate = {"query_id": "serial", "layers": [
        [prefixes[v] if v <= layer else 0 for v in range(k + 1)] for layer in range(k + 1)],
        "root": prefixes[-1], "minimal_root": minimal}
    proof = canonical(export(manager, [certificate]))
    results = [{
        "query_id": "serial", "support_count": str(3**k), "minimal_support_count": str(2**k),
        "min_size": k, "max_size": k,
        "ranked_supports": [{"rank": rank, "sources":
            [f"e{i:02d}{'b' if (int(rank) >> (k - i - 1)) & 1 else 'a'}" for i in range(k)]
            if int(rank) < 2**k else None} for rank in raw["queries"][0]["ranks"]],
        "critical_sources": [], "probability_state": "DEFINED",
        "probability": fraction_object(Fraction(3, 4)**k),
        "sensitivities": {name: fraction_object(Fraction(1, 2) * Fraction(3, 4)**(k - 1))
                          for name in variables},
    }]
    report = canonical({"version": 1, "proof_sha256": hashlib.sha256(proof).hexdigest(), "results": results})
    return canonical(raw), proof, report


def rejected(input_bytes, proof, report):
    try:
        check(input_bytes, proof, report)
    except (AssertionError, ValueError, TypeError, KeyError):
        return
    raise AssertionError("deliberately incorrect certificate/report was accepted")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    assert not args.out_dir.exists(), "preserve previous checks"
    args.out_dir.mkdir(parents=True)
    started = time.monotonic()
    half = Fraction(1, 2)
    cases = [
        ("independent_diamond", graph(["A", "B", "C", "D"], [(x, half) for x in "abcd"],
            [edge("ab", "A", "B", "a"), edge("bd", "B", "D", "b"),
             edge("ac", "A", "C", "c"), edge("cd", "C", "D", "d")], [query("q", "A", "D")])),
        ("shared_diamond", graph(["A", "B", "C", "D"], [(x, half) for x in "abc"],
            [edge("ab", "A", "B", "a"), edge("ac", "A", "C", "a"),
             edge("bd", "B", "D", "b"), edge("cd", "C", "D", "c")], [query("q", "A", "D")])),
        ("unequal_minima_and_cycles", graph(["A", "B", "C", "D"], [(x, half) for x in "abcd"],
            [edge("direct", "A", "D", "a"), edge("ab", "A", "B", "b"),
             edge("bd", "B", "D", "c"), edge("bc", "B", "C", "d"),
             edge("cb", "C", "B", "d")], [query("q", "A", "D"), query("reverse", "D", "A")])),
        ("conditions_and_endpoints", graph(["A", "B"], [("a", Fraction(0)), ("b", Fraction(1)), ("c", half)],
            [edge("ab", "A", "B", "a"), edge("ba", "B", "A", "b", 6)],
            [query("normal", "A", "B"), query("self", "A", "A"),
             query("impossible", "A", "B", condition=[{"source_id": "a", "value": True}]),
             query("filtered", "B", "A", types=[5])])),
        ("zero_sources", graph(["A", "B"], [], [], [query("self", "A", "A"), query("missing", "A", "B")])),
    ]
    records = []
    for name, raw in cases:
        input_bytes, proof, report = hand_small(raw)
        checked = check(input_bytes, proof, report)
        if name == "independent_diamond":
            assert checked["results"][0]["probability"] == fraction_object(Fraction(7, 16))
        if name == "shared_diamond":
            assert checked["results"][0]["probability"] == fraction_object(Fraction(3, 8))
            bad = json.loads(report)
            bad["results"][0]["probability"] = fraction_object(Fraction(7, 16))
            rejected(input_bytes, proof, canonical(bad))
        mutated = json.loads(proof)
        mutated["queries"][0]["layers"][0][0] = 1 - mutated["queries"][0]["layers"][0][0]
        rejected(input_bytes, canonical(mutated), report)
        bad = json.loads(report)
        bad["results"][0]["minimal_support_count"] = "999"
        rejected(input_bytes, proof, canonical(bad))
        folder = args.out_dir / name
        folder.mkdir()
        for filename, body in (("input.json", input_bytes), ("proof.json", proof), ("report.json", report)):
            (folder / filename).write_bytes(body)
        records.append({"case": name, "status": "PASS", "queries": len(checked["results"])})
    for k in (1, 4, 40):
        input_bytes, proof, report = serial_pairs(k)
        checked = check(input_bytes, proof, report)
        folder = args.out_dir / f"serial_{k}"
        folder.mkdir()
        for filename, body in (("input.json", input_bytes), ("proof.json", proof), ("report.json", report)):
            (folder / filename).write_bytes(body)
        records.append({"case": f"serial_{k}", "status": "PASS",
                        "minimal_supports": checked["results"][0]["minimal_support_count"],
                        "nodes": len(json.loads(proof)["nodes"]), "certificate_bytes": len(proof)})
    result = {"status": "PASS", "cases": records, "elapsed_sec": round(time.monotonic() - started, 3),
              "blind_score": None, "full_external_task_frozen": False}
    (args.out_dir / "quality_result.json").write_bytes(canonical(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
