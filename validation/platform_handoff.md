# 远端同步与一次检测

先等个人仓库 **固定 Harbor 工作流**对本次题包完成 Oracle=1、NOP=0。
Windows Python 检查不能替代 Docker/Harbor 验证。最终平台提交仍由用户决定。

平台工作区应是 `/home/workspace/project`，origin 应为
`https://github.com/cpoct-hlo/229--224559.git`，myrepo 应为
`https://github.com/Doerrrr/229--217673.git`。先核对，不能自动改 origin。

```bash
cd /home/workspace/project
git status --short
git remote -v
```

有未提交修改时先停下，不执行后面的 restore。确认工作区干净且远端正确后，
将 `APPROVED_COMMIT` 替换为本次 CI 通过的个人仓库提交完整 SHA：

```bash
test -z "$(git status --porcelain)" || { echo "STOP: local changes"; exit 1; }
git fetch origin main
git fetch myrepo main
git switch main
git merge --ff-only origin/main
APPROVED_COMMIT=这里填写已验证的个人仓库SHA
git show -s --format='%H %s' "$APPROVED_COMMIT"
git restore --source="$APPROVED_COMMIT" --staged --worktree -- \
  .gitattributes README.md environment instruction.md review solution task.toml tests validation
git diff --cached --check
git diff --cached --name-status
git diff --cached --quiet -- .github || { echo "STOP: workflow changed"; exit 1; }
git diff --cached --quiet -- environment/data/drug_list.csv environment/data/DDI_event.csv environment/data/newddi.csv \
  || { echo "STOP: original CSV changed"; exit 1; }
git diff --cached --quiet -- tests/full_snapshot.json \
  || { echo "STOP: expected full snapshot changed"; exit 1; }
python3 validation/check_boundary.py --self-test
git commit -m "Fix DDI release file boundary and public-contract test gaps"
git push origin main
git status -sb
git rev-parse HEAD
git diff "$APPROVED_COMMIT" HEAD -- .gitattributes README.md environment instruction.md review solution task.toml tests validation
```

最后一条 diff 应无输出：题包与已验证个人提交一致。平台仓库的 workflow
不在 restore 路径中，必须保留。旧变更流、旧 launcher/Oracle 的删除是
接口替换的一部分；Git 历史中的原版本仍可恢复。

本次是第三版 R1 定向返修：只需更新测试思路，Prompt、环境与主体功能
保持第三版介绍不变。参考侧重复 launcher 已删除，solve.sh 复用候选侧入口。
核对平台当前剩余次数，再触发 **一次** 保存并检测。

记录平台提交 SHA、检测次数、R1、Oracle、NOP、两项 T1、R2、trial ID 和
运行终态。门槛是两项 T1 正常完成且均 <=0.700，并且其余阶段通过。
运行异常/跳过/无分数不是低分证据。

同一提交没有新故障恢复证据时不重复检测。正常得分仍高则先读具体反馈，
不盲目叠加功能或单纯调整权重。平台全部通过即冻结，不为余量继续冒险。
