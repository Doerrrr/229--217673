#!/bin/bash
# Only stages the approved package in the user's selected platform IDE.
set -euo pipefail
APPROVED_COMMIT=${1:?Pass the verified full source SHA}
[[ "$APPROVED_COMMIT" =~ ^[a-f0-9]{40}$ ]] || { echo 'STOP: SHA格式错误'; exit 1; }
cd /home/workspace/project
test "$(git rev-parse --show-toplevel)" = /home/workspace/project
test -z "$(git status --porcelain)" || { echo 'STOP: 工作区不干净'; git status --short; exit 1; }
TARGET=$(git remote get-url origin)
[[ "$TARGET" =~ ^https://github.com/cpoct-hlo/229--[0-9]+(\.git)?$ ]] || { echo 'STOP: origin不是平台题目仓库'; exit 1; }
echo "平台目标：$TARGET"
git fetch origin main:refs/remotes/origin/main
git switch main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || { echo 'STOP: main有未推送提交'; exit 1; }
git cat-file -e "$APPROVED_COMMIT^{commit}"
git restore --source="$APPROVED_COMMIT" --staged --worktree -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation review \
  ':(exclude)environment/data/drug_list.csv' \
  ':(exclude)environment/data/DDI_event.csv' \
  ':(exclude)environment/data/newddi.csv'
git diff --cached --check
git diff --cached --quiet -- .github environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv || {
  echo 'STOP: 工作流或原始CSV改变'; exit 1;
}
git diff --cached --exit-code "$APPROVED_COMMIT" -- \
  .gitattributes README.md instruction.md task.toml environment solution tests validation review \
  ':(exclude)environment/data/drug_list.csv' \
  ':(exclude)environment/data/DDI_event.csv' \
  ':(exclude)environment/data/newddi.csv'
git diff --exit-code -- .gitattributes README.md instruction.md task.toml environment solution tests validation review
python3 validation/dual_platform/preflight.py
git diff --cached --name-status
echo "SYNC_READY: DDI-019 v02 source=$APPROVED_COMMIT；题包一致，工作流及原始CSV保留，尚未commit/push"
