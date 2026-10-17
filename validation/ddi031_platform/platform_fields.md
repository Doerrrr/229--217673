# DDI-031 平台字段

标题：受约束 Ramsey 图补全
领域：数学 / 图构造 / 组合优化

## Prompt
维护 `/work/ramsey` 中的受约束 Ramsey 图补全工具。完整阅读 `packet/problem.md`，修复 `app/`、`bin/`，必要时新增 `build.sh`。
入口 `./bin/ramsey-complete --input INPUT --output OUTPUT`。同一张完整红蓝图须同时满足两色禁团、固定边、红度数与截面计数。接受任意合法图，不比较隐藏见证身份；允许正常返回 UNSOLVED，不视为不可行证明。
可用 Python、NumPy、SciPy、OR-Tools、g++ 和公开资料。已经在 Linux 容器内，无需嵌套 Docker。直接修改源码，平台运行判分，无需另外打包 answer.zip。

## 评分与版本
小规模0.10、两色禁团0.30、固定边0.20、度数截面0.30、错误保护0.10；组内比例计分，无封顶。
52项判据和私有评分文件与原冻结版字节相同。v01-platform.1 补平台启动、输入驱动参考、g++ 与 packet 路径，旧外测分数不转记为本版正式成绩。
Agent7200秒；Verifier1800秒；单次程序300秒；2 CPU、2GiB。GitHub固定工作流的Oracle/NOP结果须单独核对，不代表正式T1。
