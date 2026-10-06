#!/bin/bash

# 修复 bug 1
sed -i 's/G = 6.674e-10/G = 6.674e-11/' /app/simulation.py

# 验证修复
python3 /app/simulation.py