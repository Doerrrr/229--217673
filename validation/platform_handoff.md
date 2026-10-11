# 远端 IDE 直接粘贴同步说明

下面命令用于把个人仓库中已经验证的 R1 定向返修同步到平台仓库：

- 平台仓库：`https://github.com/cpoct-hlo/229--224559.git`
- 个人仓库：`https://github.com/Doerrrr/229--217673.git`
- 已验证版本：`f6e6d99c24929b54dac553b92a345fceabda51d2`
- Harbor 结果：Oracle `1.000`、NOP `0.000`
- CI：[run 38134071605](https://github.com/Doerrrr/229--217673/actions/runs/38134071605)

在远端 IDE 的终端中，完整复制并粘贴下面这一段。不要删除最外层的括号：

```bash
(
  set -euo pipefail

  cd /home/workspace/project

  APPROVED_COMMIT=f6e6d99c24929b54dac553b92a345fceabda51d2
  PLATFORM_REPO=https://github.com/cpoct-hlo/229--224559.git
  PERSONAL_REPO=https://github.com/Doerrrr/229--217673.git

  echo "[1/7] 检查工作区和平台远端"
  test -d .git || { echo "STOP: /home/workspace/project 不是 Git 仓库"; exit 1; }
  test -z "$(git status --porcelain)" || { echo "STOP: 工作区存在未提交修改"; git status --short; exit 1; }

  ORIGIN_URL=$(git remote get-url origin)
  case "$ORIGIN_URL" in
    https://github.com/cpoct-hlo/229--224559|https://github.com/cpoct-hlo/229--224559.git) ;;
    *) echo "STOP: origin 不是预期的平台仓库：$ORIGIN_URL"; exit 1 ;;
  esac

  echo "[2/7] 配置并拉取两个远端"
  if git remote get-url myrepo >/dev/null 2>&1; then
    git remote set-url myrepo "$PERSONAL_REPO"
  else
    git remote add myrepo "$PERSONAL_REPO"
  fi
  git fetch origin main
  git fetch myrepo main

  echo "[3/7] 更新本地平台 main"
  git switch main
  git merge --ff-only origin/main
  PLATFORM_BASE=$(git rev-parse HEAD)

  git cat-file -e "$APPROVED_COMMIT^{commit}"
  git merge-base --is-ancestor "$APPROVED_COMMIT" myrepo/main || {
    echo "STOP: myrepo/main 不包含已验证版本"
    git show -s --format='%H %s' myrepo/main
    exit 1
  }
  git show -s --format='将同步：%H %s' "$APPROVED_COMMIT"

  echo "[4/7] 同步题包，保留平台自己的 .github 工作流"
  SYNC_PATHS=(.gitattributes README.md environment instruction.md review solution task.toml tests validation)
  git restore --source="$APPROVED_COMMIT" --staged --worktree -- "${SYNC_PATHS[@]}"

  echo "[5/7] 执行发布前保护检查"
  git diff --cached --check
  git diff --cached --quiet -- .github || { echo "STOP: .github 工作流发生变化"; exit 1; }
  git diff --cached --quiet -- environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv || {
    echo "STOP: 三份原始 CSV 发生变化"
    exit 1
  }
  git diff --cached --quiet -- tests/full_snapshot.json || {
    echo "STOP: 全量预期摘要或哈希发生变化"
    exit 1
  }
  python3 validation/check_boundary.py --self-test
  git diff --cached --name-status

  echo "[6/7] 提交并推送平台仓库"
  if git diff --cached --quiet; then
    echo "题包已经是目标版本，无需新提交"
  else
    git commit -m "Fix DDI R1 file boundary and public-contract coverage"
    git push origin main
  fi

  echo "[7/7] 最终核对"
  git status -sb
  git rev-parse HEAD
  git diff --quiet "$APPROVED_COMMIT" HEAD -- "${SYNC_PATHS[@]}" || {
    echo "STOP: 平台题包与已验证个人版本不一致"
    exit 1
  }
  git diff --quiet "$PLATFORM_BASE" HEAD -- .github || {
    echo "STOP: 平台工作流被改动"
    exit 1
  }
  echo "SYNC_OK: 题包一致，平台工作流已保留"
)
```

成功时最后必须看到：

```text
SYNC_OK: 题包一致，平台工作流已保留
```

如果出现任何 `STOP:`，不要继续检测，把从 `STOP:` 开始的终端输出发给我。
由于命令运行在括号子进程中，失败不会自动关闭远端终端。

## 同步后填写平台字段

本次只更新“测试思路”，Prompt、环境思路和参考解思路保持第三版内容不变。
把下面文字直接粘贴进“测试思路”：

```text
按业务交付分六类评分：精确匹配 0.35、化学分簇分折 0.20、候选安全性与分数 0.15、正例分区 0.10、基础清洗 0.10、确定性与失败保护 0.10。15 项测试覆盖传递相似性、scaffold 等价、手性、别名、冲突拒绝、反向及其他事件已知正例、top-8、候选容量、贪心反例和字典序决胜。小图通过穷举独立核算；全量数据核对守恒摘要和 CSV SHA-256。验证器使用独立图遍历与 Hungarian 算法，不导入参考解。致命错误测试在四份旧输出放置哨兵字节后重跑，验证它们完全不变。测试还覆盖不存在的多层输出目录自动创建，三份输入的 BOM、表头前空行、逗号与双引号转义、单字段空白与多字段空记录，以及分别缺少四个必填参数和完全无参数时的非零退出、错误说明与旧输出保护。另用四种不完整实现作负对照，并在发布前扫描候选环境与隐藏 solution/tests 文件，拒绝 SHA-256 及内容均完全相同的跨边界文件。检查项数量和六类权重保持不变。
```

确认平台当前剩余检测次数后，只触发一次“保存并检测”。运行异常、跳过或
无分数不视为低分；同一提交没有外部故障恢复证据时不要重复检测。

检测完成后记录平台提交 SHA、已使用次数、R1、Oracle、NOP、两个 T1、R2、
trial ID 和运行终态。平台最终提交仍由用户决定。
