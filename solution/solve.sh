#!/bin/bash
set -euo pipefail
cp /solution/src/*.c /solution/src/cohort.h /work/cohort-release/src/
cd /work/cohort-release
make -B
