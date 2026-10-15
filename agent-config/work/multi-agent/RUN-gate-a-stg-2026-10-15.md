# 2.2 验收（Gate A）在 STG 上的跑法与进度

起草 2026-10-15 16:00（统筹线程 local_accccb4e）。测试定义见设计 v5 §5.2 的 Gate A 表；Owner 参与方式按 10-15「验收参与 一」（`PLAN-gate-a-stg-2026-10-15.md` §2）。
STG 现状：平台 `de64cff`（16:35 发，`bifrost-deliver-platform-1792099853`）；agentd `3b4e372`（14:55 装，主机 `mbp-dev`）；MCP `54a02e7`。
今天两趟走查已经走通「派 → 领 → 做 → 确定性验收 → 评审 → accepted」（M-2，Cursor 写、Codex 评审），报告在 `~/agent-work/stg-walk/`。

查库：`psql "host=192.168.10.73 port=30432 dbname=bifrost_platform_stg user=agent_reader"`（只读，表在 `agentrt.*`）。
提 mission 要新版 MCP 的 `propose_mission`（`dbf30a9` 之后启动的会话才有）。

## 第二批一览（16:30–17:55）

测试身份 `agentd:gate-b` 用 `~/agent-work` 外的测试客户端（统筹线程 scratchpad 的 `gateb.py`）在接口层扮第二台主机；mbp-dev 的 agentd 用 Owner 给的 sudoers 行发 `STOP`/`CONT`/`KILL`。
mission：M-3（T08，后来也放 T22 组合测试）、M-4（T22；T01、T02 也在这里跑）、M-5（T34）。T01、T02 自己的 mission 是托 M-2 会话代建的，被那个会话的 auto mode 分类器按 goal 字面拦下（LESSONS 143）；这两项改由统筹方在自己的会话里、按 Owner「验收参与 一」的授权逐个动作跑，没有让别的会话代建。

- 过：T01（branch）、T02、T08、T22 ①（宽限内、超过宽限）、T22 ③、T34 ①②③⑥⑦、T36（接口）。
- 有缺口：T34 ⑤（Progress 不显示「结果未持久化」，F-T34-5）。
- 卡在 Owner 的决定上：T34 ⑧ 后半（采纳保全结果）要一个与 codex 不同提供方的评审者（F-T08）。
- 没跑：T01 external、T22 ②（第二个 agentd，Owner 起）、合盖 20 分钟、T22 ④（gate-b 推不了分支）、T34 ④（上传中途重启 agentd）、T25、T33、T35、基准 6 题。
- 新发现：F-none、F-T08、F-scale、F-T34-5、F-T34-8、F-T34-8b、F-T01（见文末）；卡点 LESSONS 143–148。

## 每项的状态

