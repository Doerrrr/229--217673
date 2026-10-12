#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
printf '0.000000\n' > /logs/verifier/reward.txt
python3 /tests/joint_score.py
exit 0
