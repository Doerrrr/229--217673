#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_release.py /opt/ddi-release/release.py
install -m 0644 /solution/screen_optimizer.py /opt/ddi-release/screen_optimizer.py

/usr/local/bin/ddi-release \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --screen-plan /data/screen_plan.json \
  --out-dir /output
