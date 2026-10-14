# DDI-018：跨批次观测聚合维护

这是题设构造的原生C工程，不冒称公司内部事故或上游已公布的补丁任务。依赖为HTSlib1.20，工具名cohort-release，Makefile从src/构建。修复对象是本工程，而不是替换上游库。

从本题目录运行：

```bash
docker build -t ddi018-lab ./environment
docker run --rm -it -v "$PWD:/packet" ddi018-lab bash
cd /work/cohort-release
make -B
./cohort-release --manifest /packet/samples/batches.tsv --samples B,A
python /packet/clients/consume.py --binary ./cohort-release --manifest /packet/samples/batches.tsv --samples B,A
```

源码在/work/cohort-release，修改后的源码需复制到宿主的changes/目录再打包。样例只展示调用，并不构成完整验收器或涵盖整个输入域。

调用形式：cohort-release --manifest batches.tsv --samples S1,S2。实验室交换资料在lab/exchange.md，接收端在clients/consume.py。

JSON Lines位点包含chrom、position、reference、alternate（ALT字符串列表）、contributors（source/ordinal源记录列表）、samples。samples按请求名称顺序，每项含name、winner（观测对象或null）、others（观测列表）。观测对象含source、ordinal、format（字段名称列表）、values（名称到测量的对象）。GT仍用VCF的字符串表示；AD/PL用整数或null元素的数组，整向量缺失也可用null；DP/GQ/PS用整数或null。JSON键序、空白和额外元数据不作为答案。

来源含义和字段身份可查询固定上游源码与[VCF4.3/BCF2.2规范](https://samtools.github.io/hts-specs/VCFv4.3.pdf)。允许查阅资料，不禁止联网。不限定线程、堆、临时盘或其他方法；尚未规定必须修改哪些函数。

资源检查采用Linux wait4记录的一次完整命令的ru_maxrss，上限192MiB。判卷器自身内存和输出文件大小不计入该数值；临时盘允许使用。测试包含40万个位点的单源报告，以及16源、64样本、32贡献记录、17种等位、四倍体的宽位点。它们都在公开支持域内，并有完成相同有限发布的原生控制，非通用参考修复。单次命令180秒仅作挂起保护；不以超时或OOM作为增难成功的证据。正常完成但超出RSS预算才属于资源未达标。

不存在或不可读的来源、无法解析的标题或源记录、全局不存在的请求样本应非零退出并有简短stderr，措辞自由。空数据源和所有来源均无记录是合法的，后者成功输出零行。其他超出支持域的输入不纳入本题验收。不要求失败前stdout原子回滚、并发发布、掉电恢复、兼容旧ABI或字节级匹配。
