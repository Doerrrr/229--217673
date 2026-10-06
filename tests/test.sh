#!/bin/bash

REWARD_FILE="/logs/verifier/reward.txt"
mkdir -p /logs/verifier

# ====== 运行被测程序 ======
OUTPUT=$(python3 /app/simulation.py 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "0" > "$REWARD_FILE"
    cat "$REWARD_FILE"
    exit 0
fi

# ====== 数值验证（用 Python 比较浮点数）======
python3 << 'PYEOF'
import json, sys, subprocess

expected = {"energy_eV": -13.6, "wavelength_nm": 121.567}
tolerance = 0.001   # 0.1% 相对误差

result = subprocess.run(["python3", "/app/simulation.py"],
    capture_output=True, text=True, timeout=60)
actual = json.loads(result.stdout.strip())

all_pass = True
for key in expected:
    rel_err = abs(actual[key] - expected[key]) / abs(expected[key])
    if rel_err > tolerance: all_pass = False

sys.exit(0 if all_pass else 1)
PYEOF

if [ "$?" -eq 0 ]; then echo "1" > "$REWARD_FILE"
else echo "0" > "$REWARD_FILE"
fi

# ====== 反硬编码检查 ======
if grep -qE "13\.6|121\.567" /app/simulation.py; then
    echo "0" > "$REWARD_FILE"
fi

cat "$REWARD_FILE"