# Codex 复核 113 — 调度脚本（记录器）第一片第 6 轮：两处答错的修复和设计 12.9 的八条裁定（分支 `w31/w66-recorder`，infra `faa94bf`，platform `082a7bd`）

2026-10-12 04:43 CDT · 只读，在自己的副本上跑 · 这一轮由 Cursor 实现、统筹方验收 · 结论：先修。会答错的输入 3 处：满额之后跟着一段没有换行的残尾时不记 `limit_log`；记录连续找到但中间一次状态是 Unknown 时 `since` 取晚了；两件事绑定同一张单时 `next_not_sent` 的 `since` 没用另一份日志里的了结时间。脱敏上界核对为可靠（38 份边缘夹具都过真实校验）；只缺测试 1 条。程序生成的种错不在这次复核范围内（已另作第 7 轮）。

VERDICT: fix first
AN INPUT THAT IS ANSWERED WRONGLY: found
RULES THAT ONLY LACK A TEST: 1
第8节的一问：否；真实 fold_total→publish_total 路径有错误输入，下面3项 P1 均须修复。
范围：infra faa94bf、platform 082a7bd；仅在本目录的 git archive 副本执行，未跑已交回第7轮的生成突变体。
复核106 P1-1：行为已关闭，redact_bound.py:29、publish.py:177、:632；未造出记录器检查通过而真实 HandlePut 拒绝的文档；规则变更测试仍有缺口，见 P2-test。
复核106 P1-2：未完全关闭，read.py:439-456、:499；完整第20,001行和超16 MiB的完整行已关闭，满额后的残尾仍漏 limit_log。
P1-1（裁定2、表B第2行）：read.py:439-456、:499；在本目录运行 `/opt/anaconda3/bin/python3 evidence/repro.py` 的 cap-tail：有效 work_opened＋19,999条 note＋无换行残尾。
实测发布 log_full=true、torn_tail=true，却无 log_invalid_at=20001/log_invalid_why=limit_log，球仍为 coordinator；应按断链判 unknown/log_invalid。无全清，但必备标记和判球错了。
16 MiB同样复现：`/opt/anaconda3/bin/python3 evidence/limits.py`，恰好16 MiB的131行后加1字节，仍无第132行 limit_log；观察日志20,000行后加残尾也丢了该断点。
最小修复：保留完整行和残尾的字节位置，满额后仍有任意字节即在下一行记 limit_log；只有无未读字节才给 log_full。补两种真实上限的残尾和观察日志测试。
P1-2（裁定3的连续找到段）：ownerball.py:397；同一记录 found=true、condition=Unknown@10→found=true@20，零 defects，球为 agents/record_created，since=20，应为10。
最小复现：同上 evidence/repro.py 的 since；最小修复：连续找到段以 found 判定，Unknown condition 不截断；补两个观测次序的测试。
P1-3（裁定3的 next_not_sent）：ownerball.py:162-165、:492-513；两件工作绑定同一 approval，a在@50记录executed，b的下一步@5声明、waiting_on该等待。
最小复现：同上 evidence/repro.py 的 merged-next；两个日志零 defects，合并后等待已了结，发布 since=5，应为50。
最小修复：合并状态保留该ref最早权威终态的sampled_at，_one_next_since按合并后的了结时间计算，再与声明和after结束时间取max；补跨日志终态测试。
P2-test-1：platform api/internal/agentprogress/recorder_fixtures_test.go:133-142；规则监测没有JWT/AWS样本，只数7条编译表达式，不能发现这些规则增长超出假定。
最小复现：`/opt/anaconda3/bin/python3 evidence/redaction.py` 在副本中暂把AWS替换词改为 `[redacted aws key extended]`（增长从−2变+7），TestRecorderRedactionBoundCoversEveryRule仍通过；脚本finally恢复原码。
最小修复：逐条覆盖实际规则的最短匹配和增长，包括JWT/AWS及同规则下的各令牌分支；让上述规则变更使监测测试失败。当前上界行为正确，此项不单独停线。
上界核对：七条最短匹配字节/最大增长依次为27/0、14/+2、5/+9、29/0、20/0、15/+1、7/+9；gh令牌最短24、glpat最短26，均不增长，Slack最短15必须算+1。
增长匹配消耗原字符串中的Basic/Bearer、冒号或等号、Slack前缀、@；9×(:和=)+9×@+2×关键词+1×Slack，对键和值求和可靠；重叠/后续规则复扫未找到漏算。REPORT-6“替换结果不再进后面的规则”叙述不准确，Go实际逐条复扫。
平台重编码：document.go:92关闭HTML转义；引号/反斜杠已有JSON转义，U+2028/2029及控制字符在输入边界被拒，敏感键并块后删掉；134字节外壳偏安全。
自主压力：evidence/redaction.py生成38份真实大小边缘/键名夹具，含四种增长规则、长s折叠、交叠、JWT/AWS/gh/glpat及转义；原106两份复现重跑，均获202。
真实缩减：evidence/real_paths.py和level6.py，不替换量字节函数；原有0–6级夹具确由真实日志生成；limit_log与logs_unread、附加块缺失共同经过真实0–6级，标记和工作/步骤/Owner计数守恒。
大小决策边界另用真实候选的bound−1/bound/bound＋1调整测试预算，0–6级均按边界接受/继续缩减；3、5级预算低于骨架时正确回退，这不是默认预算下的反例。
裁定3：同holder/why取最早正确（ownerball.py:304、:430、:439）；after三时钟的单日志例正确（:501-513），但连续找到和跨日志了结见P1。
裁定4：正确，read.py:60-76、:98-101，按id登记弱引用并核对is、绕过__init__；hash/eq与替换init复现测试通过，普通代码边界和注册表增长已写入模块说明。
裁定5、6：正确，fold.py:85允许未来unrecorded；publish.py:77、:545未知键统一blocks且并块后清敏感键；read.py:532拒绝logs_unread>2^53（含10**5000），边界2^53保留。
REPORT-6“问题”：last_at只是闭合字段清单未同步，P3（fold.py:256）；不改变第8节计数/结论。“没做完”的等效证明已交回第7轮，本轮未将其作停线依据。
验证：现有686项执行为685通过、1失败；失败仅test_guard递归调用的发布CLI测试尝试开网络服务，被沙箱拒绝，未修改测试绕过。15份原夹具和本轮76份夹具均过真实进程内HandlePut（go-baseline.out、go-final-evidence.out）。
须补入设计：把last_at加入字段清单或明确删去；重申满额后残尾也是“其后还有字节”、连续found包含Unknown、绑定等待的since使用跨日志合并证据，避免再次按局部状态解释。
END OF REPORT
