#!/usr/bin/env bash
set -euo pipefail
cp /solution/implementation/*.py /work/phase/app/
python3 /work/phase/clients/check_legacy.py
