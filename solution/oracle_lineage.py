#!/usr/bin/env python3
"""Repair this command according to instruction.md; use Python 3.11 stdlib.

ddi-lineage analyses directed observation paths over shared evidence sources.

Model
-----
Every evidence source ``s`` is an independent Bernoulli variable with
probability ``numerator/denominator``.  An assignment *activates* an edge when
the edge's source variable is true and the edge's event type is selected by the
query.  ``F`` is the Boolean function "``end`` is reachable from ``start``"
over the free (unconditioned) source variables.

Outputs
-------
``proof.json`` carries one shared reduced ordered BDD over all source variables
(variables ordered by ascending source id, terminals 0/1 implicit, non-terminal
ids assigned bottom-up by decreasing variable index and then by increasing
``(low, high)``).  Per query it pins ``root`` down through the layered
reachability recurrence and supplies ``minimal_root``, the characteristic
function of the inclusion-minimal supports.

``report.json`` carries the logical metrics (counts, lexicographic ranks,
criticality) and the exact rational reliability metrics derived from the
free-source Bernoulli distribution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from math import gcd
from pathlib import Path

sys.setrecursionlimit(100000)

_ID_RE = re.compile(r"\A[A-Za-z0-9_\-]{1,32}\Z")
_RANK_RE = re.compile(r"\A(?:0|[1-9][0-9]{0,127})\Z")
_MAX_TYPE = (1 << 63) - 1
_TOP_KEYS = frozenset(("version", "nodes", "sources", "edges", "queries"))
_EDGE_KEYS = frozenset(("edge_id", "d1", "d2", "type", "source_id"))
_SOURCE_KEYS = frozenset(("source_id", "numerator", "denominator"))
_QUERY_KEYS = frozenset(
    ("query_id", "start", "end", "event_types", "condition", "ranks")
)
_COND_KEYS = frozenset(("source_id", "value"))


class Fatal(Exception):
    """Any invalid input, invalid CLI usage or fatal runtime condition."""


# --------------------------------------------------------------------------
# input validation
# --------------------------------------------------------------------------


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Fatal("duplicate JSON key: %r" % (key,))
        obj[key] = value
    return obj


def _load_document(path):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Fatal("cannot read input file: %s" % (exc,)) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Fatal("input is not valid UTF-8: %s" % (exc,)) from exc
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except Fatal:
        raise
    except Exception as exc:
        raise Fatal("input is not valid JSON: %s" % (exc,)) from exc


def _need_int(value, what, lo=None, hi=None):
    if type(value) is not int:
        raise Fatal("%s must be an integer" % what)
    if lo is not None and value < lo:
        raise Fatal("%s must be at least %d" % (what, lo))
    if hi is not None and value > hi:
        raise Fatal("%s must be at most %d" % (what, hi))
    return value


def _need_bool(value, what):
    if type(value) is not bool:
        raise Fatal("%s must be a JSON boolean" % what)
    return value


def _need_list(value, what, lo=None, hi=None):
    if type(value) is not list:
        raise Fatal("%s must be an array" % what)
    if lo is not None and len(value) < lo:
        raise Fatal("%s must have at least %d entries" % (what, lo))
    if hi is not None and len(value) > hi:
        raise Fatal("%s must have at most %d entries" % (what, hi))
    return value


def _need_object(value, what):
    if type(value) is not dict:
        raise Fatal("%s must be an object" % what)
    return value


def _need_exact_keys(obj, keys, what):
    got = set(obj)
    if got == keys:
        return obj
    missing = keys - got
    if missing:
        raise Fatal("%s is missing field(s): %s" % (what, ", ".join(sorted(missing))))
    raise Fatal("%s has unknown field(s): %s" % (what, ", ".join(sorted(got - keys))))


def _need_id(value, what):
    if type(value) is not str:
        raise Fatal("%s must be a string" % what)
    if not _ID_RE.match(value):
        raise Fatal("%s is not a valid identifier" % what)
    return value


def parse_input(document):
    """Validate the whole document and normalise it.  Raises Fatal."""
    if type(document) is not dict:
        raise Fatal("input JSON must be an object")
    _need_exact_keys(document, _TOP_KEYS, "input")

    if _need_int(document["version"], "version") != 1:
        raise Fatal("version must be 1")

    raw_nodes = _need_list(document["nodes"], "nodes", 1, 160)
    nodes = []
    seen_nodes = set()
    for index, item in enumerate(raw_nodes):
        node_id = _need_id(item, "nodes[%d]" % index)
        if node_id in seen_nodes:
            raise Fatal("duplicate node id: %s" % node_id)
        seen_nodes.add(node_id)
        nodes.append(node_id)

    raw_sources = _need_list(document["sources"], "sources", 0, 96)
    sources = []
    seen_sources = set()
    for index, item in enumerate(raw_sources):
        label = "sources[%d]" % index
        _need_exact_keys(_need_object(item, label), _SOURCE_KEYS, label)
        source_id = _need_id(item["source_id"], label + ".source_id")
        if source_id in seen_sources:
            raise Fatal("duplicate source id: %s" % source_id)
        seen_sources.add(source_id)
        numerator = _need_int(item["numerator"], label + ".numerator")
        denominator = _need_int(item["denominator"], label + ".denominator", 1, 1000000)
        if not 0 <= numerator <= denominator:
            raise Fatal("%s.numerator must be an integer in 0..denominator" % label)
        sources.append((source_id, numerator, denominator))

    raw_edges = _need_list(document["edges"], "edges", 0, 600)
    edges = []
    seen_edges = set()
    for index, item in enumerate(raw_edges):
        label = "edges[%d]" % index
        _need_exact_keys(_need_object(item, label), _EDGE_KEYS, label)
        edge_id = _need_id(item["edge_id"], label + ".edge_id")
        if edge_id in seen_edges:
            raise Fatal("duplicate edge id: %s" % edge_id)
        seen_edges.add(edge_id)
        d1 = _need_id(item["d1"], label + ".d1")
        d2 = _need_id(item["d2"], label + ".d2")
        if d1 not in seen_nodes:
            raise Fatal("%s.d1 references unknown node: %s" % (label, d1))
        if d2 not in seen_nodes:
            raise Fatal("%s.d2 references unknown node: %s" % (label, d2))
        source_id = _need_id(item["source_id"], label + ".source_id")
        if source_id not in seen_sources:
            raise Fatal("%s.source_id references unknown source: %s" % (label, source_id))
        event_type = _need_int(item["type"], label + ".type", 0, _MAX_TYPE)
        edges.append((d1, d2, event_type, source_id))

    raw_queries = _need_list(document["queries"], "queries", 1, 12)
    queries = []
    seen_queries = set()
    for index, item in enumerate(raw_queries):
        label = "queries[%d]" % index
        _need_exact_keys(_need_object(item, label), _QUERY_KEYS, label)
        query_id = _need_id(item["query_id"], label + ".query_id")
        if query_id in seen_queries:
            raise Fatal("duplicate query id: %s" % query_id)
        seen_queries.add(query_id)
        start = _need_id(item["start"], label + ".start")
        end = _need_id(item["end"], label + ".end")
        if start not in seen_nodes:
            raise Fatal("%s.start references unknown node: %s" % (label, start))
        if end not in seen_nodes:
            raise Fatal("%s.end references unknown node: %s" % (label, end))

        raw_types = _need_list(item["event_types"], label + ".event_types")
        event_types = []
        seen_types = set()
        for position, value in enumerate(raw_types):
            event_type = _need_int(
                value, "%s.event_types[%d]" % (label, position), 0, _MAX_TYPE
            )
            if event_type in seen_types:
                raise Fatal("%s.event_types has a duplicate entry" % label)
            seen_types.add(event_type)
            event_types.append(event_type)

        raw_condition = _need_list(item["condition"], label + ".condition")
        condition = []
        seen_condition = set()
        for position, entry in enumerate(raw_condition):
            entry_label = "%s.condition[%d]" % (label, position)
            _need_exact_keys(_need_object(entry, entry_label), _COND_KEYS, entry_label)
            source_id = _need_id(entry["source_id"], entry_label + ".source_id")
            if source_id not in seen_sources:
                raise Fatal("%s references unknown source: %s" % (entry_label, source_id))
            if source_id in seen_condition:
                raise Fatal("%s repeats source %s" % (label, source_id))
            seen_condition.add(source_id)
            condition.append(
                (source_id, _need_bool(entry["value"], entry_label + ".value"))
            )

        raw_ranks = _need_list(item["ranks"], label + ".ranks", 0, 32)
        ranks = []
        seen_ranks = set()
        for position, value in enumerate(raw_ranks):
            rank_label = "%s.ranks[%d]" % (label, position)
            if type(value) is not str:
                raise Fatal("%s must be a string" % rank_label)
            if not _RANK_RE.match(value):
                raise Fatal("%s is not a canonical unsigned decimal string" % rank_label)
            if value in seen_ranks:
                raise Fatal("%s.ranks has a duplicate entry" % label)
            seen_ranks.add(value)
            ranks.append(value)

        queries.append(
            {
                "query_id": query_id,
                "start": start,
                "end": end,
                "event_types": frozenset(event_types),
                "condition": condition,
                "ranks": ranks,
            }
        )

    queries.sort(key=lambda query: query["query_id"])
    return {
        "nodes": sorted(nodes),
        "sources": sorted(sources),
        "edges": edges,
        "queries": queries,
    }


# --------------------------------------------------------------------------
# reduced ordered BDD
# --------------------------------------------------------------------------


class _BDD:
    """Shared reduced ordered BDD; node 0 is false and node 1 is true.

    Variable indices follow the order of ``variables`` (ascending source id),
    and a node's children always carry a strictly larger variable index.
    """

    __slots__ = ("nvars", "var", "lo", "hi", "uniq", "c_and", "c_or", "c_not", "c_cof")

    def __init__(self, nvars):
        self.nvars = nvars
        self.var = [nvars, nvars]
        self.lo = [0, 0]
        self.hi = [0, 1]
        self.uniq = {}
        self.c_and = {}
        self.c_or = {}
        self.c_not = {}
        self.c_cof = {}

    def mk(self, var, lo, hi):
        if lo == hi:
            return lo
        key = (var, lo, hi)
        found = self.uniq.get(key)
        if found is None:
            found = len(self.var)
            self.var.append(var)
            self.lo.append(lo)
            self.hi.append(hi)
            self.uniq[key] = found
        return found

    def variable(self, var):
        return self.mk(var, 0, 1)

    def _split(self, f, g):
        vf = self.var[f]
        vg = self.var[g]
        if vf <= vg:
            if vg == vf:
                return vf, self.lo[f], self.hi[f], self.lo[g], self.hi[g]
            return vf, self.lo[f], self.hi[f], g, g
        return vg, f, f, self.lo[g], self.hi[g]

    def AND(self, f, g):
        if f == 0 or g == 0:
            return 0
        if f == 1:
            return g
        if g == 1:
            return f
        if f == g:
            return f
        key = (f, g) if f < g else (g, f)
        found = self.c_and.get(key)
        if found is not None:
            return found
        var, fl, fh, gl, gh = self._split(f, g)
        result = self.mk(var, self.AND(fl, gl), self.AND(fh, gh))
        self.c_and[key] = result
        return result

    def OR(self, f, g):
        if f == 1 or g == 1:
            return 1
        if f == 0:
            return g
        if g == 0:
            return f
        if f == g:
            return f
        key = (f, g) if f < g else (g, f)
        found = self.c_or.get(key)
        if found is not None:
            return found
        var, fl, fh, gl, gh = self._split(f, g)
        result = self.mk(var, self.OR(fl, gl), self.OR(fh, gh))
        self.c_or[key] = result
        return result

    def NOT(self, f):
        if f == 0:
            return 1
        if f == 1:
            return 0
        found = self.c_not.get(f)
        if found is not None:
            return found
        result = self.mk(self.var[f], self.NOT(self.lo[f]), self.NOT(self.hi[f]))
        self.c_not[f] = result
        return result

    def cofactor(self, f, var, high):
        """Restrict ``f`` to ``var == 1`` (high) or ``var == 0`` (low)."""
        if f < 2:
            return f
        key = (f, var, high)
        found = self.c_cof.get(key)
        if found is not None:
            return found
        fv = self.var[f]
        if fv == var:
            result = self.hi[f] if high else self.lo[f]
        elif fv > var:
            result = f
        else:
            result = self.mk(
                fv,
                self.cofactor(self.lo[f], var, high),
                self.cofactor(self.hi[f], var, high),
            )
        self.c_cof[key] = result
        return result

    def trim_caches(self, limit=1500000):
        """Drop pure memo tables once they grow large; the node table stays.

        The shared diagram must survive across queries, but the operation
        caches are only accelerators, so shedding them bounds peak memory on
        wide queries without changing any output.
        """
        if len(self.c_and) + len(self.c_or) + len(self.c_not) + len(self.c_cof) > limit:
            self.c_and.clear()
            self.c_or.clear()
            self.c_not.clear()
            self.c_cof.clear()

    def low_chain(self, f):
        """Value of ``f`` once every variable it mentions is set to false."""
        while f > 1:
            f = self.lo[f]
        return f


# --------------------------------------------------------------------------
# support-family helpers
# --------------------------------------------------------------------------


def _sat_count(bdd, root, order, position):
    """Satisfying assignments over the variables listed in ``order``.

    ``order`` holds BDD variable indices in ascending order and ``position``
    maps a variable index to its rank.  Variables the diagram does not mention
    are counted twice each, since they are irrelevant but still assignable.
    """
    total = len(order)
    memo = {}

    def rec(node, first):
        if node == 0:
            return 0
        if node == 1:
            return 1 << (total - first)
        at = position[bdd.var[node]]
        if at > first:
            # The variables skipped between ``first`` and ``at`` are free, so
            # every one of them doubles the count.
            return rec(node, at) << (at - first)
        found = memo.get(node)
        if found is not None:
            return found
        result = rec(bdd.lo[node], at + 1) + rec(bdd.hi[node], at + 1)
        memo[node] = result
        return result

    return rec(root, 0)


def _family_sizes(bdd, root):
    """(minimum, maximum) support cardinality, or None when the family is empty."""
    memo = {}

    def rec(node):
        if node == 0:
            return None
        if node == 1:
            return (0, 0)
        found = memo.get(node)
        if found is not None or node in memo:
            return found
        options = []
        low = rec(bdd.lo[node])
        if low is not None:
            options.append(low)
        high = rec(bdd.hi[node])
        if high is not None:
            options.append((high[0] + 1, high[1] + 1))
        result = None
        if options:
            result = (min(x[0] for x in options), max(x[1] for x in options))
        memo[node] = result
        return result

    return rec(root)


def _critical_variables(bdd, root):
    """Variables that are true in every model of the family."""
    memo = {}

    def has_model(node):
        if node == 0:
            return False
        if node == 1:
            return True
        found = memo.get(node)
        if found is None:
            found = has_model(bdd.lo[node]) or has_model(bdd.hi[node])
            memo[node] = found
        return found

    reachable = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node < 2 or node in reachable:
            continue
        reachable.add(node)
        stack.append(bdd.lo[node])
        stack.append(bdd.hi[node])

    # A source is critical iff no model of the family leaves it false, i.e. no
    # root-reachable node carrying that variable may have a satisfiable low
    # child (a low branch is exactly "this source is false").
    present = {bdd.var[node] for node in reachable}
    can_be_false = {
        bdd.var[node] for node in reachable if has_model(bdd.lo[node])
    }
    return reachable, present - can_be_false


class _RankSelector:
    """Orders models by their ascending source-id lists (a prefix sorts first)."""

    def __init__(self, bdd, root, free_vars):
        self.bdd = bdd
        self.root = root
        self.free_vars = free_vars
        self.total = len(free_vars)
        self.rank_of = {var: index for index, var in enumerate(free_vars)}
        self.memo = {}

    def count(self, first, node):
        """Models of ``node`` over the free variables at ranks >= ``first``."""
        bdd = self.bdd
        if node == 0:
            return 0
        if node == 1:
            return 1 << (self.total - first)
        at = self.rank_of[bdd.var[node]]
        if at > first:
            return self.count(at, node) << (at - first)
        found = self.memo.get(node)
        if found is not None:
            return found
        total = 1 if bdd.low_chain(node) == 1 else 0
        current = node
        rank = at
        while current and rank < self.total:
            var = self.free_vars[rank]
            total += self.count(rank + 1, bdd.cofactor(current, var, True))
            current = bdd.cofactor(current, var, False)
            rank += 1
        self.memo[node] = total
        return total

    def select(self, first, node, rank):
        """Rank-th model as a list of free ranks, or None when out of range."""
        bdd = self.bdd
        if node == 0:
            return None
        if bdd.low_chain(node) == 1:
            # Every remaining free variable may stay false; the empty
            # continuation is the smallest model in this order.
            if rank == 0:
                return []
            rank -= 1
        current = node
        at = first
        while current and at < self.total:
            var = self.free_vars[at]
            high = bdd.cofactor(current, var, True)
            size = self.count(at + 1, high)
            if rank < size:
                rest = self.select(at + 1, high, rank)
                if rest is None:
                    return None
                return [at] + rest
            rank -= size
            current = bdd.cofactor(current, var, False)
            at += 1
        return None


# --------------------------------------------------------------------------
# exact rational reliability
# --------------------------------------------------------------------------


def _reliability(bdd, root, free, condition_probability_zero):
    """Exact P(F) and the hypothetical sensitivity of every free source.

    ``free`` is a list of ``(variable index, numerator, denominator, source id)``
    in ascending variable order.  Sensitivities are
    ``P(F | s=true) - P(F | s=false)`` without dividing by the conditioning
    probability, so they stay defined for degenerate ``p(s)``.
    """
    if condition_probability_zero:
        # The conditioning event has probability zero, so the conditional
        # distribution is undefined; every derived fraction becomes null while
        # the logical metrics stay meaningful.
        return None, {info[3]: None for info in free}

    free_vars = [info[0] for info in free]
    numerators = [info[1] for info in free]
    denominators = [info[2] for info in free]
    total = len(free_vars)
    rank_of = {var: index for index, var in enumerate(free_vars)}

    prefix = [1] * (total + 1)
    for index in range(total):
        prefix[index + 1] = prefix[index] * denominators[index]
    suffix = [1] * (total + 1)
    for index in range(total - 1, -1, -1):
        suffix[index] = suffix[index + 1] * denominators[index]
    whole = prefix[total]

    reachable = []
    seen = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node < 2 or node in seen:
            continue
        seen.add(node)
        reachable.append(node)
        stack.append(bdd.lo[node])
        stack.append(bdd.hi[node])

    # ``scaled[n]`` is P(subtree(n)) times the denominators of the free bits at
    # rank >= rank(n), so the whole diagram is evaluated with exact integers.
    scaled = {}
    for node in sorted(reachable, key=lambda n: bdd.var[n], reverse=True):
        at = rank_of[bdd.var[node]]
        base = suffix[at + 1]
        mass = 0
        for child, weight in (
            (bdd.lo[node], denominators[at] - numerators[at]),
            (bdd.hi[node], numerators[at]),
        ):
            if weight == 0 or child == 0:
                continue
            if child == 1:
                mass += weight * base
            else:
                child_at = rank_of[bdd.var[child]]
                mass += weight * scaled[child] * (base // suffix[child_at])
        scaled[node] = mass

    probability = None
    if root == 0:
        probability = (0, 1)
    elif root == 1:
        probability = (1, 1)
    else:
        at = rank_of[bdd.var[root]]
        numerator = scaled[root] * prefix[at]
        denominator = whole
        common = gcd(numerator, denominator)
        probability = (numerator // common, denominator // common)

    # Share of the prefix measure that reaches each node.
    reaching = {}
    if root > 1:
        reaching[root] = prefix[rank_of[bdd.var[root]]]
    for node in sorted(reachable, key=lambda n: bdd.var[n]):
        share = reaching.get(node)
        if not share:
            continue
        at = rank_of[bdd.var[node]]
        for child, weight in (
            (bdd.lo[node], denominators[at] - numerators[at]),
            (bdd.hi[node], numerators[at]),
        ):
            if weight == 0 or child < 2:
                continue
            child_at = rank_of[bdd.var[child]]
            step = prefix[child_at] // prefix[at + 1]
            reaching[child] = reaching.get(child, 0) + share * weight * step

    accumulated = {}
    for node in reachable:
        share = reaching.get(node)
        if not share:
            continue
        at = rank_of[bdd.var[node]]
        base = suffix[at]
        gap = 0
        for child, sign in ((bdd.hi[node], 1), (bdd.lo[node], -1)):
            if child == 1:
                gap += sign * base
            elif child > 1:
                child_at = rank_of[bdd.var[child]]
                gap += sign * scaled[child] * (base // suffix[child_at])
        if gap:
            var = bdd.var[node]
            accumulated[var] = accumulated.get(var, 0) + share * gap

    sensitivities = {}
    for info in free:
        numerator = accumulated.get(info[0], 0)
        if numerator == 0:
            sensitivities[info[3]] = (0, 1)
        else:
            common = gcd(abs(numerator), whole)
            sensitivities[info[3]] = (numerator // common, whole // common)
    return probability, sensitivities


# --------------------------------------------------------------------------
# reachability layers
# --------------------------------------------------------------------------


def _layer_stack(bdd, node_count, incoming, start_position):
    """Layers k = 0..N-1 of the finite reachability recurrence."""
    previous = [0] * node_count
    previous[start_position] = 1
    layers = [previous]
    for step in range(1, node_count):
        current = list(previous)
        for target in range(node_count):
            accumulator = current[target]
            for origin_position, activation in incoming[target]:
                origin = previous[origin_position]
                if origin == 0 or activation == 0:
                    continue
                term = bdd.AND(origin, activation)
                if term == 0:
                    continue
                accumulator = bdd.OR(accumulator, term)
            current[target] = accumulator
        layers.append(current)
        if current == previous:
            for _ in range(node_count - 1 - step):
                layers.append(current)
            break
        previous = current
    return layers


# --------------------------------------------------------------------------
# whole computation
# --------------------------------------------------------------------------


def _render_fraction(value):
    return {"denominator": str(value[1]), "numerator": str(value[0])}


def compute(model):
    sources = model["sources"]
    var_of = {source[0]: index for index, source in enumerate(sources)}
    nvars = len(sources)
    bdd = _BDD(nvars)

    nodes = model["nodes"]
    node_position = {node: index for index, node in enumerate(nodes)}
    node_count = len(nodes)

    records = []
    for query in model["queries"]:
        conditioned = dict(query["condition"])
        free = [
            (var_of[source_id], numerator, denominator, source_id)
            for source_id, numerator, denominator in sources
            if source_id not in conditioned
        ]
        free_vars = [info[0] for info in free]
        free_position = {var: index for index, var in enumerate(free_vars)}

        activation = {}
        for source_id, _, _ in sources:
            if source_id in conditioned:
                activation[source_id] = 1 if conditioned[source_id] else 0
            else:
                activation[source_id] = bdd.variable(var_of[source_id])

        selected = query["event_types"]
        incoming = [[] for _ in range(node_count)]
        for d1, d2, event_type, source_id in model["edges"]:
            if selected and event_type not in selected:
                continue
            act = activation[source_id]
            if act == 0:
                continue
            incoming[node_position[d2]].append((node_position[d1], act))

        layers = _layer_stack(
            bdd, node_count, incoming, node_position[query["start"]]
        )
        root = layers[-1][node_position[query["end"]]]

        condition_probability_zero = False
        for source_id, value in query["condition"]:
            index = var_of[source_id]
            numerator, denominator = sources[index][1], sources[index][2]
            if (value and numerator == 0) or (not value and numerator == denominator):
                condition_probability_zero = True
                break

        # Inclusion-minimal supports: M = F AND over free s of
        # (NOT s OR NOT F[s=0]), and every conditioned bit forced false.
        minimal = root
        for var in free_vars:
            reduced = bdd.cofactor(root, var, False)
            if reduced == 0:
                continue
            minimal = bdd.AND(minimal, bdd.OR(bdd.mk(var, 1, 0), bdd.NOT(reduced)))
            if minimal == 0:
                break
        if minimal != 0:
            for source_id in conditioned:
                minimal = bdd.AND(minimal, bdd.mk(var_of[source_id], 1, 0))
                if minimal == 0:
                    break

        # Project the family onto the free bits for counting and ranking.
        family = minimal
        for source_id in conditioned:
            if family > 1:
                family = bdd.cofactor(family, var_of[source_id], False)

        support_count = _sat_count(bdd, root, free_vars, free_position)
        minimal_count = _sat_count(bdd, family, free_vars, free_position)

        if family == 0:
            min_size = max_size = None
            critical = []
            ranked = [{"rank": text, "sources": None} for text in query["ranks"]]
        else:
            sizes = _family_sizes(bdd, family)
            min_size, max_size = sizes
            _, forced_vars = _critical_variables(bdd, family)
            critical = sorted(
                source_id
                for var, _, _, source_id in free
                if var in forced_vars
            )
            selector = _RankSelector(bdd, family, free_vars)
            ranked = []
            for text in query["ranks"]:
                chosen = selector.select(0, family, int(text))
                entry = {"rank": text, "sources": None}
                if chosen is not None:
                    entry["sources"] = sorted(free[at][3] for at in chosen)
                ranked.append(entry)

        probability, sensitivities = _reliability(
            bdd, root, free, condition_probability_zero
        )

        records.append(
            {
                "query": query,
                "layers": layers,
                "root": root,
                "minimal": minimal,
                "support_count": support_count,
                "minimal_count": minimal_count,
                "min_size": min_size,
                "max_size": max_size,
                "critical": critical,
                "ranked": ranked,
                "probability": probability,
                "probability_state": (
                    "UNDEFINED" if condition_probability_zero else "DEFINED"
                ),
                "sensitivities": sensitivities,
            }
        )
        bdd.c_cof.clear()
        bdd.trim_caches()

    # ---- certificate serialisation ---------------------------------------
    referenced = []
    for record in records:
        referenced.append(record["root"])
        referenced.append(record["minimal"])
        for layer in record["layers"]:
            referenced.extend(layer)

    reachable = set()
    stack = [node for node in referenced if node > 1]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        for child in (bdd.lo[node], bdd.hi[node]):
            if child > 1 and child not in reachable:
                stack.append(child)

    def final(node, mapping):
        return node if node < 2 else mapping[node]

    numbering = {}
    next_id = 2
    groups = {}
    for node in reachable:
        groups.setdefault(bdd.var[node], []).append(node)
    for var in range(nvars - 1, -1, -1):
        group = groups.get(var)
        if not group:
            continue
        group.sort(
            key=lambda n: (final(bdd.lo[n], numbering), final(bdd.hi[n], numbering))
        )
        for node in group:
            numbering[node] = next_id
            next_id += 1

    proof_nodes = []
    for node in sorted(reachable, key=lambda n: numbering[n]):
        proof_nodes.append(
            {
                "high": final(bdd.hi[node], numbering),
                "id": numbering[node],
                "low": final(bdd.lo[node], numbering),
                "var": bdd.var[node],
            }
        )

    def mapped(node):
        return node if node < 2 else numbering[node]

    proof_queries = []
    results = []
    for record in records:
        proof_queries.append(
            {
                "layers": [
                    [mapped(entry) for entry in layer] for layer in record["layers"]
                ],
                "minimal_root": mapped(record["minimal"]),
                "query_id": record["query"]["query_id"],
                "root": mapped(record["root"]),
            }
        )
        sensitivities = record["sensitivities"]
        results.append(
            {
                "critical_sources": record["critical"],
                "max_size": record["max_size"],
                "min_size": record["min_size"],
                "minimal_support_count": str(record["minimal_count"]),
                "probability": (
                    None
                    if record["probability"] is None
                    else _render_fraction(record["probability"])
                ),
                "probability_state": record["probability_state"],
                "query_id": record["query"]["query_id"],
                "ranked_supports": record["ranked"],
                "sensitivities": {
                    key: (None if value is None else _render_fraction(value))
                    for key, value in sorted(sensitivities.items())
                },
                "support_count": str(record["support_count"]),
            }
        )

    proof = {
        "nodes": proof_nodes,
        "queries": proof_queries,
        "variables": [source[0] for source in sources],
        "version": 1,
    }
    report = {"proof_sha256": "", "results": results, "version": 1}

    proof_bytes = (
        json.dumps(proof, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    report["proof_sha256"] = hashlib.sha256(proof_bytes).hexdigest()
    report_bytes = (
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return proof_bytes, report_bytes


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _atomic_write(path, body):
    handle, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=".ddi-", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(prog="ddi-lineage")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        model = parse_input(_load_document(args.input))
        proof_bytes, report_bytes = compute(model)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(args.out_dir / "proof.json", proof_bytes)
        _atomic_write(args.out_dir / "report.json", report_bytes)
    except Fatal as error:
        print(str(error), file=sys.stderr)
        return 1
    except RecursionError:
        print("symbolic evaluation exceeded the recursion budget", file=sys.stderr)
        return 1
    except MemoryError:
        print("symbolic evaluation exceeded the memory budget", file=sys.stderr)
        return 1
    except Exception as error:  # pragma: no cover - defensive
        print("fatal: %s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
