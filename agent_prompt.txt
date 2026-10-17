# EB032 MATH-M：布尔极值的精确下界证书

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

这是 EB032 MATH-M 平台适配版：公开数学契约沿用 DDI-032，计分实例采用已冻结的 MATH-M 版本。
直接修改容器内工程；无需另交压缩包。Agent 执行时限为三小时。
