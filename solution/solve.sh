#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_curate.py /opt/ddi-curator/curate.py
install -m 0755 /solution/ddi-curate /usr/local/bin/ddi-curate

/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --withdrawals /data/withdrawals.csv \
  --out-dir /output