| 项 | 怎么跑 | 要 Owner | 现在 |
|---|---|---|---|
| T01 恢复 | 尝试进行中 `sudo -u bifrost-agentd /bin/kill -9` agentd，launchd 拉起；branch 一次；external 用种下的任务 | sudoers（第 1 步） | **branch 那一半过**（16:58，M-4 任务 `t_01M50S5AWEKN85XFCFQ98RWQPJ`，第 3 次才测到）：codex 在 `sleep 120` 里时 `kill -9` agentd（16:58:46）→ 1 秒内 launchd 拉起新进程；codex 所在进程组 1 秒内清空；尝试 `a_01M50S5M…` 记 `attempt_ended{daemon_restart, group_cleared: true}`（21:58:46.79Z），任务回 ready，0.1 秒后第 2 次尝试领走（隔离号 30）并正常提交 `ca5a92c3`；旧尝试只有 leased/started/checkpointed/ended，没有第二次提交。重启后的 agentd 先给残留工作区存了检查点 1。前两次没测到：第 1 次 codex 10 秒做完、kill 落在提交之后；第 2 次脚本用 `pgrep -f` 拿到两个进程（agentd 跑执行者时派生的 `agentd launch` 子进程命令行也带这个路径）。**external 那一半没跑**（第 2 轮不派 external，种任务要直写库） |
| T02 租约 | mbp-dev 与 gate-b 同时领同一批；拿旧隔离号心跳、提交 | gate-b（第 2、3 步） | **过**（16:46–17:05，任务在 M-4，因为 T01、T02 的 mission 没建出来）：同一批 3 个任务，gate-b 领 t02a（隔离号 20）、mbp-dev 领 t02b（21），t02c 等到 mbp-dev 空了才被它领走（每台主机 1 个槽，gate-b 占着槽时再领回 204）；每个任务只有一次活着的尝试。409 共 10 次：自己尝试用旧号 19 / 别人的号 21 心跳和提交；用 mbp-dev 那条尝试自己的号以 gate-b 心跳、提交、`ended`；t02a 判 lost 之后用原号 20 心跳和提交。t02a 的尝试不心跳 → 到期 5 秒后 `attempt_stale` → 宽限内心跳 `attempt_renewed`（回 leased）→ 再不心跳 → 宽限过后 5 秒 `attempt_lost`、任务回 ready、mbp-dev 起第 2 次（隔离号 32） |
| T05 无证据的声明 | 任务书不写 verify；报告写「测试全过」 | 无 | **过**（16:08）：M-1 任务 `t_01M50P8BBTT3PRZ9WT4RGP2784`，实现尝试自报 done，确定性验收 `v_01M50P9S0B09P8ZDWY336FEPJE` 判 fail，verify.json「the spec names no verify command」；任务进第 2 轮，从未 accepted |
| T06 失败的实验 | 验收故意第一次失败、第二次通过（标记文件在 bifrost-agentd 的 $HOME） | 无 | **过**（16:09），差「进展视图」没直接看：M-2 任务 `t_01M50P8BGEJWJV767MMT1G16ZP`。第 1 轮实现 `a_01M50P92`（`c07d318c`，报告在）→ 验收 `v_01M50PA7` fail（证据 858 字节，原文是那条命令与退出码 1）；第 2 轮 `a_01M50PA7`（`667fe2ab`）→ `v_01M50PBK` pass。失败那轮的尝试、验收、证据都在，没被覆盖。观察：`agentrt.artifact` 的 task_id / attempt_id 两栏对 agentd 上传的产物是空的（经验收行和尝试行能找到）。另：M-1 第 1 次尝试（persist 被拒）产物一份没有，那是 TD-349 |
| T08 独立验收 | 作者的提供方领评审；作者领自己的验收 | gate-b | **过**（16:40–16:45，M-3）：暂停 mbp-dev 的 agentd，gate-b 以 `exec:codex/openai` 当作者领实现任务、走完提交。① 验收任务 ready 期间 gate-b 以同一执行者连领两次，都是 204（领活是长轮询，不点名任务，「拒」就是不给，不回 409）；验收岗位的候选只有 `verifier/exec:deterministic/local/*`。② 第二个任务 `t_01M50RBQ…` 验收过后评审 ready，gate-b 以作者的 codex/openai 领 → 204；`route_decided` 排除 `reviewer/exec:codex/openai/*`，原因「not independent of the subject's attempts」。**由此发现 F-T08**（见下） |
| T10 预算 | 用 M-1 剩下的 2 次：T05 的实现 + 验收用完，第 2 轮不该再派 | 无 | **过**（16:08–16:11）：M-1 预算 6 次、尝试 6 次（最后一次 21:08:07Z 开始）；T05 第 2 轮 21:08:13Z 进 ready 后一直没被领（3 分钟以上），账本与尝试一一对上。没有一条「预算用完」的事件，看不出为什么不派（记为观察） |
| T22 掉线与接管 | ① SIGSTOP 5 分钟、合盖 20 分钟；② 第二个 agentd；③ 缩 platform-workers 到 0；④ 推分支与过期同时；⑤ 存储层夹具已有 | sudoers、合盖、第二个 agentd 由 Owner 起 | **① 宽限内恢复过**（22:10–22:15Z，M-4 `t_01M50SV96TAK7SPNKHH6R983DY`）：codex 在 `sleep 120` 里时 SIGSTOP agentd 300 秒，子进程照跑；租约 22:12:23 到期，10 秒后 `attempt_stale`；SIGCONT 后 0.1 秒内 `attempt_renewed`，接着 computed → persisted → submitted，一次提交。gate-b 那一侧同样：到期 5 秒后 stale、宽限内心跳 `attempt_renewed`、宽限过后 5 秒 `attempt_lost`（见 T02）。**① 超过宽限、③ 待跑**：#21（`scale_deployment` 缩 workers 到 0）21:49:19 批准并执行成功，但 Argo 的 selfHeal 同一秒又扩回 1，控制器一直在跑，没测到（F-scale）；改走 overlay 补丁，与 ① 超过宽限合跑（M-3，探针 `t_01M50V3GR2…` 与 `t_01M50V4YB7…`）：22:32:45Z 在 codex `sleep 1500` 时 SIGSTOP mbp-dev 的 agentd、不恢复；gate-b 领探针 3 后只心跳一次（22:33:10）；infra `6015863` 把 workers 设为 0，22:34:01Z 同步生效（Argo 同步到该提交、Pod 0 个），此后租约循环不跑，两个尝试在库里一直是 running/leased。两个宽限分别 22:49:23、22:50:10 截止。**③ 过**：22:50:31 两个尝试在库里仍是 running、都已过宽限，gate-b 续租和打检查点都回 409（按数据库时间判，不等循环）。**① 超过宽限过**：22:50:31 SIGCONT agentd，1 秒内进程组 93979 清空，agentd 先 `attempt_salvaged`、再 `attempt_ended{lease_lost, group_cleared: true}`（22:50:32.17），任务回 ready 并立刻被重做（领活在 API 侧，控制器停着也能领）。infra `16f7186` 回退，22:51:31 workers 恢复，控制器随即把 gate-b 那个尝试判 lost。**④ 没跑**：gate-b 推不了分支（没有 Gitea 写权限），要么让真 agentd 在推送时过期，要么给 gate-b 一个 agent 组织的推送身份。**合盖、② 等 Owner 时间** |
| T25 状态只由事件改 | 写路由模糊测试；运行时角色直写状态表 | 无（直写要用 `run_probe_pod` 带运行时库的身份） | 待跑 |
| T32（经接口） | 反例经 propose_tasks / propose_plan_change 提交 | 无 | **不依赖计划的部分过**（16:06）：依赖成环、跨 mission 依赖、依赖不存在、计划与理由都没有、挂到不存在的步骤、提议带 subject、ref 重复，加两条改计划（不存在的父节点、把任务移到不存在的步骤），9 条全部 422，错误写明约束（成环与挂靠由库里的触发器挡）；任务数 6、事件数 120 前后不变，没有占幂等键。**缺前提**：STG 上没有计划树（plan_node 0 行，建根只有存储层函数，导入 2.3 才有），挂到 item、挂到别的 mission 的步骤、评审挂不同步骤、done_rule、父子类型、改绑、参谋长席位那几种跑不了；「并发两条依赖」经接口构造不出来（依赖只能指向已有任务或同批 ref）。另：role 与 effect_class 的越界值被 MCP 的枚举先挡住，到不了平台 |
| T33 证据绑定版本 | 旧 PASS 对新部署；交付记录读不出；T19/T20 规格 | 无 | 待跑 |
| T34 结果持久化 | 八种故障，gate-b 写测试客户端在接口层制造；重启用 sudoers | sudoers、gate-b | **接口层五种过**（17:08，M-5 `t_01M50SP2C0464AJP3TDBJVCH8V`，gate-b 尝试 `a_01M50SP4…`）：⑥ 三个检查点、第二个丢回复，重试拿回原响应，事件 seq 1、2、3 各一条；① 上传传一半断开，表里 0 行；② 再传整份 `created: true`、同一内容再传 `created: false`，产物 1 行、`artifact_put` 1 条；③ persist 丢回复后重试拿回 `persisted: true`，`attempt_persisted` 1 条；⑦ submit 丢回复、尝试已是 submitted 时重试拿回 `submitted: true`（不回 409），`attempt_submitted` 1 条。客户端：`gateb.py drop` 发完整请求后不读回复就断开，`cut` 发一半请求体就断开。**⑤ 有缺口**：主机永久丢失（M-5 `t_01M50ST4M08FCR783MZ4J9NCWD`，gate-b 打检查点 1 后不再出现），Progress 只显示 `maybe_stuck`「the lease lapsed and was not renewed」，没有「结果未持久化」、最后检查点的时间和已多久没有持久化（F-T34-5）。**⑧ 两次都没走到「采纳保全结果」那条路**：第一次（M-4 t02a）保全落在新尝试提交并验收通过之后，只记 persisted、不建验收。第二次（t34b，22:26:46Z 保全时新尝试在 `sleep 120` 里）：7 秒后控制器为保全结果建了验收任务 `t_01M50TST9F…`，但唯一的确定性验收主机 mbp-dev 的槽被新尝试占着，排不上；新尝试 22:28:58 先提交，控制器把保全验收标 accepted、理由「the subject is verifying: its own attempt's result goes first」，任务只有新尝试的一条验收记录（没有双采纳）。保全的尝试 `persisted_at` 有值、仍是 lost。单主机、每台 1 个槽时这条路走不到（F-T34-8）；第三次（M-3 探针 3，T22 组合测试之后）：gate-b 22:52:08 保全 lost 的尝试，控制器 12 秒后建保全验收，gate-b 以 `exec:deterministic/local` 领下、真跑 `true` 交 pass，22:53:35 `verification_recorded` pass（钉在 lost 的那次尝试上），随即建保全评审——评审岗位只有 codex、被独立性排除，没人能领（F-T08）；新尝试 22:54:43 提交、验收通过、又建一个评审。所以「保全→确定性验收通过」这截走通了，「评审通过→采纳保全结果→同一事务取消新尝试」要等 F-T08 解决才能在 STG 上跑。新尝试提交后保全评审仍挂 ready（F-T34-8b）。④ 上传中途重启 agentd 待跑 |
| T35 规则集 | 未签放宽、收紧、过期、body_json 不等、假收紧、错 namespace 签名、未知字段、空信任锚 | 签一份错 namespace 的（签授权第 2 版时顺带） | 待跑（rule 路由没有 MCP 工具，`rule.sh` 要 operator 令牌：由 Owner 跑，或补 MCP 工具） |
| T36 血缘尾注 | agentd 推提交，`/api/v1/lineage` 返回任务号 | 无 | **接口部分过**（16:36）：修法（血缘也扫 `AGENTRT_GIT_ORG`，同一 Change-Id 落地时不丢 agent 提交）在主线 `de64cff`，16:35 发 STG。`get_commit_lineage` 按 Change-Id `Ia6260f33…` 查到 M-2 的提交 `f30cdd8a`，仓库 `bifrost-agents/bifrost-platform`，`task` = `t_01M50M1CZSDN8PNHRH8C2241RS`，分支 `agent/t_01M50M1C…/a1`，`landed: false`（分支没合，对）；整表里 agent 组织 6 个提交都带任务号，`agent_no_lineage` 0。页面那一半见 F-T36b |
| 基准 6 题 | Go 2、Python 2、TS 1、shell 1，Cursor 写、Codex 评审，不插手 | 无 | 待出题 |

