# DDI-018 v04-setpriv 远端同步

本版移除测量器和Python适配器内直接的setgroups/setuid/setgid调用，改用util-linux
setpriv --reuid=10001 --regid=10001 --clear-groups --no-new-privs。业务语义、33项评分和权重未变。
实际降权及私有目录隔离须通过验证；不以删除安全措施来绕过门禁。
新增判分阶段标记及stderr日志。unknown原因仍待平台实际日志，不假定本版必然修复。
旧三份 0.500/0.400/0.950 属于 v01 外部答卷，不是 v02 正式 T1。

## 粘贴命令

锁定最终通过 CI 的完整 SHA 后，使用交付消息中的短命令加载本目录 sync_platform.sh。
本版使用sync_manual.sh，只在/home/workspace/project执行，检查工作区干净及平台origin，
导入完整批准题包但不导入个人.github工作流。停在暂存状态，用户自己commit/push。

执行后须出现SYNC_READY；手动提交后记录source及platform两个SHA。
远端提交 SHA 与个人仓库 SHA 不同是正常的，因为保留了不同仓库历史及平台工作流；
脚本会核对两边题包内容。若 STOP，请保留当前状态并发送完整输出，不反复粘贴长脚本。

## 平台字段与检测

从 platform_fields.md 复制四段字段，然后核对当前剩余次数，只触发一次检测。
联网保持启用；先看 R1，再看正常 Oracle=1/NOP=0，随后两项 T1 和 R2。
无分数、运行异常或被跳过不算低分；最终提交仍由用户决定。

本地已用 Harbor 0.5.0 正常验证 Oracle=1.000、NOP=0.000；
最终 GitHub CI 回执在交付消息另行给出，不以本文件冒称平台通过。
