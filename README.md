# DDI-033 v01：全局相位修复、无解证明与可恢复发布

这是一道遗留业务工程维护题，不是要求证明尚未解决的数学总命题。实例可以最优可行，也可以经过证明无解；两种都是正常业务结论。

先读 `packet/contract.md`、`packet/intake.md` 和公开 `clients/`。数学结论、原始证据、撤销历史、证明和查询视图必须属于同一版本。任何最优同价解都接受，不要求复制作者的算法或文件内部布局。

本目录可以直接作为 Docker 构建上下文：

```bash
docker build -t ddi033 .
docker run --rm -it ddi033 bash
python3 clients/check_legacy.py
phase-lab --help
```

工程根是 `/work/phase`。容器内部不需要 Docker。可查资料、编译、运行和自测。正常候选身份为 UID/GID 10001；不需要管理员服务或网络服务部署。

作答时间 7200 秒，验证器 900 秒。2 CPU、4 GiB 容器内存、10 GiB 存储；完整命令的 `wait4 ru_maxrss` 预算 512 MiB。它是等待子进程口径的最大峰值，不是多个并发进程 RSS 之和。具体的历史和证明支持范围见契约；验收不将所有维度上限同时相乘。

交付源代码增量 `answer.zip`：根目录 `changes/` 和非空 `notes.md`；可选 `deletions.txt`。修改路径相对工程根，仅允许 `app/`、`bin/` 和 `build.sh`。不附依赖源码、二进制、输入样例、私有评分器或其他答卷。`notes.md` 如实说明模型版本、实际验证、限制和未完成项。
