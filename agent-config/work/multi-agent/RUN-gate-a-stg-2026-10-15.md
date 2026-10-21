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

## 10-20 补跑：T25、T33、T35、T22 ④、T34 ④、T01 external（线程 local_6f3ef5b9）

对应运行时计划 R2:2.2-28。依据：设计 v5 §5.2 Gate A 表；平台主线 `8f30a9f6`；STG 库 `bifrost_platform_stg` 只读查（`agent_reader`）。
新测试在平台分支 `w31/gate-a-rest`（worktree `~/agent-work/gate-a-rest/bifrost-platform`，在 `8f30a9f6` 之上四个提交 `a86bcc23`、`e03fdf1c`、`1c6eaa67`、**头 `5ce3467e（变基前 ec17dec9）`**，可快进），**只加测试，不改生产代码**；没推、没合并。
复核（Claude 写、Codex 复核，按停线规矩）：449 第一轮「先改」3 A 4 B 3 C → `e03fdf1c` → 451 第二轮「先改」4 A 2 B 1 C → `1c6eaa67`（剩下的 A 都有最小修法、方向不变，照改，每条配在修之前的代码上失败的回归对照，已实跑）→ 452 确认轮「先改」1 A 1 B → `5ce3467e（变基前 ec17dec9）`（照改并配回归对照）→ 454 窄确认「**可以合并**」0 A 0 B，收线。报告 `~/agent-work/codex-review-{449,451,452,454}/REPORT.md`（450、453 是别的线程的号）。Codex 的沙箱连不上本机测试库，数据库测试由我跑：api 全套 73 个包全过（`1c6eaa67` 的树），agentrtapi / agentd / store 三个包在 `5ce3467e（变基前 ec17dec9）` 上全过，code-health 过。
这一轮没有在 STG 上提 mission、没有写库、没有答或撤任何卡，没有留下要收的 mission。

| 项 | 结论 | 一句话 |
|---|---|---|
| T25 状态只由事件改 | **过**（测试）；STG 直写跑不了，以只读核对代替 | 每条路由模糊测试 + 每条写路由的有效请求都执行到；STG 上 165 个任务、64 个 mission、67 个步骤的状态都等于它最后一条状态事件 |
| T33 证据绑定版本 | **过**（测试）；**STG 上没有可测对象**（F-T33） | 存储层、规则层、架构对照投影层都有测试；STG 上没有一条 gate 验收记录，代码里也没有写 `method='gate'` 的地方 |
| T35 规则集 | **过**（测试）+ STG 现场一条；错 namespace 那一条 **10-20 19:3x Owner 跑过，过** | 八种全在 `TestRuleSet`；STG 上 `standing-envelope:dev` v4 是不带签名的收紧、立即生效 |
| T22 ④ 推分支与过期同时 | **过**（新测试） | 推送被钩子拦住时租约越过宽限、任务被另一台主机重领；放行后提交只落在 a1，任务和新尝试不动 |
| T34 ④ 上传中途重启 agentd | **过**（新测试，真 SIGKILL）；STG 上不用跑 | 五个杀点，接管后产物、persisted、submitted 各一份，任务能进验收 |
| T01 external | **不用跑**（第 2 轮设计上不派 external）；存储层已测 | `store/claim.go:41-44` 只派 none、branch；ended → blocked + 决策卡由 `TestBlockedExternalNeedsAClearedEnd` 证 |
| T22 ② 第二个 agentd | **过**（10-21 03:05–03:25Z，Owner 跑脚本） | 第二个 agentd 12 毫秒退出（「another agentd runs on this host」），没领活；第一个醒来被 409 挡住，同一秒保全并 `ended{lease_lost, group_cleared: true}`，见下 |
| 合盖 20 分钟 | **过**（10-21 03:27–03:48Z，冻结 STG agentd 整个 unit） | 到期 2 秒后 stale、宽限过后 lost；解冻后 409、同一秒保全并清掉进程组、重领；冻结期间 Progress 显示主机失联（T24 后半） |

### T25 状态只由事件改

**数据库一半**（主线已有，`8f30a9f6` 上跑过）：`store/store_test.go` `TestIdentitiesAndTheEventRule` —— 运行时角色直写状态表：不带 `agentrt.event_id` 被拒（「needs SET LOCAL」）、带别的事务的事件被拒（「not written by this transaction」）、带键对不上的事件（同事务里另一个任务的事件）被拒、只改存活列放行（租约只许往后）、存活列和别的列一起改被拒；`review144_test.go` 补事件类型和行号不对的四种。内核一半：`store/kernel_test.go` `TestOnlyListedMoves`（任何函数都只走转移表，每次移动一条事件）。

