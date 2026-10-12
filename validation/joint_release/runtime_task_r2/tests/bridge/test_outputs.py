"""Trusted behavioral scorer; candidate C++ runs in unprivileged processes."""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import resource
import subprocess
import tempfile
import time

from analytic_cases import workload
from check_graph import expected as expected_graph
from temporal_standard import expected_panel


APP = Path("/opt/ddi-bridge")
LOG = Path("/logs/verifier")
WEIGHTS = [
    ("connected_components", 0.15),
    ("individual_bridges", 0.15),
    ("two_edge_blocks", 0.15),
    ("key_replacement_retraction", 0.10),
    ("raw_ddi_reclassification", 0.10),
    ("bounded_temporal_throughput", 0.35),
]
assert abs(sum(weight for _, weight in WEIGHTS) - 1.0) < 1e-12


def restricted(cpu_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (1_610_612_736, 1_610_612_736))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16_777_216, 16_777_216))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def run_child(command: list[str], payload: bytes | None, *, timeout: int,
              cpu_seconds: int, engine: Path | None = None) -> tuple[bytes, float]:
    with tempfile.TemporaryDirectory(prefix="ddi-bridge-child-") as folder:
        root = Path(folder)
        os.chown(root, 65534, 65534)
        os.chmod(root, 0o700)
        with (root / "stdout").open("wb") as out, (root / "stderr").open("wb") as err:
            env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
            if engine is not None:
                env["DDI_BRIDGE_ENGINE"] = str(engine)
            started = time.monotonic()
            result = subprocess.run(
                command, input=payload, stdout=out, stderr=err, cwd=root,
                env=env, timeout=timeout,
                preexec_fn=lambda: restricted(cpu_seconds), check=False,
            )
        elapsed = time.monotonic() - started
        error = (root / "stderr").read_bytes()[:2000].decode("utf-8", errors="replace")
        assert result.returncode == 0, f"exit {result.returncode}: {error}"
        return (root / "stdout").read_bytes(), elapsed


def compile_engine() -> Path:
    build = Path(tempfile.mkdtemp(prefix="ddi-bridge-build-"))
    os.chown(build, 65534, 65534)
    os.chmod(build, 0o755)
    output = build / "bridge-index"
    sources = sorted((APP / "src").glob("*.cpp"))
    assert sources, "no submitted C++ sources"
    run_child(
        ["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Wpedantic",
         "-pthread", *map(str, sources), "-o", str(output)],
        None, timeout=150, cpu_seconds=140,
    )
    assert output.is_file()
    return output


def encode(n: int, operations: list[tuple]) -> bytes:
    return (f"{n} {len(operations)}\n" + "".join(
        " ".join(map(str, op)) + "\n" for op in operations
    )).encode("ascii")


def parse_rows(data: bytes, expected_count: int) -> list[list[int]]:
    lines = data.decode("ascii").splitlines()
    assert len(lines) == expected_count, f"got {len(lines)} rows, expected {expected_count}"
    result = []
    for line in lines:
        words = line.split()
        assert len(words) == 16, f"expected 16 integers; got {len(words)}"
        assert all(word.isascii() and word.lstrip("-").isdecimal() for word in words)
        result.append([int(word) for word in words])
    return result


def direct_cases() -> list[tuple[int, list[tuple]]]:
    cases = [
        (4, [("?", 0, 3, 1), ("+", 1, 0, 1), ("+", 2, 1, 2),
             ("?", 0, 2, 1), ("+", 3, 2, 0), ("?", 0, 2, 1),
             ("-", 3), ("?", 0, 2, 2), ("+", 4, 1, 0),
             ("?", 0, 1, 1), ("-", 1), ("?", 0, 1, 4),
             ("+", 4, 2, 3), ("?", 0, 3, 4),
             ("+", 4, 3, 3), ("?", 3, 3, 4)]),
        (3, [("+", 1, 0, 1), ("+", 2, 1, 0), ("?", 0, 1, 1),
             ("-", 2), ("?", 0, 1, 1), ("-", 1), ("?", 0, 1, 1)]),
    ]
    for seed in range(12):
        rng = random.Random(seed)
        n = rng.randrange(3, 16)
        ops = []
        for _ in range(150):
            kind = rng.randrange(10)
            if kind < 5:
                ops.append(("+", rng.randrange(1, 25), rng.randrange(n), rng.randrange(n)))
            elif kind < 7:
                ops.append(("-", rng.randrange(1, 25)))
            else:
                ops.append(("?", rng.randrange(n), rng.randrange(n), rng.randrange(1, 25)))
        cases.append((n, ops))
    return cases


