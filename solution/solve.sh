#!/bin/bash
set -euo pipefail
install -m 0644 /solution/oracle_lineage.py /app/lineage.py
ddi-lineage --input /data/evidence_graph.json --out-dir /output
