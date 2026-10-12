#!/bin/bash
set -euo pipefail
cd /opt/ddi-bridge
g++ -std=c++20 -O2 -Wall -Wextra -Wpedantic -pthread \
  src/bridge_index.cpp -o bridge-index
