"""Independent local-identity checker; not a DDI reachability answer engine.

It verifies supplied finite reachability layers, then derives report metrics.
No reference solution, graph compiler, optimizer or golden output is imported.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re


ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z", re.ASCII)
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def strict_json(raw: bytes):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, "duplicate JSON key"
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("non-finite JSON value: " + value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs,
                      parse_constant=bad_constant)


def fields(value, names):
    assert type(value) is dict and set(value) == set(names), "wrong object fields"


def integer(value, lower, upper):
    assert type(value) is int and lower <= value <= upper, "invalid integer"


def identifier(value):
    assert type(value) is str and ID.fullmatch(value), "invalid ID"


def parse_input(raw: bytes) -> dict:
    data = strict_json(raw)
    fields(data, ("version", "nodes", "sources", "edges", "queries"))
    integer(data["version"], 1, 1)
    for key in ("nodes", "sources", "edges", "queries"):
        assert type(data[key]) is list
    assert 1 <= len(data["nodes"]) <= 160
    assert len(data["sources"]) <= 96 and len(data["edges"]) <= 600
    assert 1 <= len(data["queries"]) <= 12
    for name in data["nodes"]:
        identifier(name)
    assert len(set(data["nodes"])) == len(data["nodes"])
    nodes = set(data["nodes"])
    sources = {}
    for item in data["sources"]:
        fields(item, ("source_id", "numerator", "denominator"))
        identifier(item["source_id"])
        assert item["source_id"] not in sources
        integer(item["denominator"], 1, 1_000_000)
        integer(item["numerator"], 0, item["denominator"])
        sources[item["source_id"]] = item
    seen = set()
    for edge in data["edges"]:
        fields(edge, ("edge_id", "d1", "d2", "type", "source_id"))
        identifier(edge["edge_id"])
        assert edge["edge_id"] not in seen
        seen.add(edge["edge_id"])
        assert edge["d1"] in nodes and edge["d2"] in nodes
        assert edge["source_id"] in sources
        integer(edge["type"], 0, 2**63 - 1)
    seen = set()
    for query in data["queries"]:
        fields(query, ("query_id", "start", "end", "event_types", "condition", "ranks"))
        identifier(query["query_id"])
        assert query["query_id"] not in seen
        seen.add(query["query_id"])
        assert query["start"] in nodes and query["end"] in nodes
        assert type(query["event_types"]) is list
        for event_type in query["event_types"]:
            integer(event_type, 0, 2**63 - 1)
        assert len(set(query["event_types"])) == len(query["event_types"])
        assert type(query["condition"]) is list
        fixed = set()
        for item in query["condition"]:
            fields(item, ("source_id", "value"))
            assert item["source_id"] in sources and item["source_id"] not in fixed
            assert type(item["value"]) is bool
            fixed.add(item["source_id"])
        assert type(query["ranks"]) is list and len(query["ranks"]) <= 32
        for rank in query["ranks"]:
            assert type(rank) is str and len(rank) <= 128 and DECIMAL.fullmatch(rank)
        assert len(set(query["ranks"])) == len(query["ranks"])
    # Normalize collections, not rank request order.
    data["nodes"].sort()
    data["sources"].sort(key=lambda item: item["source_id"])
    data["edges"].sort(key=lambda item: item["edge_id"])
    data["queries"].sort(key=lambda item: item["query_id"])
    return data


class Diagram:
    """Boolean identities and scalar measurements of already supplied roots."""

    def __init__(self, variables):
        self.variables = tuple(variables)
        self.n = len(variables)
        self.nodes = {}
        self.unique = {}

    def level(self, root):
        return self.n if root < 2 else self.nodes[root][0]

    def make(self, var, low, high):
        if low == high:
            return low
        key = (var, low, high)
        if key not in self.unique:
            root = len(self.nodes) + 2
            self.unique[key] = root
            self.nodes[root] = key
        return self.unique[key]

    def variable(self, var):
        return self.make(var, 0, 1)

    @lru_cache(maxsize=None)
    def negate(self, root):
        if root < 2:
            return 1 - root
        var, low, high = self.nodes[root]
        return self.make(var, self.negate(low), self.negate(high))

    @lru_cache(maxsize=None)
    def combine(self, op, a, b):
        if a > b:
            return self.combine(op, b, a)
        assert op in ("and", "or")
        if a == b:
            return a
        if op == "and":
            if a == 0:
                return 0
            if a == 1:
                return b
        else:
            if a == 0:
                return b
            if a == 1:
                return 1
        top = min(self.level(a), self.level(b))
        al, ah = self.nodes[a][1:] if self.level(a) == top else (a, a)
        bl, bh = self.nodes[b][1:] if self.level(b) == top else (b, b)
        return self.make(top, self.combine(op, al, bl), self.combine(op, ah, bh))

    @lru_cache(maxsize=None)
    def restrict(self, root, var, value):
        if root < 2 or self.level(root) > var:
            return root
        current, low, high = self.nodes[root]
        if current == var:
            return high if value else low
        return self.make(current, self.restrict(low, var, value),
                         self.restrict(high, var, value))

    @lru_cache(maxsize=None)
    def count(self, root, level=0):
        if root == 0:
            return 0
        if root == 1:
            return 1 << (self.n - level)
        var, low, high = self.nodes[root]
        return (1 << (var - level)) * (self.count(low, var + 1)
                                      + self.count(high, var + 1))

    def probability(self, root, weights):
        @lru_cache(maxsize=None)
        def walk(node):
            if node < 2:
                return Fraction(node)
            var, low, high = self.nodes[node]
            p = weights[var]
            return (1 - p) * walk(low) + p * walk(high)
        return walk(root)

    def support_sizes(self, root):
        @lru_cache(maxsize=None)
        def walk(node):
            if node == 0:
                return None
            if node == 1:
                return (0, 0)
            _, low, high = self.nodes[node]
            options = []
            left, right = walk(low), walk(high)
            if left is not None:
                options.append(left)
            if right is not None:
                options.append((right[0] + 1, right[1] + 1))
            return min(x[0] for x in options), max(x[1] for x in options)
        return walk(root)

    def ranked_minimal_support(self, root, rank):
        if rank >= self.count(root):
            return None
        result = []
        level = 0
        while root >= 2:
            var, low, high = self.nodes[root]
            # In a valid minimal-family BDD, a satisfying path cannot skip a
            # variable: both assignments would contradict the antichain.
            assert var == level
            high_count = self.count(high, var + 1)
            if rank < high_count:
                result.append(self.variables[var])
                root = high
            else:
                rank -= high_count
                root = low
            level += 1
        assert root == 1 and level == self.n and rank == 0
        return result


def import_proof(raw: bytes, data: dict):
    proof = strict_json(raw)
    assert canonical(proof) == raw, "proof must use canonical JSON bytes"
    fields(proof, ("version", "variables", "nodes", "queries"))
    integer(proof["version"], 1, 1)
    variables = [item["source_id"] for item in data["sources"]]
    assert proof["variables"] == variables
    assert type(proof["nodes"]) is list and len(proof["nodes"]) <= 100000
    manager = Diagram(variables)
    keys = []
    for expected_id, item in enumerate(proof["nodes"], 2):
        fields(item, ("id", "var", "low", "high"))
        integer(item["id"], expected_id, expected_id)
        integer(item["var"], 0, manager.n - 1)
        integer(item["low"], 0, expected_id - 1)
        integer(item["high"], 0, expected_id - 1)
        assert item["low"] != item["high"]
        assert manager.level(item["low"]) > item["var"]
        assert manager.level(item["high"]) > item["var"]
        key = (item["var"], item["low"], item["high"])
        assert key not in manager.unique
        assert manager.make(*key) == expected_id
        keys.append((-item["var"], item["low"], item["high"]))
    assert keys == sorted(keys), "noncanonical node numbering"
    assert type(proof["queries"]) is list
    assert len(proof["queries"]) == len(data["queries"])
    maximum = len(proof["nodes"]) + 1
    roots = []
    for item, query in zip(proof["queries"], data["queries"]):
        fields(item, ("query_id", "layers", "root", "minimal_root"))
        assert item["query_id"] == query["query_id"]
        assert type(item["layers"]) is list and len(item["layers"]) == len(data["nodes"])
        for row in item["layers"]:
            assert type(row) is list and len(row) == len(data["nodes"])
            for root in row:
                integer(root, 0, maximum)
            roots.extend(row)
        for key in ("root", "minimal_root"):
            integer(item[key], 0, maximum)
            roots.append(item[key])
    seen = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node < 2 or node in seen:
            continue
        seen.add(node)
        stack.extend(manager.nodes[node][1:])
    assert seen == set(manager.nodes), "orphan BDD nodes"
    return proof, manager


def fraction_object(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def verify_certificates(data, proof, manager):
    node_index = {name: i for i, name in enumerate(data["nodes"])}
    var_index = {name: i for i, name in enumerate(manager.variables)}
    weights = [Fraction(item["numerator"], item["denominator"]) for item in data["sources"]]
    results = []
    for query, certificate in zip(data["queries"], proof["queries"]):
        condition = {var_index[item["source_id"]]: item["value"] for item in query["condition"]}
        selected = set(query["event_types"])
        incoming = [[] for _ in data["nodes"]]
        for edge in data["edges"]:
            if selected and edge["type"] not in selected:
                continue
            var = var_index[edge["source_id"]]
            activation = int(condition[var]) if var in condition else manager.variable(var)
            incoming[node_index[edge["d2"]]].append((node_index[edge["d1"]], activation))
        start = node_index[query["start"]]
        initial = [int(i == start) for i in range(len(data["nodes"]))]
        assert certificate["layers"][0] == initial, "invalid zero-path layer"
        for prior, current in zip(certificate["layers"], certificate["layers"][1:]):
            for target, edges in enumerate(incoming):
                expected = prior[target]
                for source, activation in edges:
                    step = manager.combine("and", prior[source], activation)
                    expected = manager.combine("or", expected, step)
                assert current[target] == expected, "false reachability-layer identity"
        root = certificate["root"]
        assert root == certificate["layers"][-1][node_index[query["end"]]]
        minimal = root
        for var in range(manager.n):
            literal = manager.variable(var)
            if var in condition:
                factor = manager.negate(literal)
            else:
                factor = manager.combine("or", manager.negate(literal),
                                         manager.negate(manager.restrict(root, var, False)))
            minimal = manager.combine("and", minimal, factor)
        assert minimal == certificate["minimal_root"], "incomplete/nonminimal support family"
        sizes = manager.support_sizes(minimal)
        condition_possible = all(weights[var] != (0 if value else 1)
                                 for var, value in condition.items())
        free = [var for var in range(manager.n) if var not in condition]
        results.append({
            "query_id": query["query_id"],
            "support_count": str(manager.count(root) >> len(condition)),
            "minimal_support_count": str(manager.count(minimal)),
            "min_size": sizes[0] if sizes else None,
            "max_size": sizes[1] if sizes else None,
            "ranked_supports": [{"rank": rank, "sources": manager.ranked_minimal_support(minimal, int(rank))}
                                for rank in query["ranks"]],
            "critical_sources": [manager.variables[var] for var in free
                                 if root != 0 and manager.restrict(root, var, False) == 0],
            "probability_state": "DEFINED" if condition_possible else "UNDEFINED",
            "probability": fraction_object(manager.probability(root, weights)) if condition_possible else None,
            "sensitivities": {
                manager.variables[var]: fraction_object(
                    manager.probability(manager.restrict(root, var, True), weights)
                    - manager.probability(manager.restrict(root, var, False), weights))
                if condition_possible else None for var in free},
        })
    return results


def check(input_bytes: bytes, proof_bytes: bytes, report_bytes: bytes):
    data = parse_input(input_bytes)
    proof, manager = import_proof(proof_bytes, data)
    expected = {"version": 1, "proof_sha256": hashlib.sha256(proof_bytes).hexdigest(),
                "results": verify_certificates(data, proof, manager)}
    report = strict_json(report_bytes)
    assert canonical(report) == report_bytes, "report must use canonical JSON bytes"
    assert report_bytes == canonical(expected), "reported metrics differ from verified certificate"
    return expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.input.read_bytes(), (args.out_dir / "proof.json").read_bytes(),
                   (args.out_dir / "report.json").read_bytes())
    print(json.dumps({"status": "PASS", "queries": len(result["results"])}))


if __name__ == "__main__":
    main()