**路由一半**（新）：`agentrtapi/stateevents_test.go` `TestRoutesMoveStateOnlyByEvents`（+ `stateevents_world_test.go`）。从路由器遍历 Mount 的全部路由（42 条，attempt 路由按 8 个动作分开算），四个世界（基础；尝试在跑；任务已提交；尝试已丢失），每个世界先把每条写路由的**有效请求**照客户端的样子发一遍，再对每条路由、每个身份发随机请求（字段取自包和存储层源码里的全部 JSON 字段名，值取状态词、世界里的 id、数字、噪声；默认种子固定 20261020，`AGENTRT_FUZZ_SEED` 换种子）。每个请求之后：
- 被拒的（4xx/5xx）：一条事件都没追加，除只追加的 event 表外每张表逐行不变；
- 受理的：凡状态变了、或有本次请求的状态事件的任务 / mission / 步骤 / 尝试，按本次的事件从前态重放到后态，每步在转移表里（任务 `taskMoves ∪ adoptMoves`、mission `missionMoves`、步骤 `stepMoves`、尝试按事件），每步有原因（正文 reason / cause、`cause_event_id`；或者是三种「由同事务里关于同一任务的那条事件引起」的移动之一，且那条事件在内核写它的位置上：→running 由 attempt_started、→submitted 由 attempt_submitted（都在本次移动之前、本行上一步之后），→ready 由 route_decided（在本次之后、本行下一步之前）——STG 上没写 reason 的任务移动全是这三种），步骤的 `state_event_id` 是最后一步；新行由本次的创建事件建出；
- 每个世界末尾每条流的哈希链校验通过；
- 最后逐条要求：每条写路由（每个 attempt 动作；ended 既打一次已 lost 的、也打一次活的）的有效请求被受理，写类的追加了事件、只答不写的一条事件都没追加；除发考卷（`GET exams/{job}`，发卷即记录）外的读路由从没追加过事件；没归类的写路由直接失败。prunes 只走空报告（这几个世界里没有做完的任务可清理分支；有内容的报告由 `TestPruneRoutes` 测）。

结果：固定种子约 6,200 次请求全过，种子 1–5 另跑全过，api 全套 73 个包全过，code-health 过。阳性对照（临时改坏，都已还原）：测试的转移表去掉 ready→leased、要求原因写在正文里、内核把 `to` 记成旧状态、内核结束活尝试后不释放任务、`GET prunes` 偷偷追加一条 note——五种都变红（后两种在上一版测试 `e03fdf1c` 上是绿的，这正是复核 451 指出的缺口）。检查器自带负向对照 `TestStateEventCheckerCatches`，每条标明是回归还是原有行为：步骤从 dropped 移出、净状态不变但中间一步记错、只有一条无关上传 / 同任务的 note / 同任务的检查点当原因、再次 ready 却只有暂停前那条 route_decided、running 的 attempt_started 在更早一步之前、被拒请求改了标题、导入头旁边冒出一个没有创建事件的节点、尝试没开始就提交，都被抓到；把检查器改回复核前的规则，这些回归用例都变红。

**STG 一半**：run_probe_pod 带运行时库身份直写**做不到**——STG 平台的探针策略（`k8s/overlays/platform-stg/config/actuation-policy.yaml` `probe.env_from`）只许 research、plugin-market-data、plugin-flex-query 三个命名空间用 env_from，`bifrost-platform-stg` 不在内；允许的镜像里也没有带运行时库凭证的。改为只读核对 STG 库（21:19–21:30Z）：
- 迁移账本 `agentrt.schema_migration` 六个文件的 sha256 与主线 `8f30a9f6` 的 `migrations/000{1..6}*.sql` 逐个相等，状态表的 `*_00_event`、`*_10_guard` 触发器 21 个全部 enabled（`tgenabled = 'O'`）：测试证明的守卫就是 STG 上在跑的那份；
- 165 个任务的状态都等于它最后一条状态事件（task_state_changed 的 `to`；没有就是 proposed），64 个 mission、67 个有状态事件的步骤同样（步骤的 `state_event_id` 也对），0 处不一致；
- 932 条 task_state_changed 里 481 条正文没写 reason，全部在同一事务里有关于同一任务的起因事件：attempt_started（168，leased→running）、attempt_submitted（148，running→submitted）、route_decided（165，proposed→ready）。
要不要另由 Owner 拿运行时库口令在 STG 上直写一次：**建议不用**，守卫同一份、测试已证。

### T33 证据绑定版本

主线已有、`8f30a9f6` 上跑过：
- `store/facts_test.go` `TestStandingGate`：gate PASS 只对环境现在跑的东西算；别的测试编号、规格、环境、提交都不算；新部署把做完的步骤退回 active（原因 `standing_lapsed`），旧部署回来又算；交付记录读不出时什么都不动（不判做完）。
- `store/progressarch_test.go` `TestArchTickFollowsTheDeployment`：架构对照那一行——没记录部署是 unknown，新部署把勾拿走、旧的回来还回；T19、T20 同一份规格只让 T19 过时整行是 false 且原因只点名 T20。`TestArchRecordedDeploymentThatIdentifiesNothing`：部署记录的引用是 null、不是对象、为空，都是 unknown。
- `plan/plan_test.go` `TestGateUsesTheExactTestID`（T21 的 PASS 不满足 T19）、`TestEvalKleene`（读不出的 gate 让整条规则 unknown，`any` 里另一支成立也不行）。

STG：17 行架构对照的完成规则全是 `{}`，`agentrt.verification` 里 `method='gate'` 0 行，`deploy_seen` 事件 0 条（控制器只监视规则里引用的环境，`plan/rule.go:392`）。**发现 F-T33**：代码里没有任何地方写 `method='gate'` 的验收记录（只有 `store/facts.go:339` 读），所以架构对照的勾在任何环境都不可能由门禁测试打上；T33 的「换部署后旧 PASS 不算」在 STG 上没有对象可测。谁来写 gate 记录（门禁运行器）是设计里的空白，要统筹定归哪一步。

### T35 规则集

