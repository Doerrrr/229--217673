#!/bin/bash
set -euo pipefail

install -m 0755 /solution/oracle_curate.py /opt/ddi-curator/curate.py
install -m 0755 /solution/ddi-curate /usr/local/bin/ddi-curate
install -m 0644 /solution/bridge_reference.cpp /opt/ddi-bridge/src/bridge_index.cpp
install -m 0755 /solution/release_reference.py /opt/ddi-release/release.py
/opt/ddi-bridge/build.sh

/usr/local/bin/ddi-release-audit \
  --drugs /data/drug_list.csv \
  --events /data/DDI_event.csv \
  --interactions /data/newddi.csv \
  --drug-changes /data/drug_changes.csv \
  --event-changes /data/event_changes.csv \
  --interaction-changes /data/interaction_changes.csv \
  --out-dir /output
