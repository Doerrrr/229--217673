"""Candidate-visible-style adapter from raw DDI updates to keyed graph updates.

This computes no graph components or bridges. A future task can provide this
adapter and ask the agent to implement the temporal graph engine separately.
"""

from __future__ import annotations

from collections import defaultdict


def translate(source: str) -> str:
    lines = source.splitlines()
    if not lines:
        raise ValueError("missing input")
    n, count = map(int, lines[0].split())
    if n <= 0 or count < 0 or len(lines) != count + 1:
        raise ValueError("invalid header or operation count")

    bindings: dict[int, tuple[int, int]] = {}
    events: dict[int, int] = {}
    assertions: dict[int, tuple[int, int, int]] = {}
    by_drug: dict[int, set[int]] = defaultdict(set)
    by_event: dict[int, set[int]] = defaultdict(set)
    output: list[str] = []

    def edge(key: int) -> tuple[int, int] | None:
        record = assertions.get(key)
        if record is None:
            return None
        left, kind, right = record
        a_state, a = bindings.get(left, (0, 0))
        b_state, b = bindings.get(right, (0, 0))
        if a_state != 1 or b_state != 1 or events.get(kind, 0) != 1:
            return None
        if left == right or a == b:
            return None
        return (min(a, b), max(a, b))

    def update(affected: set[int], mutation) -> None:
        before = {key: edge(key) for key in affected}
        mutation()
        for key in sorted(affected):
            old, new = before[key], edge(key)
            if old == new:
                continue
            if old is not None:
                output.append(f"- {key}")
            if new is not None:
                output.append(f"+ {key} {new[0]} {new[1]}")

    for line in lines[1:]:
        tokens = line.split()
        if not tokens:
            raise ValueError("blank operation")
        op = tokens[0]
        if op == "D" and len(tokens) == 4:
            raw, state, molecule = map(int, tokens[1:])
            if raw <= 0 or state not in range(4) or (state == 1 and not 0 <= molecule < n):
                raise ValueError("invalid drug update")
            if state != 1 and molecule != 0:
                raise ValueError("non-valid binding molecule must be zero")
            affected = by_drug[raw].copy()
            update(affected, lambda: bindings.__setitem__(raw, (state, molecule)))
        elif op == "E" and len(tokens) == 3:
            kind, state = map(int, tokens[1:])
            if kind < 0 or state not in range(3):
                raise ValueError("invalid event update")
            affected = by_event[kind].copy()
            update(affected, lambda: events.__setitem__(kind, state))
        elif op == "P" and len(tokens) == 5:
            key, left, kind, right = map(int, tokens[1:])
            if key <= 0 or left <= 0 or right <= 0 or kind < 0:
                raise ValueError("invalid assertion update")

            def replace() -> None:
                previous = assertions.get(key)
                if previous is not None:
                    old_left, old_kind, old_right = previous
                    by_drug[old_left].discard(key)
                    by_drug[old_right].discard(key)
                    by_event[old_kind].discard(key)
                assertions[key] = (left, kind, right)
                by_drug[left].add(key)
                by_drug[right].add(key)
                by_event[kind].add(key)

            update({key}, replace)
        elif op == "R" and len(tokens) == 2:
            key = int(tokens[1])
            if key <= 0:
                raise ValueError("invalid retraction")

            def retract() -> None:
                previous = assertions.pop(key, None)
                if previous is not None:
                    old_left, old_kind, old_right = previous
                    by_drug[old_left].discard(key)
                    by_drug[old_right].discard(key)
                    by_event[old_kind].discard(key)

            update({key}, retract)
        elif op == "Q" and len(tokens) == 4:
            a, b, key = map(int, tokens[1:])
            if not (0 <= a < n and 0 <= b < n and key > 0):
                raise ValueError("invalid query")
            output.append(f"? {a} {b} {key}")
        else:
            raise ValueError(f"unknown or malformed operation: {op}")

    return f"{n} {len(output)}\n" + "".join(line + "\n" for line in output)
