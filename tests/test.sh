#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/grade030.py --project /work/math --results /logs/verifier/ddi030
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('/logs/verifier/ddi030/result.json').read_bytes())
assert r['execution_status']=='NORMAL' and r['reward'] is not None
Path('/logs/verifier/reward.txt').write_text(str(r['reward'])+'\n')
PY
