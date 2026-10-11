#!/bin/bash
# Resume ONLY the staged 8023f518 synchronization stopped at the author preflight.
# Do not discard unrelated edits, import personal workflows or trigger evaluation.
(
  set -euo pipefail
  cd /home/workspace/project

  PREVIOUS_TASK=8023f518432b2f3534c2ac0f2a598650649265f3
  APPROVED_COMMIT=e54ff59cb6b67d9002ac2681828635e03900adab
  SYNC_PATHS=(.gitattributes README.md environment instruction.md review solution task.toml tests validation)
  RAW_PATHS=(environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv)

  echo '[1/4] 核对这次中断留下的暂存状态'
  test "$(git branch --show-current)" = main || { echo 'STOP: 当前不是 main'; exit 1; }
  case "$(git remote get-url origin)" in
    https://github.com/cpoct-hlo/229--224559|https://github.com/cpoct-hlo/229--224559.git) ;;
    *) echo 'STOP: origin 不是预期平台仓库'; exit 1 ;;
  esac
  case "$(git remote get-url myrepo)" in
    https://github.com/Doerrrr/229--217673|https://github.com/Doerrrr/229--217673.git) ;;
    *) echo 'STOP: myrepo 不是预期个人仓库'; exit 1 ;;
  esac
  git diff --quiet || { echo 'STOP: 出现额外的未暂存修改'; git status --short; exit 1; }
  test -z "$(git ls-files --others --exclude-standard)" || { echo 'STOP: 出现未跟踪文件'; git status --short; exit 1; }
  git diff --cached --quiet "$PREVIOUS_TASK" -- "${SYNC_PATHS[@]}" || {
    echo 'STOP: 暂存题包不是刚才的 8023f518，先发状态给我'; exit 1;
  }
  git diff --cached --quiet -- .github "${RAW_PATHS[@]}" || {
    echo 'STOP: 工作流或原始 CSV 有暂存改动'; exit 1;
  }
  git diff --cached --quiet -- . ':!.gitattributes' ':!README.md' ':!environment' ':!instruction.md' ':!review' ':!solution' ':!task.toml' ':!tests' ':!validation' || {
    echo 'STOP: 题包范围以外有暂存改动'; exit 1;
  }

  echo '[2/4] 拉取并安装只修作者预检的固定版本'
  git fetch origin main:refs/remotes/origin/main
  git fetch myrepo main:refs/remotes/myrepo/main
  test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || {
    echo 'STOP: 本地提交或平台 main 已变化'; exit 1;
  }
  PLATFORM_BASE=$(git rev-parse HEAD)
  git merge-base --is-ancestor "$APPROVED_COMMIT" myrepo/main
  git diff --quiet "$PREVIOUS_TASK" "$APPROVED_COMMIT" -- environment solution tests instruction.md task.toml .github || {
    echo 'STOP: 预检修复版本意外改了题目或工作流'; exit 1;
  }
  git restore --source="$APPROVED_COMMIT" --staged --worktree -- "${SYNC_PATHS[@]}"

  echo '[3/4] 重新运行保护检查'
  git diff --cached --check
  git diff --cached --quiet -- .github "${RAW_PATHS[@]}"
  python3 validation/check_boundary.py --self-test
  python3 validation/check_release_assets.py --platform --self-test
  git diff --cached --quiet "$APPROVED_COMMIT" -- "${SYNC_PATHS[@]}"
  git diff --quiet

  echo '[4/4] 提交、推送并核对'
  git commit -m 'Publish resource-constrained DDI release with portable asset preflight'
  git push origin main
  git diff --quiet "$APPROVED_COMMIT" HEAD -- "${SYNC_PATHS[@]}"
  git diff --quiet "$PLATFORM_BASE" HEAD -- .github "${RAW_PATHS[@]}"
  test -z "$(git status --porcelain)" || { echo 'STOP: 工作区不干净'; exit 1; }
  git status -sb
  git rev-parse HEAD
  echo 'SYNC_OK: 第四版一致，预检已修复，平台工作流与原始 CSV 保留'
)
