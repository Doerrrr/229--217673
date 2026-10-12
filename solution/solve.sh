#!/bin/bash
set -euo pipefail
cp /solution/reference.cpp /opt/ddi-snapshot/src/ddi_snapshot.cpp
/opt/ddi-snapshot/build.sh
