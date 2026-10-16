# DDI-032 v01：布尔极值的精确下界证书

先读 environment/packet/problem.md，再实现 app/ 和 bin/。本题要求最优赋值与精确有理下界证书，接受不同的合法证书；不比较作者矩阵。

在解压根目录：
```bash
docker build -t ddi032-answer -f environment/Dockerfile environment
docker run --rm -it -v "$PWD/environment:/work/certificate" ddi032-answer bash
```
已在 Linux 容器内时直接操作工程，不再启动 Docker：
```bash
./bin/certified-minimum --input packet/smoke.json --output /tmp/result.jsonl
```

统一提示词在 agent_prompt.txt，每个外部模型用一个全新会话。允许查资料、使用求解库、编译、运行和自测。镜像提供 NumPy/SciPy/SymPy、CVXPY、SCS、Clarabel 和 OR-Tools；不提供隐藏实例、Gram矩阵或通用求解算法。

返回 answer.zip（根目录 changes/、notes.md，必要时 deletions.txt）。修改路径相对 environment/，只交源码。注明模型版本、首次独立或延续/修订、环境是否可用。初始程序未实现任务，不要把初始退出当作数学不可解。

这是 platform.1 适配版：业务契约和评分权重保持 v01，初始原型与环境路径经过平台适配。旧 v01 的外测成绩不转移为本版正式成绩。
