#!/bin/bash
# User-run in the authorized remote IDE. No platform detection or force push.
set -euo pipefail
cd /home/workspace/project

SOURCE=f99fd220e3d5a6665547a1419e8a975c37e45c17
SOURCE_BRANCH=submission/ddi-incremental-baseline-20261013
PERSONAL=https://github.com/Doerrrr/229--217673.git
TARGET=https://github.com/cpoct-hlo/229--227194.git
RAW=(environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv)
CORE=(.gitattributes README.md environment instruction.md review solution task.toml tests)

echo '[1/6] Check clean workspace and exact platform target'
test "$(git rev-parse --show-toplevel)" = /home/workspace/project
test -z "$(git status --porcelain)" || { echo 'STOP: uncommitted changes'; git status --short; exit 1; }
case "$(git remote get-url origin)" in
  "$TARGET"|https://github.com/cpoct-hlo/229--227194) ;;
  *) echo 'STOP: origin is not the approved platform repository'; exit 1 ;;
esac
if git remote get-url myrepo >/dev/null 2>&1; then
  case "$(git remote get-url myrepo)" in
    "$PERSONAL"|https://github.com/Doerrrr/229--217673) ;;
    *) echo 'STOP: myrepo points to a different repository'; exit 1 ;;
  esac
else
  git remote add myrepo "$PERSONAL"
fi

echo '[2/6] Fetch the unchanged historical source and current platform main'
git fetch origin main:refs/remotes/origin/main
git fetch myrepo "$SOURCE_BRANCH:refs/remotes/myrepo/ddi-incremental-baseline"
test "$(git rev-parse refs/remotes/myrepo/ddi-incremental-baseline)" = "$SOURCE"
git switch main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || { echo 'STOP: local main has unpublished commits'; exit 1; }
BEFORE=$(git rev-parse HEAD)
echo "Preserved platform parent: $BEFORE"
git show -s --format='Historical source: %H %s' "$SOURCE"

echo '[3/6] Restore only task content; preserve the platform workflow'
git restore --source="$SOURCE" --staged --worktree -- "${CORE[@]}"
if test -n "$(git ls-files -- validation)"; then
  git restore --source="$SOURCE" --staged --worktree -- validation
fi
git restore --source="$BEFORE" --staged --worktree -- "${RAW[@]}"

echo '[4/6] Check source equality and protected assets'
git diff --cached --check
git diff --cached --quiet -- .github "${RAW[@]}" || { echo 'STOP: workflow or original data changed'; exit 1; }
git diff --cached --quiet "$SOURCE" -- .gitattributes README.md environment/app environment/bin instruction.md review solution task.toml tests || {
  echo 'STOP: core task differs from the historical source'; exit 1;
}
git diff --cached --quiet "$SOURCE" -- environment/data/drug_changes.csv environment/data/event_changes.csv environment/data/interaction_changes.csv || {
  echo 'STOP: change feeds differ from the historical source'; exit 1;
}
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import subprocess
import sys
for name in ('drug_list.csv', 'DDI_event.csv', 'newddi.csv'):
    relative = 'environment/data/' + name
    want = subprocess.check_output(['git', 'show', sys.argv[1] + ':' + relative])
    actual = Path(relative).read_bytes()
    assert actual.replace(b'\r\n', b'\n') == want.replace(b'\r\n', b'\n'), 'STOP: original data content differs: ' + name
print('PROTECTED_DATA_OK (only LF/CRLF normalization allowed)')
PY
grep -q '^schema_version = "1.3"$' task.toml
grep -q '^allow_internet = true$' task.toml
git diff --cached --name-status

echo '[5/6] Commit task restoration without rewriting history'
if ! git diff --cached --quiet; then
  git commit -m 'Restore unchanged incremental DDI baseline f99fd22 for controlled retest'
fi
PUBLISHED=$(git rev-parse HEAD)
git push origin HEAD:main

echo '[6/6] Verify remote main and clean local state'
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
test "$REMOTE" = "$PUBLISHED" || { echo 'STOP: remote main differs from the published commit'; exit 1; }
test -z "$(git status --porcelain)" || { echo 'STOP: workspace is not clean'; exit 1; }
git status -sb
echo "SYNC_OK: source=$SOURCE platform=$PUBLISHED previous=$BEFORE"
echo 'Historical T1 was DeepSeek=0.770, GLM=0.580; no new detection has been triggered.'
