# 私有外部答卷接收与判分

本工具只给委托人使用，不发给作答模型。它不是提示词、题面、参考解或新题包。
当前自动判卷接入 DDI-008 v01；其他七题沿用各自冻结评分器，不用 DDI-008 的评分器判其他题。
本轮不重新打包公开 ZIP，也不启动本地模型或平台检测。

## 固定验收

同一个冻结版本，两份独立、正常且在题包作答预算内的首次答卷，均不高于 0.700。
双方先封卷再判卷；不从多次作答中选择最低两份。20 项各 0.05 的评分标准不因答卷改变。
无法证明独立性或时间时，分数可供诊断，但不能用于宣布目标达成；环境错误不计零分。
作者样例调度器、初始程序、反例和重复答卷都不能冒充两份外部盲测。
相同答卷字节或会话重复会标记待复核；这不是新增行为扣分项，也不影响原判卷分数。

## 操作

把外部返回的 ZIP 原件和真实元数据保留，复制 metadata_template.json 分别填写两份。
时间采用 ISO 8601 并带时区，例如 `2026-10-13T15:00:00+08:00`。不能取得的字段保留未知。
`environment_waits` 如需排除等待，逐段记录 `started_at`、`ended_at`、`reason`，
仅限有事实依据的环境等待，不排除推理、实现、调试或正常程序运行时间。
`evidence_note` 说明独立首答、时间和终态由哪些原始记录确认。模型版本不明可写 unknown。

PowerShell，从作者工作树执行（下面只演示命令，不代表已有真实答卷）：

```powershell
$taskFrozen = 'E:\coding\passby\talentsAi\general_coding\deliverables\ddi_symbolic_lineage_20261013\frozen_v01_r1'
$receivedRoot = 'E:\coding\passby\talentsAi\general_coding\deliverables\ddi_symbolic_lineage_20261013\external_first_answers'

python validation/external_answers/receive_and_grade.py receive --frozen $taskFrozen --root $receivedRoot --record-id agent01 --answer '答卷1的绝对路径.zip' --metadata '元数据1的绝对路径.json'
python validation/external_answers/receive_and_grade.py receive --frozen $taskFrozen --root $receivedRoot --record-id agent02 --answer '答卷2的绝对路径.zip' --metadata '元数据2的绝对路径.json'

# 确认两份均已封卷后再评分，不给任一作答会话回传隐藏反馈。
python validation/external_answers/receive_and_grade.py grade --frozen $taskFrozen --record "$receivedRoot\agent01" --docker-context desktop-linux
python validation/external_answers/receive_and_grade.py grade --frozen $taskFrozen --record "$receivedRoot\agent02" --docker-context desktop-linux
python validation/external_answers/receive_and_grade.py audit --frozen $taskFrozen --records "$receivedRoot\agent01" "$receivedRoot\agent02" --out "$receivedRoot\local_goal_audit.json"
```

`receive` 不执行答案，仅校验 ZIP、冻结包哈希并保存字节一致的原件；记录目录不能覆盖。
`grade` 使用已经冻结的私有评分器和隔离容器；保存每项检查、日志及哈希。
一旦已有评分目录或回执，不会自动重跑。失败后先检查原错误，另行决定受控重试。
`audit` 重新计算固定分值并核对版本、答卷哈希、完整 20 项结果、正常终态及元数据。

## 输出含义

- `LOCAL_STANDARD_MET`：本地标准有两份合格证据，不代表正式平台 T1、Oracle 或 R2 通过。
- `SCORES_ABOVE_TARGET`：正常合格首答中有分数高于 0.700；分析实际漏检/捷径，不能改权重追分。
- `INSUFFICIENT_QUALIFIED_EVIDENCE`：缺答卷、时间/独立性不明或运行异常等，不能宣布降分成功。

接收工具的单元测试是工具质量证据，不是模型答卷成绩。既有四个作者控制只用于检查
正常/异常判分路径，不用于本地难度目标验收。DDI-008 仍没有通用生产 Oracle 或平台验收。
