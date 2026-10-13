"""Pure input construction and frozen business mapping; no answer engine."""

from fractions import Fraction


def edge(name, d1, d2, source, event_type=5):
    return {"edge_id": name, "d1": d1, "d2": d2, "source_id": source, "type": event_type}


def query(name, start, end, condition=(), types=(), ranks=("0", "1", "99")):
    return {"query_id": name, "start": start, "end": end, "condition": list(condition),
            "event_types": list(types), "ranks": list(ranks)}


def graph(nodes, sources, edges, queries):
    return {"version": 1, "nodes": nodes,
            "sources": [{"source_id": name, "numerator": p.numerator, "denominator": p.denominator}
                        for name, p in sources], "edges": edges, "queries": queries}


def diamond(shared=False, rational=False):
    ps = [Fraction(1, 3), Fraction(2, 7), Fraction(3, 5), Fraction(4, 9)] if rational else [Fraction(1, 2)] * 4
    names = "abc" if shared else "abcd"
    return graph(["DBA", "DBB", "DBC", "DBD"], list(zip(names, ps)),
                 [edge("ab", "DBA", "DBB", "a"), edge("bd", "DBB", "DBD", "b"),
                  edge("ac", "DBA", "DBC", "a" if shared else "c"),
                  edge("cd", "DBC", "DBD", "c" if shared else "d")],
                 [query("q", "DBA", "DBD")])


def cycle_fixture():
    return graph(["DBA", "DBB", "DBC", "DBD", "DBX", "DBY"],
                 [(name, Fraction(1, 2)) for name in "abcd"],
                 [edge("ab", "DBA", "DBB", "a"), edge("bc", "DBB", "DBC", "b"),
                  edge("cb", "DBC", "DBB", "c"), edge("cd", "DBC", "DBD", "d"),
                  edge("xy", "DBX", "DBY", "a"), edge("yx", "DBY", "DBX", "b")],
                 [query("grounded", "DBA", "DBD"), query("ungrounded", "DBA", "DBX"),
                  query("reverse", "DBD", "DBA")])


def directed_fixture():
    return graph(["DBA", "DBB", "DBC"], [(x, Fraction(1, 2)) for x in "abc"],
                 [edge("ab5", "DBA", "DBB", "a", 5), edge("bc6", "DBB", "DBC", "b", 6),
                  edge("ba5", "DBB", "DBA", "c", 5), edge("loop", "DBC", "DBC", "a", 5)],
                 [query("all", "DBA", "DBC"), query("five", "DBA", "DBC", types=[5]),
                  query("back", "DBB", "DBA", types=[5]), query("self", "DBC", "DBC")])


def unequal_fixture():
    return graph(["DBA", "DBB", "DBC", "DBD"], [(x, Fraction(1, 2)) for x in "abcde"],
                 [edge("direct", "DBA", "DBD", "a"), edge("ab", "DBA", "DBB", "b"),
                  edge("bd", "DBB", "DBD", "c"), edge("ac", "DBA", "DBC", "d"),
                  edge("cd", "DBC", "DBD", "e")],
                 [query("q", "DBA", "DBD", ranks=("0", "1", "2", "3", "999999999999999999999999"))])


def rank_fixture():
    return graph(["DBA", "DBB", "DBC", "DBD"], [(x, Fraction(1, 2)) for x in "abcde"],
                 [edge("ab_a", "DBA", "DBB", "a"), edge("bd_b", "DBB", "DBD", "b"),
                  edge("ac_a", "DBA", "DBC", "a"), edge("cd_c", "DBC", "DBD", "c"),
                  edge("ac_d", "DBA", "DBC", "d"), edge("cd_e", "DBC", "DBD", "e")],
                 [query("q", "DBA", "DBD", ranks=("3", "0", "2", "1", "10"))])


def irrelevant_fixture():
    return graph(["DBA", "DBB"], [(x, Fraction(1, 2)) for x in "abcdef"],
                 [edge("ab", "DBA", "DBB", "a")],
                 [query("q", "DBA", "DBB"), query("fixed", "DBA", "DBB",
                    condition=[{"source_id": "b", "value": True}])])


def empty_fixture():
    return graph(["DBA", "DBB"], [], [],
                 [query("self", "DBA", "DBA"), query("unreachable", "DBA", "DBB")])


