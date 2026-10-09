#!/bin/bash
set -uo pipefail

REWARD_DIR="/logs/verifier"
REWARD_FILE="${REWARD_DIR}/reward.txt"
DETAILS_FILE="${REWARD_DIR}/details.json"

mkdir -p "${REWARD_DIR}"
printf '0' > "${REWARD_FILE}"

python3 /tests/test_outputs.py \
  --reward-file "${REWARD_FILE}" \
  --details-file "${DETAILS_FILE}"

exit 0
