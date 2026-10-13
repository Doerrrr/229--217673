#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
printf '0.000000\n' > /logs/verifier/reward.txt
python3 /tests/test_outputs.py