def endpoint_probabilities():
    return graph(["DBA", "DBB", "DBC"], [("a", Fraction(0)), ("b", Fraction(1)), ("c", Fraction(1, 3))],
                 [edge("ab", "DBA", "DBB", "a"), edge("bc", "DBB", "DBC", "b"),
                  edge("ac", "DBA", "DBC", "c")],
                 [query("normal", "DBA", "DBC"), query("impossible", "DBA", "DBC",
                    condition=[{"source_id": "a", "value": True}])])


def serial_fixture(k, variant="base"):
    variables = [f"e{i:02d}{letter}" for i in range(k) for letter in ("a", "b")]
    names = [f"DBL{i:03d}" for i in range(k + 1)]
    sources = [(name, Fraction(1, 3) if name.endswith("a") else Fraction(2, 7))
               if variant == "rational" else (name, Fraction(1, 2)) for name in variables]
    edges = [edge(f"obs{i:02d}{letter}", names[i], names[i + 1], f"e{i:02d}{letter}",
                  6 if variant == "multi" and i % 3 == 2 else 5)
             for i in range(k) for letter in ("a", "b")]
    ranks = tuple(dict.fromkeys(("0", "1", str(2**k - 1), str(2**k), "9" * 128)))
    qs = [query("serial", names[0], names[-1], ranks=ranks)]
    if variant == "conditioned":
        qs[0]["condition"] = [{"source_id": "e00a", "value": True},
                              {"source_id": "e01b", "value": False}]
    elif variant == "multi":
        qs += [query("interval", names[4], names[15], ranks=("0", "1", "999999")),
               query("self", names[7], names[7]), query("reverse", names[-1], names[0]),
               query("five", names[0], names[-1], types=[5]),
               query("six", names[2], names[3], types=[6])]
    return graph(names, sources, edges, qs)


def shared_guard_fixture(k=40):
    names = [f"DBG{i:03d}" for i in range(k + 1)]
    sources = [("a", Fraction(1, 2))] + [(f"b{i:02d}", Fraction(1, 2)) for i in range(k)]
    edges = [edge(f"common{i:02d}", names[i], names[i + 1], "a") for i in range(k)]
    edges += [edge(f"local{i:02d}", names[i], names[i + 1], f"b{i:02d}") for i in range(k)]
    return graph(names, sources, edges, [query("shared", names[0], names[-1], ranks=("0", "1", "2"))])


def scored_cases():
    conditioned = diamond(shared=True, rational=True)
    conditioned["queries"] += [query("fixed_true", "DBA", "DBD", condition=[{"source_id": "a", "value": True}]),
                               query("fixed_false", "DBA", "DBD", condition=[{"source_id": "b", "value": False}])]
    impossible = endpoint_probabilities()
    impossible["queries"] = [impossible["queries"][1]]
    return [
        ("independent_paths", "proof", diamond()),
        ("shared_source_paths", "proof", diamond(shared=True)),
        ("grounded_cycles", "proof", cycle_fixture()),
        ("direction_and_event_filter", "proof", directed_fixture()),
        ("compressed_80_source_family", "family", serial_fixture(40)),
        ("shared_guard_large_family", "family", shared_guard_fixture()),
        ("conditioned_large_family", "family", serial_fixture(40, "conditioned")),
        ("multi_query_large_family", "family", serial_fixture(32, "multi")),
        ("rational_large_family", "family", serial_fixture(24, "rational")),
        ("inclusion_not_minimum_size", "family", unequal_fixture()),
        ("lexicographic_ranks", "family", rank_fixture()),
        ("irrelevant_source_dimensions", "family", irrelevant_fixture()),
        ("empty_and_unreachable_supports", "family", empty_fixture()),
        ("exact_rational_probability", "probability", diamond(rational=True)),
        ("conditional_shared_probability", "probability", conditioned),
        ("zero_probability_condition", "probability", impossible),
        ("endpoint_hypothetical_sensitivity", "probability", endpoint_probabilities()),
    ]


CHECKS = [(name, section, .05) for name, section, _ in scored_cases()] + [
    ("canonical_permutation_determinism", "determinism", .05),
    ("fatal_input_nonclobber", "fatal", .05),
    ("cli_and_new_output_directory", "cli", .05),
]
assert len(CHECKS) == 20 and round(sum(item[2] for item in CHECKS), 6) == 1.0
