#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/grade032.py --project /work/certificate --results /logs/verifier/eb032_math_m
python3 - <<'PY'
import json
from pathlib import Path
result=json.loads(Path('/logs/verifier/eb032_math_m/result.json').read_bytes())
assert result['execution_status']=='NORMAL' and result['reward'] is not None
Path('/logs/verifier/reward.txt').write_text(str(result['reward'])+'\n')
PY
