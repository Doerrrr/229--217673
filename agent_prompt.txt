维护 `/work/ramsey` 中的受约束 Ramsey 图补全工具。先完整阅读 `packet/problem.md`。
修复 `app/`、`bin/`，必要时增加 `build.sh`；入口 `./bin/ramsey-complete --input INPUT --output OUTPUT`。
每个查询输出同一张满足两色禁团、固定边、红度数和截面计数的完整图，接受任意合法构造；允许正常返回 UNSOLVED，不把它作为不可行证明。
镜像提供 Python、NumPy、SciPy、OR-Tools，允许资料检索、编译与自测。已经在 Linux 容器内，无需嵌套 Docker。
直接修改工程源码，平台运行工程判分，不要求另交 answer.zip。其余输入输出、精确数学验收和错误保护规则以 problem.md 为准。
