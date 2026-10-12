#!/usr/bin/env python3
"""Legacy publisher. It predates evidence-key bridge auditing and generations."""

import argparse
import csv
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("drugs", "events", "interactions", "drug-changes",
                 "event-changes", "interaction-changes", "out-dir"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # This legacy job advertises a release before its products are complete.
    (out / "CURRENT").write_text("legacy\n", encoding="ascii")
    command = ["/usr/local/bin/ddi-curate"]
    for name in ("drugs", "events", "interactions", "drug-changes",
                 "event-changes", "interaction-changes"):
        command.extend(["--" + name, getattr(args, name.replace("-", "_"))])
    command.extend(["--out-dir", str(out)])
    subprocess.run(command, check=True)
    with (out / "interactions_clean.csv").open(newline="", encoding="utf-8") as handle:
        pairs = {(row["d1"], row["d2"]) for row in csv.DictReader(handle)}
    (out / "bridge_evidence.csv").write_text(
        "evidence_index,d1,type,d2\n", encoding="utf-8")
    print(f"published {len(pairs)} undirected pairs")


if __name__ == "__main__":
    main()
