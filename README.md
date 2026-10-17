维护 `/work/math` 中的带权相位证据最小撤销工具。先完整阅读 `packet/problem.md`。
修复 `app/` 与 `bin/`，必要时新增 `build.sh`。入口为 `./bin/phase-repair --input INPUT.json --output OUTPUT.jsonl`。
在满足不可撤销 pins 的全部相位赋值中，使违反证据的总费用全局最小；接受任意最优赋值，dropped 必须恰为全部违反证据的ID。
允许使用镜像中提供的 NumPy/SciPy 等工具以及公开资料。你已经处在 Linux 容器中，无需启动嵌套 Docker。
直接修改工程源码，平台会运行工程判分，不要求额外打包 answer.zip；其他数学、输入输出和错误保护规则以 problem.md 为准。
