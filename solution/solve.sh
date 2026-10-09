#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_curate.py /opt/ddi-curator/curate.py
install -m 0755 /solution/ddi-curate /usr/local/bin/ddi-curate

/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --out-dir /output
