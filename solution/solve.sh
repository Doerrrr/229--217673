#!/bin/bash
set -euo pipefail
cp /solution/src/*.c /solution/src/cohort.h /work/cohort-release/src/
cp /solution/app/*.py /work/cohort-release/app/
cd /work/cohort-release
make -B
