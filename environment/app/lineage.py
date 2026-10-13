#!/usr/bin/env python3
"""Repair this command according to instruction.md; use Python 3.11 stdlib."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="ddi-lineage")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        args.input.read_bytes()
        raise NotImplementedError("symbolic evidence lineage has not been implemented")
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
