#!/bin/bash
set -euo pipefail
cd /opt/ddi-snapshot
g++ -std=c++20 -O2 -Wall -Wextra -Wpedantic -fPIC -shared -pthread \
  -I include src/*.cpp -o libddi.so
