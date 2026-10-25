# D-L5 审批准备单（Work 564，未提交审批）

## 拟申请动作与影响

归档并逐 mission 核对后，给下面所列历史演练 mission 写入 `scope_json.no_merge` 理由，
明确“已处置、未交付”。这是整个 mission 的设置，影响其所有任务，**不是只给表中一个分支打标签**。
accepted 的计时从收下那刻开始，标完下一轮 agentd 就可能删分支，不会再等 24 小时。
本动作不合 main、不发版、不停止新任务；4.1 的启用时刻资格屏障独立成立。

**尚未做**：未连运行时或 Gitea、未核对当前 mission 完整任务集合、未归档、未独立复核本单、
未建立 Console 审批。本单不能直接批准执行，不提供会跳过归档的 SQL。

## 范围与来源

来源：`INVENTORY-lifecycle-2026-10-24.md` §3.1、`CUT-lifecycle-2026-10-24.md` §5 D-L5，
以及 `CUT-landing-2026-10-24.md` §1.7、§2.2。
原表是 **19 条 D-L5 分支**，落地切法是 **20 个 accepted 结果**，不是两个可互换的分母。
STG M-27 的 Q07 两次尝试尚不知哪次被收下，正好是必须补查的歧义，不能按数量猜。

- PROD：M-1、M-2、M-3、M-4、M-13、M-15（6 个 mission）。
- STG：M-2、M-16、M-23、M-24、M-26、M-27、M-103（7 个 mission）。
- 不把 PROD M-9 的旧 a1、PROD M-14、STG M-1/M-13 cancelled 尝试混进本单。

## 建正式单之前的封闭条件

1. 分别从两环境读取 mission 真 ID、scope 版本、全部任务及当前状态；M-n 只作展示编号，不作写库主键。
2. 逐项绑定被收下的 attempt、完整 SHA、实际 ref、是否已在 main/是否被 revert；处理 M-27 Q07 歧义。
3. 保存能恢复确切对象的归档；记录位置、SHA-256、`git bundle verify` 与读回检查结果。
   没有对象可达性或归档证据的条目不进入批准范围，不按 patch-id 或标题认定已保全。
4. 列明每个 mission 的其他任务是否也应放弃；不应放弃的 mission 整体排除，重新拆单。
5. 正式 payload 精确列出环境、mission ID、scope 版本、预期旧 no_merge、新理由和归档清单摘要。
   版本变化时拒绝执行，不能扩大为“全部旧任务”。
6. 通过现有平台审批建 C/D 单，正文首段使用上面的影响说明，并列出未做的检查。
   Owner 在 Console 批准后才写库；保存批准/执行事件和读回证据。

## 验收与回退

批准后核对：只有精确批准的 mission 变更，理由存在，归档读回通过；后续分支清理的日志可追到本单。
未批准可取消；已写入须用版本约束的更正单；已清理分支必须从归档恢复，清空 no_merge 本身不能恢复对象。
未知 SHA、未知归档位置不是可执行占位符：补查未完成时本单保持“准备中”，S0 报告保留未验证项。

## 原盘点逐行索引（不是当前事实）

下表 **21 行 = 20 个任务，其中 Q07 的两次尝试各占一行**（19 个其他任务 + Q07 的 a1/a2）；不是 21 个 accepted 任务。
下表原样保留任务/尝试关联，不伪造完整 SHA 或归档位置。正式单须以新读取结果替换历史索引。

| 仓库 | 分支 / 任务尝试 | 环境 / mission | 原记录 |
|---|---|---|---|
| platform | `agent/t_01M50M1CZSDN8PNHRH8C2241RS/a1` | STG M-2 | accepted 10-15（UniFi 测试，演练） |
| platform | `agent/t_01M511RV9S41AEW9CDA76024Q3/a1` | PROD M-1 | accepted 10-16（一段注释） |
| platform | `agent/t_01M51EHZ92V5F2PRB7JCZVHTQ3/a1` | PROD M-2 | accepted 10-16（一段注释） |
| platform | `agent/t_01M55AN78GPF9V6NFZFS4KJP8N/a1` | PROD M-3 | accepted 10-17（safego 测试，2.3 演练） |
| platform | `agent/t_01M55AN78M1MX9NF9Q958T96Z3/a1` | PROD M-3 | accepted 10-17（statefile 测试，2.3 演练） |
| platform | `agent/t_01M56J5QPAAQQP53KV4MQYCW5Q/a1` | PROD M-4 | accepted 10-18（一段注释） |
| platform | `agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a2` | STG M-16 | accepted 10-19（T26 返工演练） |
| platform | `agent/t_01M5B37AYBAHQTM6RMQZZHE3AT/a1` | STG M-23 | accepted 10-19（隔离版 agentd 走查） |
| platform | `agent/t_01M5B6KKPMM15HZB4BC0ZWVJ5R/a1` | STG M-24 | accepted 10-19（TD-382 走查） |
| platform | `agent/t_01M5BSBEZ7J3BQM0EV7SG3NB2N/a1` | STG M-26 | accepted 10-20（Gate B 实测） |
| platform | `agent/t_01M5BSPFV3S9ET52X3JT76HJFS/a1` | STG M-27 | accepted 10-20（基准题 Q04） |
| platform | `agent/t_01M5BSPFV8JBH908TR6M58S6Q9/a1` | STG M-27 | accepted 10-20（基准题 Q06） |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a1` | STG M-27 | accepted 10-20（基准题 Q07）；两次尝试，哪次被收下没查 |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a2` | STG M-27 | accepted 10-20（基准题 Q07）；两次尝试，哪次被收下没查 |
| platform | `agent/t_01M5BSPFVDY1N34EGQ5THXYMMD/a1` | STG M-27 | accepted 10-20（基准题 Q18） |
| platform | `agent/t_01M5BSTGPP9FC3PCF4NF5PM7GD/a1` | PROD M-13 | accepted 10-20（Gate B 实测） |
| platform | `agent/t_01M5BV3W403F0SYH6HF8RAFNJ0/a1` | PROD M-15 | accepted 10-20（基准题 Q04） |
| platform | `agent/t_01M5BV3W43ETJPVBT55T2XYW30/a1` | PROD M-15 | accepted 10-20（基准题 Q06） |
| platform | `agent/t_01M5BV3W45NDSBHBTEFY4RMT97/a1` | PROD M-15 | accepted 10-20（基准题 Q07） |
| platform | `agent/t_01M5BV3W48B5HGHZB5JJKHE81G/a1` | PROD M-15 | accepted 10-20（基准题 Q18） |
| trade-infra | `agent/t_01M5G4W33CRXXVX4C7GJTCJ3VR/a1` | STG M-103 | accepted 10-21（T24/T34 演练） |
