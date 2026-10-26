# 环状DNA背景库去重统计修复

你负责修复生物序列背景库统计工具。/work/bench/app/orbits.py中的旧估计器只按碱基总量排列，再直接除以长度和2，不能正确处理闭环双核苷酸约束、周期序列或自反向互补类别。请完整阅读packet/problem.md，修改app/、bin/，必要时增加build.sh，完成精确总数及最小周期分层统计。统一入口为./bin/analyze --input input.json --output result.jsonl。

在给定Linux环境直接修改工程，允许公开资料、编译与自测，无需嵌套Docker或另交答案ZIP。完整输入、输出、错误保护、资源限制和评分规则以公开problem.md为准。
