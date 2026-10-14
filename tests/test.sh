#!/bin/bash
set -euo pipefail
trap 'status=$?; printf "VERIFIER_ENTRY_FAILURE line=%s status=%s\n" "$LINENO" "$status" >&2; exit "$status"' ERR
printf 'VERIFIER_ENTRY_START uid=%s gid=%s\n' "$(id -u)" "$(id -g)" >&2
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/test_outputs.py