主线已有：`store/rules_test.go` `TestRuleSet` 一个测试里八种全有——放宽不签名被拒（四种标成 tighten 的放宽：多尝试、新执行者、到期更晚，和标 loosen 的）；签了名但标 tighten 实为放宽被拒；收紧不签名立即生效、到期后不回到更松的上一版（回到最严默认）；版本跳号 / 重号 / 再来 initial 被拒；用发版策略 namespace（`bifrost-release-policy`）和解冻 namespace 签的、别的钥匙签的、信任锚为空、签的是别的文本、没签名，都按未签拒；正文多一个不认识的字段被拒；`body_json` 与原文解析结果不等的行读不出来。另有 `rules/rules_test.go` `TestParseRefuses`、`TestTightens`，`store/rules186_test.go` `TestExpiredRulesGrantNothing`，`store/rules187_test.go` `TestUnreadableRulesGrantNothing`，HTTP 层 `agentrtapi/rules_test.go` `TestRuleRoutes`（别的钥匙签 → 403 unsigned）。编进去的信任锚非空由 `releasepolicy/anchor_test.go` 守。

STG 现场：`standing-envelope:dev` v4 是 10-17 17:00:56Z 的不带签名收紧（事件 1000 `rule_tightened`，`signed_by` 空），到 10-18 v5 签名放宽之前一直在力；其余 17 条签名版本都是 `rule_signed`。

错 namespace 签名在 STG 上的那一条要 Owner 的签名钥匙：脚本 `~/agent-work/gate-a-rest/owner-t35-namespace.sh`（见文末「要 Owner 跑的」①）。它签的是 `concurrency` v2，内容与 STG 的 v1 完全相同（per_host 1、同样的起止时间），即使被误收也什么都不变；先经 `/rules/concurrency/check` 证明文本本身没问题，再以 `-n bifrost-release-policy` 签名交 `/rules/concurrency/sign`，过的标准是 403 `unsigned` 且在力的仍是 v1。

**结果（2026-10-21 00:3xZ，Owner 在终端面板跑，输出 `~/agent-work/gate-a-rest/owner-t35.out`）：过。** 第 2 步平台读文本判这份 v2 是收紧（与 v1 相同，`needs_signature: false`）；第 3 步带 `-n bifrost-release-policy` 的签名交上去，平台答 403 `unsigned`：「signature namespace "bifrost-release-policy" is not "bifrost-agentrt-rule"」；第 4 步在力的仍是 v1（`signed_by` 指纹不变）。比预期更严：本身不需要签名的文本，带了错 namespace 的签名照样被拒，签名不对就不收。

### T22 ④ 推分支与过期同时发生

新测试 `agentd/pushlapse_test.go` `TestPushAsTheLeaseLapses`（真库、真 git 远端、真 agentd 的 Run）：远端 pre-receive 钩子拦住推送；拦住期间租约越过宽限（夹具：超级用户以 replica 角色把 `lease_expires_at` 往回拨，再跑租约循环，尝试 lost、任务回 ready），另一台主机 h2 重领到第 2 次尝试；放行。结果：提交只落在 `agent/<task>/a1`，远端只有 main 和 a1，a2 分支不存在、main 不动；平台拒收 persist（fenced），agentd 保全该提交（`attempt_salvaged` 1 条，a1 有 `persisted_at`、仍是 lost），a1 没有 persisted / submitted 事件；推送落地前后任务的状态、version、状态事件数和 a2 的状态都不变。阳性对照：把尝试分支一律命名成 a1，测试变红（晚到的推送落在新尝试的分支上）。

### T34 ④ 上传中途重启 agentd

新测试 `agentd/handover_restart_test.go` `TestRestartDuringTheHandOver`：agentd 以独立进程跑（测试二进制带 `AGENTD_TEST_DAEMON`，`restartdaemon_test.go`），代理在选定的请求上停住后由测试 `SIGKILL` 它，再在同一登记和工作区上起新的 agentd 接管。五个杀点：报告在路上（平台没收到）；报告只发了一半就断开（关闭写端后等平台回 4xx 才杀，证明平台读到了这半截）；平台收下报告、回复没回来；分支已推、persist 在路上；平台记下 persist、回复没回来。每个杀点先核对死时平台和远端的样子（报告几份、persisted 几条、分支在不在），接管后：每个产物一条 artifact_put、report 和 log_tail 各一份、`attempt_persisted` 1 条、`attempt_submitted` 1 条、分支上一个提交且等于平台记的那个、登记清空，`StartVerification` 把任务推进 verifying。阳性对照：接管时无视登记里的「已准备」重做提交，第五个杀点变红（persist 冲突，任务停在 running）。
没覆盖的窄窗口：本地 git 提交已成、登记还没写「已准备」时被杀（代理看不到这一刻）；按代码，重启后会软重置到 base 重新提交，此前没推过，所以不会有第二个提交上远端。
STG 上不用跑：手动重启 agentd 落不进上传那几毫秒；平台侧幂等和 agentd 的登记接管都在上面这条测试里用真进程、真库测了。

### T01 external

不用跑。第 2 轮不派 external 类（`store/claim.go:41-44`，`dispatched = none, branch`；只有测试导出的 `ClaimExternalFor` 能领），STG 上种这种任务要直写库。平台侧的行为在主线测试里：`store/kernel_test.go` `TestEnded`（external 任务的尝试 `ended{daemon_restart}` → 任务 blocked；同一尝试重复报得到同一结果、别的主机报被拒）、`TestLeaseSweep`（external 的尝试 lost → blocked），`store/blockedcard_test.go` `TestBlockedExternalNeedsAClearedEnd`（进程组已清的 → 决策卡写明「no host takes external work yet」；没清的不出卡）。agentd 接管与任务类别无关，branch 那一半 10-15 在 STG 上真跑过（`t_01M50S5AWEKN85XFCFQ98RWQPJ`）。

### T22 ② 与合盖（10-21 01:58–04:30Z，M-93、M-95；T24 后半一并）

