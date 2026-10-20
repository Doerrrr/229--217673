# 当前发布：EB032-MATH-R v01（2026-10-20）

当前数学载荷、证据范围与时限见 platform_fields.md、payload.json、local_validation.json。
本版新增 11 个精确有理目标实例；作者 Oracle/NOP 分别 1/0，收到 DS 修改程序本地正常 0.550。
没有新版正式平台 T1；没有新 CI。本次个人仓库提交使用 [skip ci]，平台检测由用户自行触发。
原有 UID、读取隔离和运行保护代码未改；历史安全回归只在对应源摘要相同时复用，不转记为新数学成绩。

同步：从批准的个人提交执行 sync_platform.sh；检查暂存内容后由用户在平台仓库 commit/push。
回滚：对本次提交使用 git revert <提交号>，保留历史；不使用强制推送或全仓库重置。

---

以下为历史 MATH-M 记录，其“当前结果”措辞只适用于各自历史版本。

# EB032 MATH-M 发布、验证与回滚

本次修订保持README、instruction、agent_prompt、完整environment、task.toml、18个计分实例、algebra精确算法及五组权重；仍为66项断言／47次CLI调用。数学评分核心不变。grade032保留同一check并增加输出文件边界读取；common保护输入写入并避免历史job累计缓存日志字节；test.sh清理旧reward、标明失败阶段并输出有界诊断。日志超量只截断保存，不改变正常退出分类。运行保护变化不能据此称作整个grader逐字节不变。

## 当前结果与适用范围

历史平台结果在evidence/platform_result_20261018.json：R1=92、Oracle=1、NOP=0、两候选正常0.518／0.617、R2=77.26。模型名称来自R2标注。该成绩属于补丁之前的平台冻结版本；新补丁尚未回放两份平台候选，不能声称新分数已实测相同。R2仍待复评。

本轮固定身份子进程修订已发布；代码提交7b020d212419a491c834e65e10bfe9241dc08f6c已通过GitHub作者回归及Harbor Oracle=1／NOP=0启动验证，载荷d6e166c5f9b8204d4890a97995697f71ba60d1f8464e4077020c36fd92eb807a。platform.5及platform.6的CI单独保留为历史。CI证据应按“已验证代码提交＋payload摘要＋cases摘要”绑定。证据补录提交只增补作者材料，不改变已验证的代码载荷。发布时以local_validation.json中的实际CI回执和payload_digest为准，不将旧CI或旧T1冒充新运行。平台来源标签、R2冻结HEAD、个人提交分别记录，不因三者不同自行推断错误。

容器实际记录每次提供的输入文件SHA-256，以及当前grade／algebra／measure等源码摘要；CI回执将这些摘要绑定到已验证代码提交。容器没有平台Git信息时将source_commit明确置空，不编造冻结HEAD。结果溯源步骤只增加元数据，既有groups／cases／reward不改。

## 运行保护

- Agent18000秒、Verifier18000秒、候选每次300秒，2CPU／2048MiB，公开联网能力不变。
- 候选结束后清理其进程组；测量器以subreaper收养并清理脱离会话的后代，不杀同UID的无关进程。
- 单次stdout与stderr文件各保存前32MiB，另保留最多2KiB stderr尾部用于诊断。超量继续排空，不因日志量杀进程；stdout非空仍按原规则处理。历史job仅保留测量元数据，避免累计持有日志正文。答案JSONL未新增大小拒绝条件。
- 数学check在独立进程执行，每次最多300秒，全卷精确检查合计2400秒；超限或检查器崩溃属于VERIFIER_CHECKER_ERROR，非数学错误、非有效低分。诊断保存到结果目录checker/。
- 47次调用及可选一次构建按父进程315秒等待累计15120秒，再加checker总预算2400秒为17520秒；18000秒外层剩480秒作框架开销。不是对平台排队、重试或总墙钟的承诺。

## 作者回归与候选计分

author_checks.py是非计分作者回归：旧／新grader在正常、点解、部分证书、完整有限见证、恒等式错误、非PSD控制上逐项比较；验证进程残留、脱离会话、日志截断兼容、checker超时及输出不可写等故障；检查合法与非法输入边界。它不向候选追加计分实例，不增加failure组分母。

solution仍是诚实标注的有限见证启动控制。它不是通用生产求解器；不为提高R2而隐藏catalogue或虚称具备目录外算法。目录外合法输入可UNSOLVED。负分母原已被正则拒绝；本次再显式检查正分母，使零分母也有coef字段定位。

## 平台应用与清理

按固定提交运行sync_platform.sh，要求平台main且工作区干净；保留.github及三份原CSV。清理的旧review与validation/dual_platform属于原DDI-019活动材料，旧内容仍在应用前Git提交中，不用历史模板充作本题证据。个人仓库新增作者回归workflow不被同步到平台.github。

同步前先记下 `git rev-parse HEAD`；暂存后核对差异并提交。平台当前剩余次数以页面为准，任何平台检测均由用户决定，本轮不自动触发。

## 回滚

尚未commit：先检查暂存差异；仅对本次脚本列出的修改路径使用 `git restore --source=HEAD --staged --worktree -- <路径>`，不要用全仓库reset抹掉其他改动。

已commit/push：先确认工作区干净，查看 `git log --oneline -5` 确定本次平台应用提交，再执行 `git revert --no-edit <本次平台应用提交>`，检查后 `git push origin main`。revert保留历史并恢复本次删去的旧目录；是否触发其他平台流程取决于实际工作流配置；本轮不执行远端回滚或模型重测。个人作者代码基线为d94f7fdb983303d05cf7b54fd73b791e05ae3156。

## 交付状态

当前可报告的是本轮固定身份子进程修订的本地作者验证；本轮GitHub回执以local_validation.json为准。历史平台回执单独保留。只有平台新回执能确认R2合格或新T1成绩，不能根据检查清单、预计涨分或作者控制宣布整体验收完成。


## UID／GID静态范围反馈与当前读取结构

platform.6虽在前面验证范围，平台仍拒绝setegid(gid)和setgroups(groups)。当前不再改变父进程凭据，也不再恢复任何保存的ID。root验证器只创建一个顺序执行的读取子进程；子进程仅调用setgroups([])、setgid(10001)、setuid(10001)，三个参数均为明确字面量。普通文件、候选mode-000文件及可读链接使用同一候选权限读取，FIFO和目录拒绝，root私有文件不读取。父进程只接收字节数据并按原方式解析JSONL。

父进程边读管道边等待EOF，随后回收该子进程，避免大于管道缓冲区的答案死锁。子进程内部错误、降权失败或异常退出报告验证器异常，不冒充错误证书或有效低分。非root调用保留原身份直接读取；原环境ID范围检查保留，但不作为凭据修改参数的范围依据。

27项非计分作者控制覆盖正常与失败路径、父进程身份不变、固定子进程身份、2MiB输出传输、fork失败描述符关闭和子进程全部回收。既有15项文件／入口控制与792项计分断言对照通过。全部Python身份修改参数均为范围内字面量；本地检查不是平台门禁复评。

发布打包补充：新增 finite_witnesses.json 的 -text 规则，防止 Git 改写已验证字节。已校正新实例附带的旧因子和规模统计；所有 group/query/answer/optimum 计分字段与本地验证版本一致，判卷逻辑未改。原验证摘要保留为 validated_math_payload_digest，计分对象另由 graded_objects_sha256 绑定。
