#!/usr/bin/env bash
# Stage the approved personal-repository task; never commit/push the platform.
set -euo pipefail
APPROVED_COMMIT=${1:?Pass the approved full personal commit SHA}
test "${#APPROVED_COMMIT}" -eq 40
git cat-file -e "$APPROVED_COMMIT^{commit}"
test -z "$(git status --porcelain)" || { echo 'STOP: 工作区有未提交修改'; exit 1; }
case "$(git remote get-url origin)" in
  https://github.com/cpoct-hlo/*) ;;
  *) echo 'STOP: origin 不是平台 cpoct-hlo 仓库'; exit 1 ;;
esac
test "$(git branch --show-current)" = main || { echo 'STOP: 当前不是 main'; exit 1; }
git fetch origin main
git merge --ff-only origin/main
BEFORE_WORKFLOW=$(git rev-parse HEAD:.github)
paths=(.gitattributes README.md instruction.md agent_prompt.txt task.toml
       environment/Dockerfile environment/app environment/bin environment/packet
       solution tests validation/ddi032_platform)
git restore --source="$APPROVED_COMMIT" --staged --worktree -- "${paths[@]}"
# Remove only obsolete task source trees; keep environment/data and .github intact.
git rm -r --ignore-unmatch -- environment/Makefile environment/src environment/upstream
git diff --cached --check
git diff --cached --exit-code -- .github
test "$(git write-tree | xargs -I '{}' git rev-parse '{}:.github')" = "$BEFORE_WORKFLOW"
git diff --cached --exit-code -- environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv
git diff --exit-code "$APPROVED_COMMIT" -- "${paths[@]}"
python3 validation/ddi032_platform/preflight.py
git status --short
echo "STAGED_OK: DDI-032 source=$APPROVED_COMMIT; 平台工作流和原始 CSV 未修改"
echo '请检查暂存差异后，自行 git commit 和 git push origin main。此脚本没有提交、推送或触发检测。'
