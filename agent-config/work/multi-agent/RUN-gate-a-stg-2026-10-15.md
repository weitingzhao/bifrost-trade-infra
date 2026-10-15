# 2.2 验收（Gate A）在 STG 上的跑法与进度

起草 2026-10-15 16:00（统筹线程 local_accccb4e）。测试定义见设计 v5 §5.2 的 Gate A 表；Owner 参与方式按 10-15「验收参与 一」（`PLAN-gate-a-stg-2026-10-15.md` §2）。
STG 现状：平台 `e370d39`（15:24 发）；agentd `3b4e372`（14:55 装，主机 `mbp-dev`）；MCP `54a02e7`。
今天两趟走查已经走通「派 → 领 → 做 → 确定性验收 → 评审 → accepted」（M-2，Cursor 写、Codex 评审），报告在 `~/agent-work/stg-walk/`。

查库：`psql "host=192.168.10.73 port=30432 dbname=bifrost_platform_stg user=agent_reader"`（只读，表在 `agentrt.*`）。
提 mission 要新版 MCP 的 `propose_mission`（`dbf30a9` 之后启动的会话才有）。

## 每项的状态

| 项 | 怎么跑 | 要 Owner | 现在 |
|---|---|---|---|
| T01 恢复 | 尝试进行中 `sudo -u bifrost-agentd /bin/kill -9` agentd，launchd 拉起；branch 一次；external 用种下的任务 | sudoers（第 1 步） | 等 sudoers。另：10-15 14:18 重装时意外演练过一次（尝试 stale → 重启后 `daemon_restart` 结束 → 任务回 ready 起新尝试），见 M-1 报告 |
| T02 租约 | mbp-dev 与 gate-b 同时领同一批；拿旧隔离号心跳、提交 | gate-b（第 2、3 步） | 等 #20 与授权签名 |
| T05 无证据的声明 | 任务书不写 verify；报告写「测试全过」 | 无 | **过**（16:08）：M-1 任务 `t_01M50P8BBTT3PRZ9WT4RGP2784`，实现尝试自报 done，确定性验收 `v_01M50P9S0B09P8ZDWY336FEPJE` 判 fail，verify.json「the spec names no verify command」；任务进第 2 轮，从未 accepted |
| T06 失败的实验 | 验收故意第一次失败、第二次通过（标记文件在 bifrost-agentd 的 $HOME） | 无 | **过**（16:09），差「进展视图」没直接看：M-2 任务 `t_01M50P8BGEJWJV767MMT1G16ZP`。第 1 轮实现 `a_01M50P92`（`c07d318c`，报告在）→ 验收 `v_01M50PA7` fail（证据 858 字节，原文是那条命令与退出码 1）；第 2 轮 `a_01M50PA7`（`667fe2ab`）→ `v_01M50PBK` pass。失败那轮的尝试、验收、证据都在，没被覆盖。观察：`agentrt.artifact` 的 task_id / attempt_id 两栏对 agentd 上传的产物是空的（经验收行和尝试行能找到）。另：M-1 第 1 次尝试（persist 被拒）产物一份没有，那是 TD-349 |
| T08 独立验收 | 作者的提供方领评审；作者领自己的验收 | gate-b | 一半有证据：M-1 评审任务 `route_decided` 排除 codex，原因「not independent of the subject's attempts」；领活 409 那一半等 gate-b |
| T10 预算 | 用 M-1 剩下的 2 次：T05 的实现 + 验收用完，第 2 轮不该再派 | 无 | **过**（16:08–16:11）：M-1 预算 6 次、尝试 6 次（最后一次 21:08:07Z 开始）；T05 第 2 轮 21:08:13Z 进 ready 后一直没被领（3 分钟以上），账本与尝试一一对上。没有一条「预算用完」的事件，看不出为什么不派（记为观察） |
| T22 掉线与接管 | ① SIGSTOP 5 分钟、合盖 20 分钟；② 第二个 agentd；③ 缩 platform-workers 到 0；④ 推分支与过期同时；⑤ 存储层夹具已有 | sudoers、合盖、第二个 agentd 由 Owner 起 | 等 sudoers；③ 已授权（「一」） |
| T25 状态只由事件改 | 写路由模糊测试；运行时角色直写状态表 | 无（直写要用 `run_probe_pod` 带运行时库的身份） | 待跑 |
| T32（经接口） | 反例经 propose_tasks / propose_plan_change 提交 | 无 | **不依赖计划的部分过**（16:06）：依赖成环、跨 mission 依赖、依赖不存在、计划与理由都没有、挂到不存在的步骤、提议带 subject、ref 重复，加两条改计划（不存在的父节点、把任务移到不存在的步骤），9 条全部 422，错误写明约束（成环与挂靠由库里的触发器挡）；任务数 6、事件数 120 前后不变，没有占幂等键。**缺前提**：STG 上没有计划树（plan_node 0 行，建根只有存储层函数，导入 2.3 才有），挂到 item、挂到别的 mission 的步骤、评审挂不同步骤、done_rule、父子类型、改绑、参谋长席位那几种跑不了；「并发两条依赖」经接口构造不出来（依赖只能指向已有任务或同批 ref）。另：role 与 effect_class 的越界值被 MCP 的枚举先挡住，到不了平台 |
| T33 证据绑定版本 | 旧 PASS 对新部署；交付记录读不出；T19/T20 规格 | 无 | 待跑 |
| T34 结果持久化 | 八种故障，gate-b 写测试客户端在接口层制造；重启用 sudoers | sudoers、gate-b | 等 |
| T35 规则集 | 未签放宽、收紧、过期、body_json 不等、假收紧、错 namespace 签名、未知字段、空信任锚 | 签一份错 namespace 的（签授权第 2 版时顺带） | 待跑（rule 路由没有 MCP 工具，`rule.sh` 要 operator 令牌：由 Owner 跑，或补 MCP 工具） |
| T36 血缘尾注 | agentd 推提交，`/api/v1/lineage` 返回任务号 | 无 | **缺口**：agentd 的提交带 `Agentrt-Task`、`Change-Id`、`Work`（`agentd/workspace.go:222`），解析器认 `Agentrt-Task`（`lineage/trailers.go`），但血缘只扫交付组织 `bifrost`，不扫 `AGENTRT_GIT_ORG`（`bifrost-agents`），查不到 agent 的提交。**在修**：分支 `w31/agentrt-22-lineage-agents`（`~/agent-work/agentrt-22r`）`c647825` + `7b8586e`（复核 210 先改 A1：同一 Change-Id 落地时 agent 提交被去重丢掉 → 已修），复核 211 在跑；过了合主线、发 STG，再拿 M-2 的提交 `f30cdd8a` 核对 |
| 基准 6 题 | Go 2、Python 2、TS 1、shell 1，Cursor 写、Codex 评审，不插手 | 无 | 待出题 |

## Owner 的三步（「验收参与 一」）

1. sudoers 一行（只许以 bifrost-agentd 运行 `/bin/kill`）——看板「需要你做的」第 1 条，命令在那里。
2. 审批单 #20（`owner_run_command`）：生成 gate-b 令牌、放进 STG Secret。平台映射已推（infra `977f2ba`）。令牌放好后统筹线程重启 STG platform-api，用 gate-b 领一次活完成主机登记。
3. 签常备授权第 2 版（hosts 加 gate-b；放宽要签名，主机须已登记）。验收后收紧回 v1 的主机名单（收紧不用签）。

## 发现（随跑随记）

- F-T36：血缘不扫 agent 组织（见上表）。
- F-T06：被拒的 persist 连报告一起丢（TD-349）。
- F-T10：预算用完不再派活，但没有事件写明原因（任务停在 ready，看起来像「没人领」）。
- F-T36b：Console 血缘页点任务号只在本页筛选，没有任务详情可跳（复核 210 B1）；Console 没有任务页（2.5 界面）。T36「血缘页能从提交点到任务」要 Owner 定：算筛选过，还是等 2.5。
- F-art：agentd 上传的产物在 `agentrt.artifact` 里不记 task_id / attempt_id。
