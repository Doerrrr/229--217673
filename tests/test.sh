#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/grade031.py --project /work/ramsey --results /logs/verifier/ddi031
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('/logs/verifier/ddi031/result.json').read_bytes())
assert r['execution_status']=='NORMAL' and r['reward'] is not None
Path('/logs/verifier/reward.txt').write_text(str(r['reward'])+'\n')
PY