执行者：STG mission M-93、M-95（标题「W-31 Gate A on STG: T22 case 2 and the lid drill…」，effect none，预算 20 次 / 8 小时，在常备授权内、直接 active），各一件实现任务，任务书只让 codex 跑一条 `sleep`：睡到 04:30Z 与 45 分钟中较早的那个（STG 每次尝试硬上限 1 小时，`budget:dev`），不改任何文件，verify `true`。这样没有任务会 blocked、也就没有卡；04:30Z 之后的尝试立即交差，任务被收下，mission 自己收成 done。M-93 的那次（01:58–02:43Z）等过了最晚开始时间（Owner 不在，统筹两次替他开脚本都停在口令上）；M-95 排在它后面接上，Owner 在它的窗口里跑了两项。最晚开始时间随长任务更替写在 `~/agent-work/gate-a-drills/watch.log`（Z 与 CDT）。
**收尾**：合盖之后 M-95 的第 3 次尝试 03:47Z 起睡到 04:30Z，约 03:50Z Owner 开始在 STG agentd 上坐考（agentd 停掉），它 03:52Z 转 stale。统筹要求不再让它被领走：03:55:02Z 对 M-95 下 mission 级 stop（`c_01M5E9J8BNNKKJY1SVDDTF87K8`，只挡领活、不改任务状态，不出卡）；M-95 停在 active、任务 ready，等 Owner 定是否解除。M-93 只剩它的确定性验收（`true`）和评审，考完后自己跑完、收成 done。
**偏差**：统筹要的 `needs_owner` 没带上。本线程的 STG MCP 跑在共享检出的 `mcp/platform` 上，那份停在 platform `8948a5c5`（比 main 落后 199 个提交），`propose_mission` 还没有这个字段；改用上面的「不出卡」设计，全程两个 mission 没有出过一张卡。

**T22 ②**（M-95 第 1 次尝试 `a_01M5E5FT4CA19F9CNXDCG0DD5X`，输出 `~/agent-work/gate-a-rest/owner-t22-second-agentd.out`）：
- 03:05:54Z 只对 agentd（pid 1439559）发 SIGSTOP；codex（进程组 1496758）照跑，18 分钟后仍在（`ps` 记录在输出里）。
- 租约 03:07:47Z 到期，03:07:56Z `attempt_stale`；03:22:56Z `attempt_lost`（「lease expired … and the grace passed」），任务回 ready。
- 03:23:54Z 以同一用户、同样的环境和隔离（`systemd-run`，与 `bifrost-agentd-stg.service` 相同的 Environment / ProtectHome / BindPaths）起第二个 agentd：12 毫秒退出 exit 1，日志「agentd: another agentd runs on this host」，没有任何网络请求、没领活。
- 同一秒 SIGCONT：第一个 agentd 的第一次调用（检查点 #5）被平台 409 fenced（「this attempt's lease is not yours」），03:23:54.926Z `attempt_salvaged`、.935Z `attempt_ended{lease_lost, group_cleared: true}`，旧进程组随即不在；然后重新领到这件任务（第 2 次尝试，03:23:55Z）。effect none，没有分支推送，「晚到的推送落在自己的分支上」这一半不适用（T22 ④ 的测试覆盖）。

**合盖**（M-95 第 2 次尝试 `a_01M5E7S94Y2HH43W46NMVVBW35`，输出 `owner-t22-lid.out`）：06 没有盖子，用 `systemctl freeze` 冻结 STG agentd 整个 unit（agentd 和执行者一起停，PROD 的不动）20 分钟。
- 03:27:17Z 冻结；租约 03:28:54.9Z 到期，2 秒后 `attempt_stale`；03:43:56Z `attempt_lost`，任务回 ready。
- 03:47:17Z 解冻：冻结前悬着的那次 claim 立刻超时（客户端超时，无害）；第一次调用（检查点 #1）被 409 fenced；同一秒 `attempt_salvaged`、`attempt_ended{lease_lost, group_cleared: true}`；03:47:32Z 重新领任务（第 3 次尝试，03:47:48Z 起睡到 04:30:00Z）。
- 与真合盖的差别照旧：冻结不停 CLOCK_MONOTONIC，agentd 醒来时计时器已过期、马上发调用，所以测不到「醒来后以为租约还在」那一段；平台按数据库时间判，隔离不受影响。

**T24 后半（停 agentd → 宿主失联）**：每 60 秒用 Progress 自己的 SQL（`store/progress.go` `HostsSQL`，`/hosts` 和 Progress 投影读同一条，`HostLostAfter` 180 秒）对 STG 库只读查一次，存在 `~/agent-work/gate-a-drills/progress-snaps.log`；每 15 秒的简表在 `watch.log`。两次都在 3 分钟内显示失联：T22 ② 时 03:09:20Z 起 `online: false`；合盖时 03:30:43Z 起 `online: false`（`poll_age_s` 184 → 1055），解冻后 03:47:39Z 恢复 `true`；冻结期间 `live_attempts` 先是 1（stale），lost 后 0，恢复后 1（新尝试）。同一段时间这件任务按 `TaskStatus` 的规则是 `host_lost`（主机最后一次轮询超过 3 分钟，优先于 stale）。Console 页面本身没看（不用界面工具），读的是页面背后的同一条查询。

### 发现

