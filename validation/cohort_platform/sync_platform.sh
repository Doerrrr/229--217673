#!/bin/bash
# Run only in the user-selected remote platform workspace, never locally.
set -euo pipefail
APPROVED_COMMIT=${1:?Pass the approved full commit SHA}
cd /home/workspace/project
test "$(git rev-parse --show-toplevel)" = /home/workspace/project || { echo 'STOP: unexpected workspace'; exit 1; }
test -z "$(git status --porcelain)" || { echo 'STOP: uncommitted changes'; git status --short; exit 1; }
TARGET=$(git remote get-url origin)
case "$TARGET" in
  https://github.com/cpoct-hlo/229--[0-9]*|https://github.com/cpoct-hlo/229--[0-9]*.git) ;;
  *) echo 'STOP: origin is not a cpoct-hlo platform repository'; exit 1 ;;
esac
echo "Platform target: $TARGET"
git cat-file -e "$APPROVED_COMMIT^{commit}"
git fetch origin main:refs/remotes/origin/main
git switch main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || { echo 'STOP: local main has extra commits'; exit 1; }
BASE=$(git rev-parse HEAD)
git restore --source="$APPROVED_COMMIT" --staged --worktree -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation \
  ':(exclude)environment/data/*.csv'
git diff --cached --check
test -z "$(git diff --cached --name-only -- .github environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv)" || {
  echo 'STOP: workflow or original CSV changed'; exit 1;
}
python3 validation/cohort_platform/preflight.py
git diff --cached --name-status
if ! git diff --cached --quiet; then
  git commit -m 'Publish DDI-018 platform v02 with validated Oracle and NOP'
fi
git push origin HEAD:main
test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$(git rev-parse HEAD)" || { echo 'STOP: remote SHA mismatch'; exit 1; }
git diff --exit-code "$APPROVED_COMMIT" HEAD -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation \
  ':(exclude)environment/data/*.csv'
git diff --exit-code "$BASE" HEAD -- .github environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv
test -z "$(git status --porcelain)" || { echo 'STOP: workspace not clean after push'; exit 1; }
echo "SYNC_OK: source=$APPROVED_COMMIT platform=$(git rev-parse HEAD); platform workflow and original CSV preserved"
