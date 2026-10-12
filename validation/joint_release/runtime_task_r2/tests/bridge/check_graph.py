"""Author-only independent oracle: delete each keyed edge and use BFS.

Does not import the C++ bridge algorithm or any DDI candidate implementation.
"""
import argparse
import json
from pathlib import Path
import random
import subprocess
import time


def partitions(n, edges, excluded=frozenset()):
    adjacency = [[] for _ in range(n)]
    for key, (a, b) in edges.items():
        if key not in excluded:
            adjacency[a].append(b)
            adjacency[b].append(a)
    classes = [-1] * n
    sizes = [0] * n
    count = 0
    for start in range(n):
        if classes[start] >= 0:
            continue
        stack, members = [start], []
        classes[start] = start
        while stack:
            v = stack.pop()
            members.append(v)
            for w in adjacency[v]:
                if classes[w] < 0:
                    classes[w] = start
                    stack.append(w)
        for v in members:
            sizes[v] = len(members)
        count += 1
    return classes, sizes, count


def inspect(n, edges, a, b, key):
    cc, cc_size, count = partitions(n, edges)
    bridges = set()
    for edge_key, (x, y) in edges.items():
        without, _, _ = partitions(n, edges, frozenset([edge_key]))
        if without[x] != without[y]:
            bridges.add(edge_key)
    blocks, block_size, block_count = partitions(n, edges, bridges)
    return [count, len(bridges), block_count,
            cc[a], cc_size[a], blocks[a], block_size[a],
            cc[b], cc_size[b], blocks[b], block_size[b],
            int(cc[a] == cc[b]), int(blocks[a] == blocks[b]),
            int(key in edges), int(key in bridges)]


def expected(n, operations):
    edges, rows = {}, []
    for op in operations:
        if op[0] == '+':
            edges[op[1]] = (op[2], op[3])
        elif op[0] == '-':
            edges.pop(op[1], None)
        else:
            rows.append([len(rows)] + inspect(n, edges, op[1], op[2], op[3]))
    return rows


def run(executable, n, operations, timeout=30):
    text = f'{n} {len(operations)}\n' + ''.join(' '.join(map(str, op)) + '\n' for op in operations)
    answer = subprocess.run([executable], input=text, text=True, capture_output=True, timeout=timeout)
    if answer.returncode:
        raise AssertionError(f'reference exited {answer.returncode}: {answer.stderr[-2000:]}')
    return [list(map(int, line.split())) for line in answer.stdout.splitlines()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seeds', type=int, default=500)
    args = parser.parse_args()
    started = time.monotonic()
    manual = [
        (4, [('?', 0, 3, 1), ('+', 1, 0, 1), ('+', 2, 1, 2), ('?', 0, 2, 1),
             ('+', 3, 2, 0), ('?', 0, 2, 1), ('-', 3), ('?', 0, 2, 2),
             ('+', 4, 1, 0), ('?', 0, 1, 1), ('-', 1), ('?', 0, 1, 4),
             ('+', 4, 2, 3), ('?', 0, 3, 4), ('+', 4, 3, 3), ('?', 3, 3, 4)]),
        (3, [('+', 1, 0, 1), ('+', 2, 1, 0), ('?', 0, 1, 1),
             ('-', 2), ('?', 0, 1, 1), ('-', 1), ('?', 0, 1, 1)]),
        (2, [('+', 1, 0, 1), ('-', 1), ('+', 1, 0, 1), ('?', 0, 1, 1)]),
        (2, [('+', 1, 0, 1), ('-', 1)]),
    ]
    checked_queries = 0
    for ordinal, (n, ops) in enumerate(manual):
        want, got = expected(n, ops), run(args.executable, n, ops)
        assert got == want, ('manual', ordinal, got, want)
        checked_queries += len(want)
    for seed in range(args.seeds):
        rng = random.Random(seed)
        n = rng.randrange(2, 19)
        ops = []
        for _ in range(240):
            choice = rng.randrange(10)
            if choice < 5:
                ops.append(('+', rng.randrange(1, 29), rng.randrange(n), rng.randrange(n)))
            elif choice < 7:
                ops.append(('-', rng.randrange(1, 34)))
            else:
                ops.append(('?', rng.randrange(n), rng.randrange(n), rng.randrange(0, 34)))
        want, got = expected(n, ops), run(args.executable, n, ops)
        if got != want:
            for i, (a, b) in enumerate(zip(got, want)):
                if a != b:
                    raise AssertionError({'seed': seed, 'n': n, 'query': i, 'got': a, 'want': b, 'ops': ops})
            raise AssertionError({'seed': seed, 'length': [len(got), len(want)]})
        checked_queries += len(want)
    result = {'status': 'PASS', 'manual_cases': len(manual), 'independent_random_graphs': args.seeds,
              'queries': checked_queries, 'oracle': 'delete each individual key and BFS',
              'elapsed_sec': round(time.monotonic() - started, 3)}
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
