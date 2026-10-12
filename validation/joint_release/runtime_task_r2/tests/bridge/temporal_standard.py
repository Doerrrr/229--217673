"""Independent small-instance standard for the proposed temporal DDI audit.

All graph decisions are reconstructed from raw state and checked via
delete-one-key BFS in check_graph.py. There is no optimized candidate code or
answer lookup in this module.
"""

from __future__ import annotations

from check_graph import inspect


def expected_panel(n: int, operations: list[tuple]) -> list[list[int]]:
    if n <= 0:
        raise ValueError("n must be positive")
    bindings: dict[int, tuple[int, int]] = {}
    events: dict[int, int] = {}
    assertions: dict[int, tuple[int, int, int]] = {}
    results: list[list[int]] = []

    def current_edges() -> dict[int, tuple[int, int]]:
        edges: dict[int, tuple[int, int]] = {}
        for key, (left, kind, right) in assertions.items():
            left_state, left_mol = bindings.get(left, (0, 0))
            right_state, right_mol = bindings.get(right, (0, 0))
            if left_state != 1 or right_state != 1 or events.get(kind, 0) != 1:
                continue
            if left == right or left_mol == right_mol:
                continue
            edges[key] = (left_mol, right_mol)
        return edges

    for op in operations:
        name = op[0]
        if name == "D":
            _, raw, state, molecule = op
            if raw <= 0 or state not in range(4) or (state == 1 and not 0 <= molecule < n):
                raise ValueError("invalid drug operation")
            if state != 1 and molecule != 0:
                raise ValueError("non-valid binding must use molecule 0")
            bindings[raw] = (state, molecule)
        elif name == "E":
            _, kind, state = op
            if kind < 0 or state not in range(3):
                raise ValueError("invalid event operation")
            events[kind] = state
        elif name == "P":
            _, key, left, kind, right = op
            if key <= 0 or left <= 0 or right <= 0 or kind < 0:
                raise ValueError("invalid assertion operation")
            assertions[key] = (left, kind, right)
        elif name == "R":
            _, key = op
            if key <= 0:
                raise ValueError("invalid retraction")
            assertions.pop(key, None)
        elif name == "Q":
            _, a, b, key = op
            if not (0 <= a < n and 0 <= b < n and key > 0):
                raise ValueError("invalid query")
            results.append([len(results)] + inspect(n, current_edges(), a, b, key))
        else:
            raise ValueError(f"unknown operation: {name}")
    return results
