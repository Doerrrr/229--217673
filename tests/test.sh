#!/bin/bash
set -euo pipefail
chmod 0700 /tests
mkdir -p /logs/verifier
python /tests/test_outputs.py
