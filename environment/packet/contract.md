# DDI-033 v01 — 证据相位系统维护

本文件规定结果、支持域和验收，不指定内部数据结构或求解路线。修复现有多模块工程，保留 legacy-export 的公开行为，使证据回放、全局数学结论、证明、观测视图和发布版本一致。

## 数学对象

变量为相位块ID，取0/1。XOR证据要求vars中变量异或等于bit，重复变量抵消；FORBID证据禁止vars同时取bits，重复变量相同值合并，冲突值使该禁止条件恒不触发。XOR空式bit=0恒真，bit=1恒假；FORBID空式恒假。

每条证据具有source、protected和cost。protected=true不可在修复决定中撤销，cost固定为0；其他cost为正整数。每个来源可有QUOTA，限制该来源被撤销的记录条数。没有QUOTA表示不额外限制。记录逻辑相同也必须保留各自来源、费用、重数和审计身份。

求满足全部保留条件和来源QUOTA的最小撤销总代价。相同代价多解接受。完整结果为SAT(cost=0)、REPAIRED(cost>0)或UNSAT。UNSAT也是正常成功结论，不等于运行失败。UNKNOWN表示未完成认证，返回8且不提交。

证明使用公开phase_codec生成的规范CNF：给出达到费用K的布尔赋值，并证明不存在费用≤K−1的可行赋值；UNSAT则证明无费用上界的可行性CNF不可满足。ASCII DRAT由固定DRAT-trim检查。证明必须绑定正确模型和阈值，不接受仅打印UNSAT。编码器只定义协议，不求解。候选可使用已安装CaDiCaL、DRAT-trim或其他正常工具。

## 批次与事件

清单JSON键恰为version,batch_id,variables,source。version=1；batch_id为1–64位ASCII字母数字、下划线、连字符。variables是不重复的变量ID列表，包含本批新声明变量；与祖先声明取并集，上限128。source键恰为path,bytes,sha256；path相对清单目录或绝对路径，bytes为1…2^30整数，sha256为实际完整原字节SHA-256小写十六进制。路径可以是普通文件或一次性FIFO。每批一个字节流，内部可以含64个逻辑source。

事件为UTF-8 JSONL，首字节可BOM，空白物理行忽略；单行≤65536字节。拒绝重复JSON键、非有限数和布尔冒充整数。seq为1…2^63−1范围内的严格递增整数，身份(batch_id,seq)，RETRACT目标seq使用相同范围。操作：

- PUT：键seq,op,kind,id,record；kind为EVIDENCE/OBSERVATION/QUOTA，完整替换该(kind,id)。
- DELETE：键seq,op,kind,id；删除当前记录，无匹配合法。
- RETRACT：键seq,op,target；target键batch_id,seq，须指向祖先或本批更早的PUT/DELETE。不允许撤销RETRACT。多个RETRACT停用同一目标是合法集合语义。

选择性撤销从历史回放并跳过目标操作，不是对最终状态做逆操作。PUT和DELETE引用的旧版本不需要仍然生效。已在祖先出现的batch_id不能作为新批次重复使用。origin.ordinal是该批次忽略空白行后的事件序号（从1开始，独立于seq）；BOM不算事件。

所有ID均满足batch_id相同字符规则。支持至多200万条历史事件；生效来源至多64个；规范逻辑条件至多4096种；可撤销费用总和≤2^63−1。

EVIDENCE record的公共键为source,protected,cost,type,vars；XOR另有bit，FORBID另有bits。vars长度≤8，变量须已声明；bit/bits仅整数0/1，bits与vars等长。protected仅JSON布尔。

OBSERVATION record键恰为source,sample,chrom,position,block,gt；block须声明，position为1…2^63−1整数，gt为0|0、0|1、1|0、1|1、.|.之一。决定中block为1时反转两侧顺序，0时保持。来源原观测不得改写为发布后的值。

QUOTA的id即来源ID，record键仅max_drops，为0…2000000整数。删除QUOTA恢复该来源无额外限额。

## CLI

工程根下bin/phase-lab，支持：

```
phase-lab legacy-export --input OLD_JSON
phase-lab prepare --manifest M --store S --base NONE|G --ticket T [--checkpoint-bytes N --checkpoint-gate D] [--gate D]
phase-lab resume --manifest M --store S --ticket T [--gate D]
phase-lab commit --store S --ticket T --expect NONE|G
phase-lab rebase --store S --ticket T --base G [--gate D]
phase-lab query --store S --generation CURRENT|G --view decision|calls|facts|provenance [--id ID]
phase-lab verify --store S --generation CURRENT|G
```

T为调用方选择且不含路径分隔符的ID。G为64位小写SHA-256。prepare/resume/rebase成功后为PREPARED，不自动提交；commit才移动CURRENT。修改命令成功输出一行JSON回执；query输出JSON或JSONL；错误stdout为空、stderr简短说明。query省略id返回完整对应视图。

legacy-export的输入是version=1,variables,relations,observations，relations为受保护二元XOR的{a,b,bit}，形成森林；输出与公开旧消费者一致。新事务域没有森林承诺，不能用旧局部方法代替全局求解。

