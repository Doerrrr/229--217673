# EB032-MATH-K：布尔极值的精确下界证书

v02 补充多查询和输出写失败检查，五组权重保持题面规定，历史测评分数保留原版本归属。

平台登记标识为 `mathematics/eb032-math-k-exact-certificate`。

你在维护布尔多项式优化与精确下界证书工具。工程位于 `/work/certificate`。
先完整阅读该工程中的 `packet/problem.md`，再修改 `app/`、`bin/`，必要时新增 `build.sh`。
输入格式、输出状态、精确证书条件、失败保护、规模和评分规则均以该文件为准。

命令为：

```bash
cd /work/certificate
./bin/certified-minimum --input packet/smoke.json --output /tmp/result.jsonl
```

需要交付全局最优赋值及精确有理半正定 Gram 下界证书；允许不同的合法赋值和证书，
不按隐藏参考矩阵逐项比较。只找到赋值时如实返回 `INCUMBENT`，没有结果时返回 `UNSOLVED`，
不要把数值容差或求解器状态当作精确证明。先校验完整输入，再原子替换输出。

镜像已提供锁定版本的 NumPy、SciPy、SymPy、CVXPY、SCS、Clarabel 和 OR-Tools。
可以查资料、编译、运行和自行测试；已经处于 Linux 容器内，不需要也不应启动嵌套 Docker。
请直接完成工作目录中的工程修改。平台会运行该工程判分，不需要另交 `answer.zip`。

这是 EB032-MATH-K 平台适配版：公开数学契约沿用 DDI-032，计分实例采用已冻结的 MATH-K 版本。
直接修改容器内工程；无需另交压缩包。Agent 总执行预算为四小时。请先完成可运行的入口并持续保存修改，再逐步完善证书。为最后的编译、烟测和前台退出预留时间，自测应设置有限的迭代次数和时限。

## 发布校验

公开标识为 EB032-MATH-K。task.toml、适配元数据和当前结果的 task 字段使用 mathematics/eb032-math-k-exact-certificate。根目录 .gitattributes 控制 Git 检出的 LF 行尾，包含没有扩展名的 bin 入口。当前检出与全入口验证记录位于 validation/eb032_platform/evidence/current。
