#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /tests /logs/verifier
python3 /tests/grade033.py --project /work/phase --results /logs/verifier/ddi033
python3 - <<'PY'
import json
from pathlib import Path
result=json.loads(Path('/logs/verifier/ddi033/result.json').read_bytes())
assert result['execution_status']=='NORMAL' and type(result['reward']) in (int,float), 'no valid score on an execution failure'
Path('/logs/verifier/reward.txt').write_text(str(result['reward'])+'\n')
PY
