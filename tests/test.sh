#!/usr/bin/env bash
set -euo pipefail
phase=setup
report_failure() {
  failure_code=$?
  printf 'EB032_VERIFIER_FAILURE phase=%s exit_code=%s\n' "$phase" "$failure_code" >&2
  exit "$failure_code"
}
trap report_failure ERR
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
rm -f /logs/verifier/reward.txt
phase=candidate_and_exact_checks
python3 /tests/grade032.py --project /work/certificate --results /logs/verifier/eb032_math_m
phase=provenance
python3 /tests/provenance.py --results /logs/verifier/eb032_math_m
phase=reward
python3 /tests/report_reward.py --result /logs/verifier/eb032_math_m/result.json --reward /logs/verifier/reward.txt
