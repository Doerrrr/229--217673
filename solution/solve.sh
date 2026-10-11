#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_release.py /opt/ddi-release/release.py

/usr/local/bin/ddi-release \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --out-dir /output
