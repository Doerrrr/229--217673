#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_curate.py /opt/ddi-curator/curate.py
install -m 0644 /solution/oracle_publication.py /opt/ddi-curator/publication.py

/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --out-dir /output

/usr/local/bin/ddi-curate \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --out-dir /output/releases-store --release-id batch_a --expected-parent NONE