- **F-T33**：没有 gate 验收记录的写入方（见 T33）。
- **F-mcp-checkout**：线程的平台 MCP 跑在共享检出的 `bifrost-platform/mcp/platform` 源码上，共享检出不跟 main（10-21 时落后 199 个提交），新加的 MCP 字段（这次是 `needs_owner`）线程里用不到。由统筹定：共享检出定期快进，或 `.mcp.json` 指向一个跟 main 的检出。
- **F-probe**：STG 的 run_probe_pod 不能带平台自己的库身份（env_from 不许 `bifrost-platform-stg`）；设计里「直写用 run_probe_pod」这条路在现行策略下走不通。是否要开，属于策略（RBAC 级）决定，不在这一轮。
- **F-T32-card**（10-21）：STG 的 `card-auto-answer v3` 遇到没有推荐、也没有 AI 评估的计划变更卡，取「不改」（`q_4beba10878543ee3`，04:13:12Z）。所以在 STG 上，常设授权以外的计划变更（`move_task`、`rebind_step`、`drop_step`、加 item）都落不了地，测试夹具也丢不掉：「卡由规则自动答」不等于「变更会生效」。要不要让这类卡在 STG 上取提议的那一项，交统筹定。
- **F-T33-rec**（10-21）：架构行门槛的计划变更卡带不上推荐。`store.gatesRecommend` 算出了「应用」（`card.Recommended = 1`），但 `internal/server/questions_wire.go` 的 `agentRuntimeAsk` 只在卡自带选项（`len(card.Options) > 0`：planner、mission、blocked 卡）时才把 `recommended` 传给问题库。计划变更卡用默认的「应用 / 不应用」，推荐被丢掉，STG 规则只能取「不改」（`q_d58aaf5995349bf1`，04:32:43Z）。TD-397 ② A（STG 照推荐自动应用）因此在 STG 上走不通，PROD 的卡也不会显示推荐。测试只在存储层经假的 asker 看 `card.Recommended`（`store/gates_test.go:464`），没有一条测试走真的 `agentRuntimeAsk`。修法：卡没有自带选项时，`card.Recommended > 0` 也写进 `req["recommended"]`，并把 `RecommendedWhy` 放进那一项的 detail；回归测试经 server 的问题库提一次目录里的规则，断言问题的 recommended 是 a、STG 规则应用了它。
- **F-review-report**（10-21）：评审看不到被检尝试的报告。agentd 给评审的提示（`agentd/executors.go` `promptRest`）只有任务书、检出的提交和 verify.json；store 给评审的规格（`accept.go`）也只带 `verify_report`。effect none 的任务，结果就是那份报告，评审看不到。M-93 两轮评审都判了 FAIL：实现已在 01:58–02:43 睡满 2700 秒，报告是 `slept 2700 s`，评审却在空工作区里找那行输出，又用检查时刻去比 04:30。branch 任务不受影响（评审看得到提交）。

### 要 Owner 跑的（统筹线程转）

① **T35 错 namespace**（建议跑：一次口令，约 1 分钟；不跑不挡 Gate A，测试已证）——在 App 的终端面板里跑（要输钥匙口令或 Touch ID）：

    bash ~/agent-work/gate-a-rest/owner-t35-namespace.sh

最后一行 `T35 (release-policy namespace) PASS` 就是过；输出同时存在 `~/agent-work/gate-a-rest/owner-t35.out`，统筹读它。

② **T22 ② 第二个 agentd**（**已跑，过**：10-21 03:05–03:25Z，见上）（约 21 分钟）——前提：统筹先给 STG 的 agentd（主机 agent-06-stg）派一件执行者会 sleep 30 分钟的任务，带 `needs_owner`；脚本发现 agentd 底下没有执行者就停。只碰 STG 的 agentd，不碰 PROD 的。在终端面板里跑（一次节点钥匙口令）：

    bash ~/agent-work/gate-a-rest/owner-t22-06.sh second-agentd

它 SIGSTOP agentd（执行者照跑）→ 等 18 分钟（租约 2 + 宽限 15 + 1）→ 以同一用户、同样的环境和隔离起第二个 agentd（最多 30 秒，应报「another agentd runs on this host」立刻退出）→ SIGCONT → 看 90 秒日志。输出在 `owner-t22-second-agentd.out`。过的标准（统筹查 STG 事件）：第二个 agentd 退出、没有以 agent-06-stg 领到活；第一个醒来后被 409 挡住、30 秒内清掉进程组、`attempt_ended{lease_lost, group_cleared: true}`，结局 `attempt_salvaged`（有结果时）、任务按 effect_class 处理。

③ **合盖 20 分钟**（**已跑，过**：10-21 03:27–03:48Z，见上）（约 23 分钟）——前提同②。06 没有盖子，用 cgroup 冻结 STG agentd 的整个 unit（agentd 和它起的执行者一起停，PROD 的不动）：

    bash ~/agent-work/gate-a-rest/owner-t22-06.sh lid

输出在 `owner-t22-lid.out`。过的标准：到期约 10 秒后 `attempt_stale`、宽限过后 `attempt_lost`；解冻后 agentd 被 409 挡住、30 秒内清掉进程组、`attempt_ended{lease_lost}`。与真合盖的差别：真睡眠时 CLOCK_MONOTONIC 不走，agentd 醒来后会以为租约还在、要等一次心跳被拒才知道；平台按数据库时间判，这一点不影响隔离，但冻结测不到这个时钟差。真睡眠（`rtcwake`）会连 PROD 的 agentd 一起停，不建议。

先跑 `bash ~/agent-work/gate-a-rest/owner-t22-06.sh check`（只读）看 STG agentd 底下有没有执行者。

### T32 经接口（10-21 04:11–04:14Z，STG，本线 thread 身份）

