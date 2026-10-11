# TD-172 / TD-142：已批准 60-session 批次执行记录

Owner批准主64父键/256目标日与必要时9备用父键/36目标日；HTTP总上限220；SPY两日闸门→SPY其余→NVDA→AAPL。禁止发布/扩大范围。

方案：`TD-172-142_DEPTH_60_PLAN_2026-10-10.md`。冻结2026-10-09/252 session；execution manifest SHA `f05a758d2496b851387c4d5918f99748827ae9f0d5cd18e1e8de4e54c75af381`，108执行区间/292目标日是含备用的上限。

## 入口与测试

Plugin隔离提交 `6a5e209`：新depth入口独立验证manifest、108/292总规模及7个phase子集；历史180–220 DTE和标准成员校验，主键差集/DO NOTHING；220 total /90 reference /130 bars。阶段携带持久私有checkpoint和验收digest，HTTP前fsync日志并输出计数；未知/中断动作未对账不得继续。SPY180无改善、上名未达60、备用非必要均拒绝继续。每名positive control只读，不扩大写入。

入口lint PASS、插件1310 passed/9 skipped、Research repair/cone16 passed；DEV基线SPY39/33、NVDA44/43、AAPL41/40。事务恢复修复后1313 passed/9 skipped；最终accepted-receipt重放防线 `bc1c8c9` 后lint PASS、全量 **1315 passed/9 skipped**。9项跳过属于既有环境测试，不把它们算作通过。

## 分步执行

| 阶段 | 新raw / ATM / witness | 90 / 180 有效n | 累计HTTP | 验收 |
|---|---:|---:|---:|---|
| SPY两日闸门 | 8 / 2 / 4 | 39/33→41/35 | 10 | SQL/API/DEV一致、旧值保护、7/30/60全序列、feature重放0均PASS |
| SPY其余 | 93 / 25 / 51 | 41/35→66/60 | 73 | 对账恢复，SQL/API/DEV、旧值、7/30/60序列、feature重放0 PASS |
| NVDA | 67 / 17 / 34 | 44/43→61/60 | 114 | 同上 PASS；无需备用 |
| AAPL | 79 / 20 / 40 | 41/40→61/60 | 152 | 同上 PASS；无需备用 |

主范围64父键/256合同日/82执行区间全部完成；新增247 raw /64 ATM /129 reconstructed。9个合同日已挂牌但没有合格aggregate（SPY7/NVDA1/AAPL1），不是权限错误，也不能据此断言完全无成交。每个父键仍有合格双方合约、strict observed rate和可解IV，64个父键实际全部有效。合并范围外157个bar丢弃，没有写入额外日期。

累计HTTP **152/220**，reference67/90、bars85/130；计入3次控制各自的detail+aggregate，全部attempt/control/recovery均未重置。SPY中断后的25组目录复用而非再次HTTP。方案预算先前只列3个control aggregate，实际另有3个control detail，主范围正常请求由149变为152；仍在批准硬上限内。剩余68并不是追加范围的授权。三名均达到60，因此9个备用日期（36合同日）**全部未执行**。

## SPY目录后连接中断及恢复防线

SPY其余25组历史as_of已全部验证后，在第一个aggregate前连接关闭。agent_reader核实data_writer角色设置 `idle_in_transaction_session_timeout=15s`，数据库postmaster未重启；原入口在外部HTTP期间保留了只读事务。此中断没有新增raw，累计total35/reference28/bars7完整保存。旧异常分支还会因对已关闭连接rollback而把receipt留为running，不能据此假定仍在工作。

隔离修复 `7c6b118`：外部HTTP前提交只读事务；会话级advisory lock跨COMMIT保持；closed连接不rollback掩盖原错，先写stopped状态。每组完成后保存历史reference记录；恢复仅复用与原phase匹配、重新验证标准成员的已对账证明。3项新增事务边界/断线回执/cache测试，全量1313 passed/9 skipped，lint PASS。

本次特殊恢复用原只读历史目录真实合同字段，加上中断回执中已完成25组membership验证的证明；逐合同日读库确认新raw为0。保留原中断action/job/log/receipt，35计数继承，不重抓目录、不重置预算；没有生成或伪造市场行情。

受限probe加载已测隔离代码，不是发布。长source拆为明文argv片段避免Linux单参数长度限制，源码字节保持不变。

## 验收边界与私有证据

执行前保护三名06-26至09-03全记录：186574raw /1950ATM /94798reconstructed，包含此前已验收范围。每阶段逐主键全值比较均PASS；额外raw/feature主键只属于已执行批准phase；7/30/60全252-session序列保持；有效n以Research reader逐session复算，不用Job Complete/bar行数替代；DEV三名实际页面与SQL/API一致，90/180的history_status=sufficient、withheld=null、percentiles有值。

每阶段feature dry proposed=实际新增，stored-source读回及重复执行新增ATM/source均0。最终raw重放使用已验收阶段原回执的逐phase SHA；所有未在DB中的目标日必须与该ticker原listed_no_eligible_aggregate数完全对账，unknown/invalid_price/删除行/中断回执不能跳过。247个已存目标日全部preserved，9个已证实空日继续保留缺口，不造raw行；四阶段重放 **0 HTTP /0 raw新增**，计数保持152。最终全部三表与重放前逐值一致。合法0由append/regression覆盖，missing不能转换为0；本次保护范围原raw中的0-volume/0-trade_count实际为0条，不能虚构零值样本。

平台动作（受限probe，不是发布）：SPY闸门raw `probe-20261011033809` / feature `probe-20261011033839`；SPY其余恢复raw `probe-20261011034509` / feature `probe-20261011034640`；NVDA raw `probe-20261011034824` / feature `probe-20261011035036`；AAPL raw `probe-20261011035134` / feature `probe-20261011035240`；最终raw重放 `probe-20261011035408`。原SPY中断Job `probe-20261011034020`留证，未算成功。

私有目录 `/Users/vision-mac-trader/agent-work/td-172-142-evidence/`：depth-before-*、depth-{phase}-{raw,feature}-action/platform-receipt/log/receipt、depth-{phase}-acceptance/checkpoint/dev.txt/dev.png、depth-checkpoint.json、depth-final-replay-*、depth-final-acceptance.json；源文件/实际市场行/合同清单不入Git。最终四阶段验收hash重新核对PASS。DEV固定数据as_of=2026-10-09，浏览器localhost:5173；API为本地Research只读reader8795。代码改变仅在Plugin隔离分支，Research本批复用已测repair，无新代码发布。

复核命令：Plugin隔离目录用已配置Python runtime执行 `make lint && make test`；私有证据目录用Research venv运行 `depth-budget-index.py`、逐阶段 `depth-acceptance.py PHASE`（对应DEV文本与只读snapshot需存在）；`depth-final-acceptance.json`为最终全值/预算/digest结果。执行命令不得随意重跑，必须沿原checkpoint和accepted receipt。

本批验收PASS，隔离代码已提交，**未发布、未扩大范围**。累计所有此前已批准批次为849 ATM /1840 source /362 raw（本批64/129/247另列）。整债不因60显示门槛闭合：NVDA >90-DTE有效expiry只有60 session，仍未达到TD-142 ≥150目标；TD-172 725×59全名单历史breadth缺口及短腿缺口未补，本批180–220 DTE不能冒充50–100 breadth改善。防线尚未常规发布、runtime告警回执仍NOT VERIFIED。TD-172/142保持在做，不自动开始下一批。