## 会话、恢复和并发

状态为CAPTURING→CAPTURED→MODELED→PROVED→PREPARED→COMMITTED。CAPTURED意味着实际完整原字节核验通过；来源此后允许消失。恢复不得把后缀当新批次，不得按恢复次数重置原始ordinal。每个ticket仅允许一个变更命令在运行；不同ticket可以并行。

检查点N为正整数且小于source.bytes，可能位于行或UTF-8字符中间。恰收到N字节并持久保存后，在checkpoint-gate/ready原子写{stage:"CHECKPOINTED",ticket,bytes:N,sha256:前缀实际摘要}，等待go。外部可此时SIGKILL。resume清单身份须相同，path可变并只供应剩余后缀；若来源已完整采集，resume和rebase不得再次打开来源。

发布gate在所有待提交产物已齐、可验证后写ready={stage:"PREPARED",ticket,generation,model_id,statement_id}，等待go。不同准备者必须可同时到达此处，不得在等待期持全局排他锁。等待最多300秒，超时退出8、不提交。

commit必须在实际提交时检查CURRENT==expect==ticket基线，不得仅准备开始时检查。不同批次同一前置并发提交恰一个成功，其余7。同一版本重复提交幂等，但不得覆盖已提交字节或把CURRENT退回历史版本。失败保留完整采集会话。rebase仅到原基线后继，重新回放同一批次，重新确定模型和证明；只在声明身份完全相同的情况下可复用证明。

允许SIGKILL后留下自己的未提交临时状态，重试须能检查和恢复；不能误删别人的ticket、固定读者的版本或已提交产物。不要求机器掉电、介质损坏或垃圾回收旧版本。

## 对象与身份

JSON规范字节为UTF-8、键排序、无多余空白、不ASCII转义，不允许浮点值。phase_codec.canonical/digest定义该编码。input={batch_id,variables:本批声明排序,source:{bytes,sha256}}，不含path。generation=SHA256(canonical({version:1,parent:基线,input}))。

每个版本在STORE/generations/G/，至少包括facts.jsonl、model.json、decision.json、statement.json、certificate.drat、calls.jsonl、provenance.jsonl、manifest.json，允许另存内部索引。manifest键为version,generation,parent,input,variables,model_id,provenance_id,statement_id,files；files含除manifest自身外的所有公开/内部版本文件及其sha256和bytes。已提交文件不可变。CURRENT为一行JSON{generation,manifest_sha256}，整体切换。

facts行键kind,id,record,origin；origin={batch_id,seq,ordinal}。按kind,id排序。model.json必须等于公开model_from_records结果。model_id为该模型的digest；provenance_id为provenance.jsonl实际字节摘要；statement_id为statement.json对象digest。原字节不同但数学模型相同可以复用证明，但来源审计仍不同。相同费用不代表相同模型。

decision键status,assignment,dropped,cost。SAT/REPAIRED的assignment完整覆盖变量，dropped为所有违反的可撤销EVIDENCE记录ID升序列表；费用及各来源撤销数必须从生效事实重算。UNSAT三字段均null。calls按chrom,position,sample,id排序，每行包含观测的id、原record各字段、gt替换成发布方向的值、origin和generation；UNSAT时为空，query decision仍明确UNSAT，不回退旧可行版本。

provenance按kind,id排序，每行键kind,id,origin,source,outcome。EVIDENCE为KEPT/DROPPED或UNSAT时UNRESOLVED；OBSERVATION为PROJECTED或UNRESOLVED；QUOTA为POLICY；QUOTA的source为其id，其他为record.source。

verify必须核对文件字节、独立重建数学模型、决定、来源映射和证明声明。不能仅接受候选提供的另一份CNF。query固定一次CURRENT或指定G；不混用不同版本的文件。显式查询旧G仍应正常。

## 失败和资源

0成功（包括已认证UNSAT）；2用法/结构错误；3来源打不开；4原字节/记录/历史引用错误；5对象或证明绑定损坏；6I/O错误；7CAS或同ticket并发冲突；8未完成认证。任何失败不得移动CURRENT或破坏既有版本。多种错误优先级不计核心分。

完整候选命令wait4 ru_maxrss默认≤512MiB，包含正常等待子进程的最大峰值，不声称总同时RSS。2CPU、4GiB环境、10GiB存储；允许原档案和磁盘暂存。禁止脱离命令的残留进程。数学大规模与原字节大规模不要求同时取上限。最终agent时限7200秒，验证器900秒。判卷调用另有180秒挂起保护；gate场景由测试在ready后发go或主动终止，不让候选等待超过该保护。挂起保护不是缩短模型作答时间；运行异常、信号终止和超时单独记录，不当有效低T1证据。

评分：回放0.12、全局数学0.26、证明绑定0.20、发布查询0.14、并发恢复rebase0.16、资源0.06、旧接口0.06。各组按场景比例，无额外封顶；没有证明不会抹掉已验证的数学结果分。旧域烟测是发布前检查，不给未实现新业务的NOP保底分。