做法：反例都经 MCP 的 `propose_tasks`（`POST /missions/{id}/tasks`）和 `propose_plan_change`（`POST /plan/proposals`）提交。提议任务一律投给 M-95，它被停止控制 `c_01M5E9J8BNNKKJY1SVDDTF87K8` 挡住，万一误收也派不出去；任务规格是一份写明「不该存在」的 task_spec（`sha256:f134025f…`）。前后用只读足迹核对（`~/agent-work/gate-a-drills/t32-footprint.sh`：节点、任务、M-95 的任务、挂在步骤上的任务、绑定、完成规则、事件、本线事件、`plan_changed`、幂等键）。

夹具：一次提议加了两个测试步骤，R2:2.2 下有进行中的步骤，按常设授权立即落地（事件 4649 → `plan_changed` 4651）：F1 = `R2:2.2-32`（绑已结的 M-94），F2 = `R2:2.2-33`（不绑 mission）。

| # | 反例 | 路由 | 结果（HTTP 422 的原文） |
|---|---|---|---|
| C1 | 任务挂到 item `R2:2.2` | 新增任务 | `task … must hang on a step, not on item` |
| C2 | M-95 的任务挂到 M-94 的步骤 F1 | 新增任务 | `step R2:2.2-32 belongs to M-94, task … to M-95` |
| C4 | F2 的完成规则引用不在 F2 上的任务（M-94 的简报任务） | 改计划 | `the done rule of R2:2.2-33 names task t_01M5E2ZV2PJ880Z90MSN9BKE2A, which is not on this step` |
| C5a | F2 的完成规则引用没绑的审批 #77 | 改计划 | `… names approval #77, which is not bound to this step` |
| C5b | F2 的完成规则引用没绑的问题 | 改计划 | `… names question q_5a850f489345d009, which is not bound to this step` |
| C6a | 步骤直接挂在 round `R2` 下 | 改计划 | `a step cannot sit under a round` |
| C6b | item 挂在 item 下 | 改计划 | `a item cannot sit under a item` |
| C7 | 把 M-27 的验收任务单独移到 F2（离开它的对象） | 改计划 | `verify task t_01M5BSS5QFQ0F4YN8P1HC0AZ29 must sit where its subject t_01M5BSPFV3S9ET52X3JT76HJFS sits` |
| C8 | 复核 142 R3「改绑」：同一提议里先把 F2 改绑到 M-27，再把 M-94 的任务移上去 | 改计划 | `step R2:2.2-33 belongs to M-27, task t_01M5E2ZV2PJ880Z90MSN9BKE2A to M-94`，整个提议回滚，F2 仍不绑 mission |

9 条全拒，原因写明违反的约束。足迹除夹具那一次以外不变：任务 184、M-95 的任务 1、挂在步骤上的任务 0、绑定 0、完成规则 54、`plan_changed` 1（夹具），被拒的提议不占幂等键（幂等键只多夹具那 1 个）。

改绑这一种经接口的形状和存储层不同：`rebind_step` 总是把步骤连同它的任务一起迁走，所以「只改步骤的 mission、把任务留下」在接口上表达不出来。接口上能表达的反例就是 C8；单纯的改绑是合法迁移，要 Owner 的卡。

没跑成的两种：

- **规则引用之后移走任务**（复核 142 R3 第二种）：先要把一个任务挂到 F1、并让 F1 的规则引用它。挂任务（`move_task`）不在常设授权内，会生成计划变更卡（`q_4beba10878543ee3`，提议事件 4662）。STG 的 `card-auto-answer v3` 5 秒后选了「不改」：卡没有推荐，也没有 AI 评估，规则就取不改的那一项（事件 4663 → `plan_change_decided: refused` 4664）。所以凡是要发卡的夹具在 STG 上都落不了地（F-T32-card）。剩下的路只有往一个在用的 mission 里新建任务挂到步骤上：投 M-93 会和收尾抢 agentd；投 M-95 会在被停住的 mission 里多留一个任务。所以没做。同一个拒收由路由调用的同一个函数 `store.ProposePlanChange` 覆盖：`TestPlanChangeOutside` 的 `a task out of the step naming it`，另有存储层 `TestPlanLinks`。
- **参谋长席位提议的任务挂到别的 mission 的步骤**：本线的令牌是 thread / operator（`whoami`：read、propose、upload、stop、drain），没有席位身份。要一个 STG 上 `seat:chief_of_staff` 的令牌或经它的 MCP；接口测试 `agentrtapi/propose_test.go` 里席位走的是同一条路由。

留在 STG 上的：F1、F2 两个测试步骤（planned，没有任务、没有规则，标题写明 STG test）。丢弃（`drop_step`）也要发卡，同样会被自动答成「不改」，所以留着；R2:2.2 的分母在 STG 上多 2。

### T33 在 STG 上（10-21 04:24–04:33Z，platform d360a118）

统筹 04:24Z 把 d360a118（含 TD-397、迁移 0007 和 0008）发上 STG。本线按 TD-397 笔记的做法配门槛目录：
- 在 d360a118 上跑 `go -C api run ./cmd/agentrt-gate catalog -env stg`，得 13 份规格、13 项 `set_done_rule`（本机 `~/agent-work/gate-a-t33/catalog-stg.json`）；
- 13 份规格按原样上传（kind task_spec），返回的 sha256 和目录逐一相同；
- 用 `propose_plan_change`（root ARCH，事件 4810）提交 13 项。

结果：卡 `q_d58aaf5995349bf1` 没带推荐。`card-auto-answer v3` 04:32:43Z 取了「不改」，`plan_change_decided: refused`（4812），13 行规则仍是 `{}`，没有派门槛（F-T33-rec）。

