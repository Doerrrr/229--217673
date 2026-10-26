#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/reward.json
python3 /tests/grade.py --project /work/bench --results /logs/verifier/details
