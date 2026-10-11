# 第四版：远端 IDE 直接粘贴同步说明

本文件的已验证 SHA 与 CI 回执将在验收完成后锁定。现在不要触发平台检测。
完成后在个人仓库最新版说明中复制整个 Bash 代码块，不删除最外层括号。
遇到 STOP 时停止，把报错发给我；不会自动关闭终端。

```bash
(
  set -euo pipefail
  cd /home/workspace/project

  APPROVED_COMMIT=WAIT_FOR_V4_CI
  PERSONAL_REPO=https://github.com/Doerrrr/229--217673.git

  echo "[1/7] 检查干净工作区和平台 origin"
  test -d .git || { echo "STOP: 不是 Git 仓库"; exit 1; }
  test -z "$(git status --porcelain)" || { echo "STOP: 有未提交修改"; git status --short; exit 1; }
  case "$(git remote get-url origin)" in
    https://github.com/cpoct-hlo/229--224559|https://github.com/cpoct-hlo/229--224559.git) ;;
    *) echo "STOP: origin 不是预期平台仓库"; exit 1 ;;
  esac

  echo "[2/7] 拉取两个远端"
  if git remote get-url myrepo >/dev/null 2>&1; then
    git remote set-url myrepo "$PERSONAL_REPO"
  else
    git remote add myrepo "$PERSONAL_REPO"
  fi
  git fetch origin main:refs/remotes/origin/main
  git fetch myrepo main:refs/remotes/myrepo/main

  echo "[3/7] 核对平台基线和批准 SHA"
  git switch main
  git merge --ff-only origin/main
  test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" || {
    echo "STOP: 本地 main 有尚未同步的提交"; exit 1;
  }
  PLATFORM_BASE=$(git rev-parse HEAD)
  git cat-file -e "$APPROVED_COMMIT^{commit}"
  git merge-base --is-ancestor "$APPROVED_COMMIT" myrepo/main || {
    echo "STOP: 个人仓库不包含批准版本"; exit 1;
  }
  git show -s --format='同步版本：%H %s' "$APPROVED_COMMIT"

  echo "[4/7] 仅同步题包和说明，不导入个人工作流"
  SYNC_PATHS=(.gitattributes README.md environment instruction.md review solution task.toml tests validation)
  git restore --source="$APPROVED_COMMIT" --staged --worktree -- "${SYNC_PATHS[@]}"

  echo "[5/7] 发布保护检查"
  git diff --cached --check
  git diff --cached --quiet -- .github || { echo "STOP: 平台工作流变动"; exit 1; }
  git diff --cached --quiet -- environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv || {
    echo "STOP: 三份原始 CSV 变动"; exit 1;
  }
  python3 validation/check_boundary.py --self-test
  python3 validation/check_release_assets.py --platform
  test ! -e solution/ddi-release || { echo "STOP: 隐藏启动器重复"; exit 1; }
  grep -n 'screen-plan' instruction.md solution/solve.sh
  head -n 3 task.toml
  git diff --cached --name-status

  echo "[6/7] 提交并推送"
  if git diff --cached --quiet; then
    echo "已经是目标题包，无需新提交"
  else
    git commit -m "Publish resource-constrained DDI experiment release"
  fi
  git push origin main

  echo "[7/7] 核对同一题包和平台工作流"
  git diff --quiet "$APPROVED_COMMIT" HEAD -- "${SYNC_PATHS[@]}" || {
    echo "STOP: 平台题包与批准版本不一致"; exit 1;
  }
  git diff --quiet "$PLATFORM_BASE" HEAD -- .github || { echo "STOP: 平台工作流改动"; exit 1; }
  test -z "$(git status --porcelain)" || { echo "STOP: 工作区不干净"; exit 1; }
  git status -sb
  git rev-parse HEAD
  echo "SYNC_OK: 第四版题包一致，平台工作流已保留"
)
```

本版候选表和资源报告的预期哈希会改变，这是批准改动；分子表和正例表的
预期哈希仍与第三版一致，由 check_release_assets.py 核对。平台工作流
可能不同于个人 Harbor 工作流，平台模式仅验证数据/题包，工作流用 Git
前后对比保护，不能将个人工作流的哈希要求强加给平台。

同步成功后，更新 platform_fields.md 中四段平台介绍，而非只改测试思路。
确认平台当前剩余次数，再触发一次“保存并检测”；本地检查与 CI 不会
消耗平台 10 次检测机会。最新已知回执剩余 5 次，但须以当前页面为准。

## 结果决策

- R1、Oracle、NOP 失败：定向修一致性，不据该轮判断 T1 难度。
- 两个 T1 正常完成且均 <=0.700：继续 R2；全部通过即冻结。
- 任一 T1 正常得分 >0.700：不重复检测同一提交，先分析新增证据。
- runtime_error、超时、跳过：记录 trial ID，不作为低分；查明后再决定重试。
- R2 失败：只修具体质量意见。最终提交由你决定。

最多 5 次剩余机会的安排：2 次实质版本、2 次明确质量返修、1 次已查明
的平台异常；不是要求用完。建议保存本轮平台提交 SHA、介绍字段版本、
R1/Oracle/NOP、两个 T1、R2、trial ID 和运行终态。