已逐条核对推荐的条件，都成立：
- 平台的库身份是 `platform_agentrt_stg`，环境是 stg；
- 13 行都是 ARCH 下没有规则的 arch_row；
- 13 份规格都存着，kind task_spec，sha256 一致；
- 提交的规则规范化后和 `gaterun.Catalog` 给 stg 的逐字节相同（本地对照了 13 行）。

推荐是在 server 把卡交给问题库时丢的。T33 要等这处修好、发上 STG 以后，用新的幂等键重提。

### M-93、M-95 收尾（10-21 04:16–04:32Z）

- **M-93：stopped，不是 done。** 第 1 轮实现在 01:58–02:43 睡满 2700 秒，报告 `slept 2700 s`，验收（`true`）过。cursor 评审 04:16Z 判 FAIL，原因是工作区里没有那行输出、04:15 还没到 04:30。
  第 2 轮 04:16–04:30 又跑一次，验收过，评审 04:31Z 又判 FAIL → blocked → 卡 `q_b9f58b0617429ed6` 没有推荐，规则取「不做了」→ 任务 cancelled → mission stopped（04:31:46Z）。
  两轮评审都没看到报告（F-review-report）。T22 ② 和合盖的结论不受影响：它们看的是租约、隔离和接管，不是这件任务的结果。
- **M-95：** 第 3 次尝试 04:15:09Z 抢救、结束（没有报告，不 persisted）。之后任务回到 ready，停止控制 `c_01M5E9J8BNNKKJY1SVDDTF87K8` 挡着，没有再被领。

### Gate A 收尾清单（计划步骤 R2:2.2-28，2026-10-21 04:10Z 核对）

逐项对照设计 v5 §5.2 的 Gate A 表。「过」= 表里的过的标准都有证据；证据栏写在哪看。

