"""Closed-form chain and one-cycle expectations for large graph workloads."""

from __future__ import annotations


def expected_row(n: int, a: int, b: int, key: int,
                 removed: int | None = None,
                 cycle: tuple[int, int] | None = None) -> list[int]:
    def component(v: int) -> tuple[int, int]:
        if removed is None:
            return 0, n
        if v <= removed:
            return 0, removed + 1
        return removed + 1, n - removed - 1

    def block(v: int) -> tuple[int, int]:
        if cycle is not None and cycle[0] <= v <= cycle[1]:
            return cycle[0], cycle[1] - cycle[0] + 1
        return v, 1

    ca, sa = component(a)
    cb, sb = component(b)
    ba, za = block(a)
    bb, zb = block(b)
    cc_count = 1 if removed is None else 2
    bridge_count = n - cc_count - (0 if cycle is None else cycle[1] - cycle[0])
    active = (1 <= key < n and key != (0 if removed is None else removed + 1)) \
        or (cycle is not None and key == n + 1)
    critical = active and 1 <= key < n and not (
        cycle is not None and cycle[0] <= key - 1 < cycle[1]
    )
    return [cc_count, bridge_count, cc_count + bridge_count,
            ca, sa, ba, za, cb, sb, bb, zb,
            int(ca == cb), int(ba == bb), int(active), int(critical)]


def workload(n: int, phases: int, family: str) -> tuple[list[tuple], list[list[int]]]:
    if family not in ("cut_restore", "local_cycles") or n < 72:
        raise ValueError("unsupported analytic family or size")
    operations = [("+", i + 1, i, i + 1) for i in range(n - 1)]
    answers: list[list[int]] = []
    for i in range(phases):
        a = (i * 7919 + 17) % (n - 70)
        b = a + 64
        if family == "cut_restore":
            cut = (i * 1543 + 41) % (n - 1)
            operations.append(("-", cut + 1))
            x = cut // 2 if i % 2 else cut
            y = cut + 1 + (n - cut - 2) // 2
            key = cut + 1 if i % 3 else max(1, cut)
            operations.append(("?", x, y, key))
            answers.append([len(answers)] + expected_row(n, x, y, key, removed=cut))
            operations.append(("+", cut + 1, cut, cut + 1))
            operations.append(("?", x, y, key))
            answers.append([len(answers)] + expected_row(n, x, y, key))
        else:
            operations.append(("+", n + 1, b, a))
            key = a + 1 if i % 3 else n + 1
            operations.append(("?", a + 1, b - 1, key))
            answers.append([len(answers)] + expected_row(
                n, a + 1, b - 1, key, cycle=(a, b)))
            operations.append(("-", n + 1))
            operations.append(("?", a + 1, b - 1, key))
            answers.append([len(answers)] + expected_row(n, a + 1, b - 1, key))
    return operations, answers
