#!/bin/bash
# User runs in the selected platform IDE. No commit, push, reset or workflow edit.
set -euo pipefail
APPROVED_COMMIT=${1:?Pass the approved full SHA}
cd /home/workspace/project
test "$(git rev-parse --show-toplevel)" = /home/workspace/project
test -z "$(git status --porcelain)" || {
  echo 'STOP: 工作区有未提交修改'; git status --short; exit 1;
}
TARGET=$(git remote get-url origin)
case "$TARGET" in
  https://github.com/cpoct-hlo/*) ;;
  *) echo 'STOP: origin不是平台仓库'; exit 1 ;;
esac
echo "平台目标：$TARGET"
git fetch origin main:refs/remotes/origin/main
git switch main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || {
  echo 'STOP: main有未推送提交'; exit 1;
}
git cat-file -e "$APPROVED_COMMIT^{commit}"
git restore --source="$APPROVED_COMMIT" --staged --worktree -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation
git diff --cached --check
git diff --cached --quiet -- .github || { echo 'STOP: 平台工作流改变'; exit 1; }
git diff --cached --exit-code "$APPROVED_COMMIT" -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation
git diff --exit-code -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation
python3 validation/cohort_platform/preflight.py
git diff --cached --name-status
echo "SYNC_READY: source=$APPROVED_COMMIT；尚未commit/push，平台工作流保留"