def compare_columns(actual: list[list[int]], wanted: list[list[int]], columns: tuple[int, ...]) -> None:
    assert len(actual) == len(wanted)
    for i, (got, expect) in enumerate(zip(actual, wanted)):
        assert all(got[column] == expect[column] for column in columns), (
            i, [got[c] for c in columns], [expect[c] for c in columns]
        )


def check_direct(engine: Path, columns: tuple[int, ...]) -> None:
    for n, ops in direct_cases():
        wanted = expected_graph(n, ops)
        output, _ = run_child([str(engine)], encode(n, ops), timeout=30, cpu_seconds=30)
        actual = parse_rows(output, len(wanted))
        compare_columns(actual, wanted, columns)


def check_key_updates(engine: Path) -> None:
    n = 3
    ops = [
        ("+", 7, 0, 1), ("?", 0, 1, 7),
        ("+", 7, 1, 2), ("?", 0, 1, 7),
        ("-", 99), ("?", 1, 2, 7),
        ("-", 7), ("?", 1, 2, 7),
        ("-", 7), ("+", 7, 0, 2), ("?", 0, 2, 7),
    ]
    wanted = expected_graph(n, ops)
    output, _ = run_child([str(engine)], encode(n, ops), timeout=30, cpu_seconds=30)
    actual = parse_rows(output, len(wanted))
    compare_columns(actual, wanted, (14,))


def check_raw_ddi(engine: Path) -> None:
    n = 3
    ops = [
        ("D", 1, 1, 0), ("D", 2, 1, 1), ("D", 3, 1, 2),
        ("E", 0, 1), ("P", 11, 1, 0, 2), ("P", 12, 2, 0, 3),
        ("Q", 0, 2, 11), ("P", 13, 2, 0, 1), ("Q", 0, 2, 11),
        ("D", 2, 1, 0), ("Q", 0, 2, 11), ("E", 0, 2),
        ("Q", 0, 2, 11), ("E", 0, 1), ("D", 2, 1, 1),
        ("Q", 0, 2, 13), ("R", 13), ("Q", 0, 2, 12),
    ]
    wanted = expected_panel(n, ops)
    output, _ = run_child(
        ["python", str(APP / "client.py")], encode(n, ops),
        timeout=30, cpu_seconds=30, engine=engine,
    )
    actual = parse_rows(output, len(wanted))
    compare_columns(actual, wanted, (1, 2, 3, 14, 15))


def check_throughput(engine: Path) -> list[dict]:
    measurements = []
    for family in ("cut_restore", "local_cycles"):
        n, phases = 60_000, 20_000
        ops, wanted = workload(n, phases, family)
        output, elapsed = run_child(
            [str(engine)], encode(n, ops), timeout=45, cpu_seconds=120,
        )
        actual = parse_rows(output, len(wanted))
        assert actual == wanted, f"{family} large output mismatch"
        measurements.append({"family": family, "vertices": n,
                             "operations": len(ops), "queries": len(wanted),
                             "elapsed_sec": round(elapsed, 3)})
    return measurements


def main() -> None:
    started = time.monotonic()
    LOG.mkdir(parents=True, exist_ok=True)
    checks = []
    try:
        engine = compile_engine()
        build_error = None
    except Exception as exc:
        engine = None
        build_error = f"{type(exc).__name__}: {exc}"[:1000]
    for name, weight in WEIGHTS:
        group_start = time.monotonic()
        error = build_error
        measurements = None
        if engine is not None:
            try:
                if name == "connected_components":
                    check_direct(engine, (0, 1, 4, 5, 8, 9, 12))
                elif name == "individual_bridges":
                    check_direct(engine, (2, 15))
                elif name == "two_edge_blocks":
                    check_direct(engine, (3, 6, 7, 10, 11, 13))
                elif name == "key_replacement_retraction":
                    check_key_updates(engine)
                elif name == "raw_ddi_reclassification":
                    check_raw_ddi(engine)
                elif name == "bounded_temporal_throughput":
                    measurements = check_throughput(engine)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:2000]
        item = {"name": name, "weight": weight, "passed": error is None,
                "error": error, "elapsed_sec": round(time.monotonic() - group_start, 3)}
        if measurements is not None:
            item["measurements"] = measurements
        checks.append(item)
        print(json.dumps(item), flush=True)
    reward = round(sum(item["weight"] for item in checks if item["passed"]), 6)
    details = {"checks": checks, "reward": reward,
               "elapsed_sec": round(time.monotonic() - started, 3),
               "verifier_completed": True, "scoring": "independent additive groups"}
    (LOG / "details.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    (LOG / "reward.txt").write_text(f"{reward:.6f}\n", encoding="ascii")
    print(json.dumps({"reward": reward, "elapsed_sec": details["elapsed_sec"]}), flush=True)


if __name__ == "__main__":
    main()