| 项 | 过了没有 | 证据 | 还差什么 |
|---|---|---|---|
| T01 恢复 | **过** | branch：10-15 STG M-4 `t_01M50S5AWEKN85XFCFQ98RWQPJ`（本文件「每项的状态」）；external：10-20 一节「T01 external」（第 2 轮不派 external，`TestEnded`、`TestLeaseSweep`、`TestBlockedExternalNeedsAClearedEnd`） | 无 |
| T02 租约 | **过** | 10-15 STG M-4 + gate-b（「每项的状态」T02） | 无 |
| T05 无证据的声明 | **过** | 10-15 STG M-1 `t_01M50P8BBTT3PRZ9WT4RGP2784` | 无 |
| T06 失败的实验 | **过** | 10-15 STG M-2 `t_01M50P8BGEJWJV767MMT1G16ZP`（失败那轮的尝试、验收、证据都在、没被覆盖）；「进展视图看得到」当时没直接看，现由 Progress 的近期失败列表（`store/progress.go` `recentView`，SPEC §2.6 T06）及其测试 `TestRecentPicksByEndTime` 证 | 无（STG 页面没有再看一遍；不用界面工具） |
| T08 独立验收 | **过** | 10-15 STG M-3（作者领不到自己的验收、作者的提供方领不到评审，`route_decided` 写明原因）；当时的 F-T08（没有与 codex 不同提供方的评审者）已由 `job:reviewer` v2（cursor）解决，2.2-31 的 M-15 / M-27 都是 codex 写、cursor 评审 | 无 |
| T10 预算 | **过** | 10-15 STG M-1（预算用完不再派、账本与尝试一一对上） | 无；当时的观察「没有事件写明为什么不派」记在 TD-354（P2，未开始），不是过的标准 |
| T22 ① SIGSTOP / 合盖 | **过** | SIGSTOP：10-15（宽限内、超过宽限都测了）；合盖：10-21 03:27–03:48Z，上文「T22 ② 与合盖」 | 无 |
| T22 ② 第二个 agentd | **过** | 10-21 03:05–03:25Z，上文「T22 ② 与合盖」 | 无（effect none，「晚到的推送落在自己分支上」由 T22 ④ 的测试覆盖） |
| T22 ③ 控制器停 | **过** | 10-15 22:34–22:51Z（overlay 把 workers 设 0；续租按数据库时间被拒） | 无 |
| T22 ④ 推分支与过期同时 | **过** | 新测试 `agentd/pushlapse_test.go` `TestPushAsTheLeaseLapses`（上文「T22 ④」） | 无 |
| T22 ⑤ 锁后截止 | **过** | 存储层夹具 `store/kernel_test.go` `TestFenceAndLeaseClock`（「T22 ⑤」那段），按 10-15 计划不在 STG 重做 | 无 |
| T25 状态只由事件改 | **过** | 上文「T25」：`TestRoutesMoveStateOnlyByEvents`（每条写路由、四个世界）+ `TestIdentitiesAndTheEventRule`（直写）+ STG 只读核对 | 无；STG 上用运行时身份直写做不到（F-probe），以迁移哈希、触发器、状态与事件一致性的只读核对代替 |
| T32（经接口） | **基本过，差两种** | 10-15 9 条反例 422（「每项的状态」T32）；10-21 STG 再 9 条 422（上文「T32 经接口」：挂到 item、挂到别的 mission 的步骤、规则引用别一步的任务、没绑的审批、没绑的问题、步骤挂在 round 下、item 挂在 item 下、验收离开对象、改绑后再挂别的 mission 的任务），不留半条记录；接口层测试 `agentrtapi/propose_test.go`、`TestPlanProposalRoute` | ① 规则引用之后移走任务：STG 的卡片规则把夹具卡答成「不改」（F-T32-card），落不了地；同一拒收由路由调用的 `store.ProposePlanChange` 的测试覆盖（`TestPlanChangeOutside`）。② 参谋长席位：缺 STG 的 `seat:chief_of_staff` 令牌。「并发两条依赖」「迁移与新建交错」经接口构造不出来，由存储层 T32（`store_test.go`）证 |
| T33 证据绑定版本 | **测试过，STG 卡在 F-T33-rec** | 上文「T33」：`TestStandingGate`、`TestArchTickFollowsTheDeployment`、`TestArchRecordedDeploymentThatIdentifiesNothing`、`TestGateUsesTheExactTestID`；上文「T33 在 STG 上」 | TD-397 已发 STG（d360a118），但架构行门槛的计划变更卡带不上推荐，STG 规则答成「不改」，规则没落地（F-T33-rec）。修好、发上 STG 后重提 13 项，验一行（`ARCH:owner-three-duties`，T40 不需要库）被部署提交上的真门槛打勾；再换一次部署看旧 PASS 不算 |
| T34 ①②③⑥⑦ | **过** | 10-15 STG M-5（gate-b 测试客户端在接口层制造） | 无 |
| T34 ④ 上传中途重启 | **过** | 新测试 `agentd/handover_restart_test.go` `TestRestartDuringTheHandOver`（真进程 SIGKILL，五个杀点） | 无 |
| T34 ⑤ 主机永久丢失 | **不过** | 10-15 STG M-5 `t_01M50ST4M08FCR783MZ4J9NCWD`：Progress 只显示 `maybe_stuck`，没有「结果未持久化」、最后确认的检查点时间和已多久没持久化 | TD-352（P2，未开始）：Progress 补这三样并且不显示做完；修好后在 STG 重跑一次（gate-b 式客户端打一个检查点后不再出现） |
| T34 ⑧ 采纳保全结果 | **存储层过，STG 未走到** | `store/adopt_test.go` `TestAdoptSalvagedResult`（采纳记录指向 lost 的那次尝试、同一事务取消新尝试、只有一条采纳）；10-15 STG 三次都走不到：每台主机 1 个槽，保全的验收排在新尝试后面（F-T34-8），保全评审另有 TD-353（P3） | 要统筹或 Owner 定：认存储层测试，或在 STG 上给 `concurrency` 放到每台 2 个槽（放宽要签名）再跑一次 |
| T35 规则集 | **过** | 上文「T35」：`TestRuleSet` 等；STG 上 Owner 10-20 跑过错 namespace（403 unsigned，`concurrency` 仍 v1） | 无 |
| T36 血缘尾注 | **接口过，页面待定** | 10-15：`get_commit_lineage` 返回任务号、agent 组织 6 个提交都带任务号 | 「血缘页能从提交点到任务」：现在血缘页点任务号只在本页筛选（F-T36b），没有跳到任务。Console 已有 Crew 页的任务详情（`OwnerCrew`），血缘页没连过去。要 Owner 定：认「按任务筛选」算过，或给血缘页的任务号加一个到 Crew 任务详情的链接（Console 小改） |
| 基准 6 题 | **过（建议算）** | 2.2-31 ★ 的同一次运行（`RUN-r2-stars-2026-10-20.md` 第二节、第五节「2.2-31」）：PROD M-15、STG M-27，6 题提议后零人工写入、22 分钟内全部到结论（4 accepted、2 两轮确定性验收不过而 blocked，答错不是环境）；codex 写、cursor 评审（Gate A 表允许「或反过来，按 capability_fact」）；题目组成改为 Go 3、TS 1、Python 1、shell 1（Python 第二题在 research，运行时派不到），Owner 10-20 11:5x「★ 三条 A」认可这处改写；结果在结论时记进 `capability_score`（PROD 10-20 05:25:56Z：codex `implementer` / `benchmark` 6 次、4 次首轮通过，0.300） | 无。附带发现 F-bench-score：两道不过的题 Owner 选「不做了」（任务 cancelled）之后，在岗成绩把它们剔掉了：PROD 15:28:54Z 变 5 次 4 过（0.376）、15:31:54Z 变 4 次 4 过（0.510）；STG 同样从 6 次 3 过（0.188）变成 4 次 3 过（0.301），失败不再计入；`store/scores.go` 只计 accepted、rejected 和 blocked-as-failed。要不要让「失败后被放弃」仍算失败，交统筹定（可记 TD） |

**还差 5 项**（其余全部过）：
1. **T32 经接口的最后两种**：9 种已在 STG 上被拒。剩下两种：「规则引用之后移走任务」卡在 STG 的卡片规则把夹具卡答成「不改」（认 `TestPlanChangeOutside`，或在 M-95 里留一个不做事的任务当夹具）；「参谋长席位」卡在没有 STG 的席位令牌。
2. **T33**：TD-397 已发 STG，但卡在 F-T33-rec：计划变更卡的推荐在 server 交给问题库时被丢掉，STG 规则答成「不改」。修好并发 STG 后重提，再验打勾；换一次部署看旧 PASS 不算，等下一次 STG 发版。
3. **T34 ⑤**：卡在 TD-352（Progress 补「结果未持久化」+ 检查点时间 + 时长）没做；做完后 STG 重跑一次。
4. **T34 ⑧**：卡在决定。认存储层测试，或 STG 放到每台 2 个槽（放宽要 Owner 签）再跑。
5. **T36 页面**：卡在决定。认「按任务筛选」，或加一个到 Crew 任务详情的链接。
