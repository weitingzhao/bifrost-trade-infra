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
| T35 规则集 | **过**（测试）+ STG 现场一条；错 namespace 那一条**要 Owner 跑一次脚本** | 八种全在 `TestRuleSet`；STG 上 `standing-envelope:dev` v4 是不带签名的收紧、立即生效 |
| T22 ④ 推分支与过期同时 | **过**（新测试） | 推送被钩子拦住时租约越过宽限、任务被另一台主机重领；放行后提交只落在 a1，任务和新尝试不动 |
| T34 ④ 上传中途重启 agentd | **过**（新测试，真 SIGKILL）；STG 上不用跑 | 五个杀点，接管后产物、persisted、submitted 各一份，任务能进验收 |
| T01 external | **不用跑**（第 2 轮设计上不派 external）；存储层已测 | `store/claim.go:41-44` 只派 none、branch；ended → blocked + 决策卡由 `TestBlockedExternalNeedsAClearedEnd` 证 |
| T22 ② 第二个 agentd | **等 Owner**（06 上动手） | 脚本 `owner-t22-06.sh second-agentd`，见下 |
| 合盖 20 分钟 | **等 Owner**（06 上动手） | 06 没有盖子：冻结 STG agentd 整个 unit 20 分钟，`owner-t22-06.sh lid` |

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

### T22 ④ 推分支与过期同时发生

新测试 `agentd/pushlapse_test.go` `TestPushAsTheLeaseLapses`（真库、真 git 远端、真 agentd 的 Run）：远端 pre-receive 钩子拦住推送；拦住期间租约越过宽限（夹具：超级用户以 replica 角色把 `lease_expires_at` 往回拨，再跑租约循环，尝试 lost、任务回 ready），另一台主机 h2 重领到第 2 次尝试；放行。结果：提交只落在 `agent/<task>/a1`，远端只有 main 和 a1，a2 分支不存在、main 不动；平台拒收 persist（fenced），agentd 保全该提交（`attempt_salvaged` 1 条，a1 有 `persisted_at`、仍是 lost），a1 没有 persisted / submitted 事件；推送落地前后任务的状态、version、状态事件数和 a2 的状态都不变。阳性对照：把尝试分支一律命名成 a1，测试变红（晚到的推送落在新尝试的分支上）。

### T34 ④ 上传中途重启 agentd

新测试 `agentd/handover_restart_test.go` `TestRestartDuringTheHandOver`：agentd 以独立进程跑（测试二进制带 `AGENTD_TEST_DAEMON`，`restartdaemon_test.go`），代理在选定的请求上停住后由测试 `SIGKILL` 它，再在同一登记和工作区上起新的 agentd 接管。五个杀点：报告在路上（平台没收到）；报告只发了一半就断开（关闭写端后等平台回 4xx 才杀，证明平台读到了这半截）；平台收下报告、回复没回来；分支已推、persist 在路上；平台记下 persist、回复没回来。每个杀点先核对死时平台和远端的样子（报告几份、persisted 几条、分支在不在），接管后：每个产物一条 artifact_put、report 和 log_tail 各一份、`attempt_persisted` 1 条、`attempt_submitted` 1 条、分支上一个提交且等于平台记的那个、登记清空，`StartVerification` 把任务推进 verifying。阳性对照：接管时无视登记里的「已准备」重做提交，第五个杀点变红（persist 冲突，任务停在 running）。
没覆盖的窄窗口：本地 git 提交已成、登记还没写「已准备」时被杀（代理看不到这一刻）；按代码，重启后会软重置到 base 重新提交，此前没推过，所以不会有第二个提交上远端。
STG 上不用跑：手动重启 agentd 落不进上传那几毫秒；平台侧幂等和 agentd 的登记接管都在上面这条测试里用真进程、真库测了。

### T01 external

不用跑。第 2 轮不派 external 类（`store/claim.go:41-44`，`dispatched = none, branch`；只有测试导出的 `ClaimExternalFor` 能领），STG 上种这种任务要直写库。平台侧的行为在主线测试里：`store/kernel_test.go` `TestEnded`（external 任务的尝试 `ended{daemon_restart}` → 任务 blocked；同一尝试重复报得到同一结果、别的主机报被拒）、`TestLeaseSweep`（external 的尝试 lost → blocked），`store/blockedcard_test.go` `TestBlockedExternalNeedsAClearedEnd`（进程组已清的 → 决策卡写明「no host takes external work yet」；没清的不出卡）。agentd 接管与任务类别无关，branch 那一半 10-15 在 STG 上真跑过（`t_01M50S5AWEKN85XFCFQ98RWQPJ`）。

### 发现

- **F-T33**：没有 gate 验收记录的写入方（见 T33）。
- **F-probe**：STG 的 run_probe_pod 不能带平台自己的库身份（env_from 不许 `bifrost-platform-stg`）；设计里「直写用 run_probe_pod」这条路在现行策略下走不通。是否要开，属于策略（RBAC 级）决定，不在这一轮。

### 要 Owner 跑的（统筹线程转）

① **T35 错 namespace**（建议跑：一次口令，约 1 分钟；不跑不挡 Gate A，测试已证）——在 App 的终端面板里跑（要输钥匙口令或 Touch ID）：

    bash ~/agent-work/gate-a-rest/owner-t35-namespace.sh

最后一行 `T35 (release-policy namespace) PASS` 就是过；输出同时存在 `~/agent-work/gate-a-rest/owner-t35.out`，统筹读它。

② **T22 ② 第二个 agentd**（约 21 分钟）——前提：统筹先给 STG 的 agentd（主机 agent-06-stg）派一件执行者会 sleep 30 分钟的任务，带 `needs_owner`；脚本发现 agentd 底下没有执行者就停。只碰 STG 的 agentd，不碰 PROD 的。在终端面板里跑（一次节点钥匙口令）：

    bash ~/agent-work/gate-a-rest/owner-t22-06.sh second-agentd

它 SIGSTOP agentd（执行者照跑）→ 等 18 分钟（租约 2 + 宽限 15 + 1）→ 以同一用户、同样的环境和隔离起第二个 agentd（最多 30 秒，应报「another agentd runs on this host」立刻退出）→ SIGCONT → 看 90 秒日志。输出在 `owner-t22-second-agentd.out`。过的标准（统筹查 STG 事件）：第二个 agentd 退出、没有以 agent-06-stg 领到活；第一个醒来后被 409 挡住、30 秒内清掉进程组、`attempt_ended{lease_lost, group_cleared: true}`，结局 `attempt_salvaged`（有结果时）、任务按 effect_class 处理。

③ **合盖 20 分钟**（约 23 分钟）——前提同②。06 没有盖子，用 cgroup 冻结 STG agentd 的整个 unit（agentd 和它起的执行者一起停，PROD 的不动）：

    bash ~/agent-work/gate-a-rest/owner-t22-06.sh lid

输出在 `owner-t22-lid.out`。过的标准：到期约 10 秒后 `attempt_stale`、宽限过后 `attempt_lost`；解冻后 agentd 被 409 挡住、30 秒内清掉进程组、`attempt_ended{lease_lost}`。与真合盖的差别：真睡眠时 CLOCK_MONOTONIC 不走，agentd 醒来后会以为租约还在、要等一次心跳被拒才知道；平台按数据库时间判，这一点不影响隔离，但冻结测不到这个时钟差。真睡眠（`rtcwake`）会连 PROD 的 agentd 一起停，不建议。

先跑 `bash ~/agent-work/gate-a-rest/owner-t22-06.sh check`（只读）看 STG agentd 底下有没有执行者。
