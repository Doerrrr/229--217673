#!/bin/bash
set -uo pipefail

REWARD_DIR="/logs/verifier"
REWARD_FILE="${REWARD_DIR}/reward.txt"
DETAILS_FILE="${REWARD_DIR}/details.json"

mkdir -p "${REWARD_DIR}"
chmod 0700 /tests "${REWARD_DIR}"
if [ -d /solution ]; then chmod 0700 /solution; fi
# Candidates execute in child processes without access to hidden source/rewards.
# The trusted root supervisor reads expected state and alone writes the reward.
printf '0' > "${REWARD_FILE}"

python3 /tests/test_outputs.py \
  --reward-file "${REWARD_FILE}" \
  --details-file "${DETAILS_FILE}"

exit 0
