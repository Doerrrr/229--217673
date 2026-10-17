#!/usr/bin/env bash
# Stage the reviewed diagnostic revision only; never commit/push/trigger T1.
set -euo pipefail
APPROVED_COMMIT=${1:?Pass the full approved diagnostics commit SHA}
test "${#APPROVED_COMMIT}" -eq 40
git cat-file -e "$APPROVED_COMMIT^{commit}"
test -z "$(git status --porcelain)" || { echo 'STOP: 工作区有未提交修改'; exit 1; }
test "$(git branch --show-current)" = main || { echo 'STOP: 当前不是 main'; exit 1; }
case "$(git remote get-url origin)" in
  https://github.com/cpoct-hlo/*) ;;
  *) echo 'STOP: origin 不是预期的平台仓库'; exit 1 ;;
esac
python3 - "$APPROVED_COMMIT" <<'PY'
import hashlib, subprocess, sys
from pathlib import Path
sha=sys.argv[1]
fixed={
 'task.toml':'a5117cc1e57d8e52ca7405c7ba181e0a0949250d75180d0c0052ab4424c3a0d7',
 'tests/test.sh':'bf388f61a97451181b6d204a2b89b1e03de18e45fab48cff9b946c3723a69b29',
 'tests/graphs.py':'4bfdeb006748a2cd0d4f1ab403b906d0bcb788a084ddb16b899f86d1d5a28400',
 'tests/measure.py':'891c0d3f29bc76303c13043b8b8cab7bb703b7da85d7821fff9870eefd0e9e1b',
 'tests/cases031.json':'ce35c5be7ffd71e2d5b2250cd430c466f5805e5ada9a139b51995aa90bb03cf6',
}
for name,expected in fixed.items():
 assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,'STOP: different 031 baseline: '+name
base={'tests/common.py':'f2f42d3dc583ae3ce12ea9d1bda6a601d0a18204e3897ce77c1e2399dbcd93fd',
      'tests/grade031.py':'70c9b31fcdcc3c6e16d8acaf613a3d5a3398ca6bbf14e78d0d4a2ef2d74db333'}
actual={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in base}
approved={name:hashlib.sha256(subprocess.check_output(['git','show',sha+':'+name])).hexdigest() for name in base}
assert actual==base or actual==approved,'STOP: grader differs from reviewed baseline and diagnostics'
PY
BEFORE_WORKFLOW=$(git ls-tree HEAD -- .github)
paths=(tests/common.py tests/grade031.py tests/diagnostics.py
       validation/ddi031_platform/payload.json validation/ddi031_platform/adaptation.json
       validation/ddi031_platform/local_validation.json validation/ddi031_platform/platform_fields.md
       validation/ddi031_platform/sync_platform.sh validation/ddi031_diagnostics)
git restore --source="$APPROVED_COMMIT" --staged --worktree -- "${paths[@]}"
git -c core.whitespace=-blank-at-eof,cr-at-eol diff --cached --check
git diff --cached --exit-code -- .github task.toml environment solution tests/test.sh tests/cases031.json tests/graphs.py tests/measure.py instruction.md README.md agent_prompt.txt
test "$(git ls-tree "$(git write-tree)" -- .github)" = "$BEFORE_WORKFLOW"
git diff --cached --exit-code -- environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv
python3 validation/ddi031_platform/preflight.py
git status --short
echo "STAGED_OK: DDI-031 verifier diagnostics source=$APPROVED_COMMIT"
echo '题面、评分规则、实例、时限、工作流和CSV未改；只暂存，未commit/push/触发T1。'
