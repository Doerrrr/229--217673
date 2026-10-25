#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
rm -f /logs/verifier/reward.txt
python3 /tests/grade.py --project /work/bench --results /logs/verifier/details