## Owner 的三步（「验收参与 一」）

1. sudoers 一行（只许以 bifrost-agentd 运行 `/bin/kill`）——看板「需要你做的」第 1 条，命令在那里。
2. 审批单 #20（`owner_run_command`）：生成 gate-b 令牌、放进 STG Secret。平台映射已推（infra `977f2ba`）。令牌放好后统筹线程重启 STG platform-api，用 gate-b 领一次活完成主机登记。
3. 签常备授权第 2 版（hosts 加 gate-b；放宽要签名，主机须已登记）。验收后收紧回 v1 的主机名单（收紧不用签）。

## 发现（随跑随记）

- F-T36：血缘不扫 agent 组织（已修，`de64cff`，见上表）。
- F-T06：被拒的 persist 连报告一起丢（TD-349）。
- F-T10：预算用完不再派活，但没有事件写明原因（任务停在 ready，看起来像「没人领」）。
- F-T36b：Console 血缘页点任务号只在本页筛选，没有任务详情可跳（复核 210 B1）；Console 没有任务页（2.5 界面）。T36「血缘页能从提交点到任务」要 Owner 定：算筛选过，还是等 2.5。
- F-art：agentd 上传的产物在 `agentrt.artifact` 里不记 task_id / attempt_id。
- F-none：无副作用（`effect_class: none`）的任务没有推送提交，控制器给验收的规格里就没有 `commit`（`store/accept.go` `checkSpec.put` 只在非空时写），agentd 于是在空目录里跑验收命令（`agentd/run.go` `Run`：`repo`、`base` 有一个为空就建空目录）。M-3 第一个 T08 任务的 `test -f api/go.mod` 两轮都判 fail、任务进 blocked。修法：没有推送提交时用任务的 `base_commit`。第二批之后的探针一律用 `true` 绕开。
- F-T08：评审岗位只有 `reviewer/exec:codex/openai/*` 是 active（claude 在 qualifying），实现岗位又优先 codex，所以 **codex 写的任务都没人能评审**，评审任务永远 ready（M-1、M-3、M-4 现在都卡在这）。要 Owner 定：放一个与 codex 不同提供方的评审者上岗（claude 过资格、或让 cursor 当评审），或者实现岗位改成优先 cursor。
- F-scale：`scale_deployment` 对 Argo 自动同步（`selfHeal: true`）的应用回报「deployment scaled to 0 replicas」、`ok: true`，Argo 同一秒就改回去（Deployment 事件 21:49:19 缩到 0、同秒扩回 1）。动作应在目标归 selfHeal 应用管时拒绝或写明「会被改回」，否则审批人批的是一个没有效果的动作。
- F-T34-5：Progress 对主机已不在、结果没持久化的尝试只显示 `maybe_stuck`，缺设计 T34 ⑤ 要的「结果未持久化」+ 最后检查点时间 + 已多久没持久化。
- F-T34-8：保全结果的验收要排在确定性验收主机上；只有一台主机、每台 1 个槽时，它被正在跑的新尝试占着，保全的结果永远排在新尝试后面。现在的配置下设计 T34 ⑧「保全先验过、取消新尝试」不会发生；要么保全验收不占执行槽（确定性检查很便宜），要么接受「新尝试优先」并改设计。
- F-T34-8b：新尝试提交后，保全结果的评审任务（`t_01M50WAPP…`）仍挂 ready；`salvagedOpen` 只在执行检查时判过时，等有了能评审的人，它会白花一次真评审。控制器应在新尝试提交时把保全的检查一并关掉。
- F-T01：`pgrep -f /usr/local/libexec/bifrost/agentd` 在跑执行者时会拿到两个进程（`agentd launch -- codex …` 子进程），运维脚本要认父进程为 1 的那个。
