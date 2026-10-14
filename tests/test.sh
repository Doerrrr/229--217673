#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/test_outputs.py
