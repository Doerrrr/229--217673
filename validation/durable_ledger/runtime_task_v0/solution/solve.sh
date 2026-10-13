#!/bin/bash
set -euo pipefail
cp /solution/reference_ledger.py /opt/ddi-ledger/ledger.py
chmod 0755 /opt/ddi-ledger/ledger.py /usr/local/bin/ddi-ledger
