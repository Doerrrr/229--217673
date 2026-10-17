#!/usr/bin/env bash
set -euo pipefail
cp /solution/implementation/*.py /work/ramsey/app/
g++ -O3 -std=c++17 /solution/implementation/native.cpp -o /work/ramsey/app/ramsey-native
