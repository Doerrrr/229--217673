# DDI-019 v02 双视图发布接线草稿

工程/work/cohort-release含src/原生核心、app/store.py适配器和bin/命令入口；make同时构建cohort-native及cohort-release。容器已提供HTSlib1.20、Python3.11和编译工具。允许重写候选工程，但不替换上游库或消费者。

```bash
cd /work/cohort-release
make -B
cohort-release --manifest /packet/samples/batches.tsv --samples B,A
cohort-release --manifest /packet/samples/batches.tsv --samples B,A --out-dir /tmp/release-store --expect NONE
python3 /packet/clients/read_store.py --store /tmp/release-store --view release
python3 /packet/clients/read_store.py --store /tmp/release-store --view original
```

旧报告行字段chrom、position、reference、alternate、contributors、samples，以及各观测的source、ordinal、format、values保持原协议。原始视图和版本目录接口见lab/publication.md；样例仅展示调用，不是完整验收器。

当前为未冻结草稿，完整候选判卷与资源标定尚未完成；请勿将此目录当作外部作答成品或平台通过版本。正式冻结包会去掉草稿状态并带唯一摘要。
