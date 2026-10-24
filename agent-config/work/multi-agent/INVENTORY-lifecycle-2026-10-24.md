# 第 4 轮 4.6 一次性盘点（只读，第 2 稿）

> 实测时间：Gitea / GitHub 引用快照 2026-10-24T05:24:40Z（`git ls-remote`），本机检查 2026-10-24 00:25–00:35 CDT，集群 00:3x。**什么都没删。**
> 第 2 稿按复核 534 改了判据（见 `CUT-lifecycle-2026-10-24.md` §2）：
> - 「有副本」只按**对象可达性**判：确切提交能从 Gitea **现在存在**的某个引用（分支头或标签）走到，即 `git rev-list <提交…> --not <Gitea 全部引用>` 为 0；Change-Id、标题、patch-id 只作线索，不放行删除；
> - worktree 和本地分支连同它们的 **reflog** 一起算；
> - `git status --porcelain --ignored` 有任何未跟踪或被忽略的内容就不算干净（还没有登记过的缓存根）；有未提交的删除也算改动；
> - 结束要有正面证据（登记的会话已结束、复核的 `run.done`、运行时任务的终态）；「24 小时没写」「没有进程」只算旁证。
> 所有 git 调用都带 `GIT_OPTIONAL_LOCKS=0`、`GIT_NO_LAZY_FETCH=1`；`git fetch` 不带 `--prune`。单位：GiB = 2^30 字节（`df -g`、`du -k`、Go 的 `15 << 30` 都是这个单位）。
> 原始数据和脚本在同目录 `INVENTORY-lifecycle-2026-10-24.data/`（路径已把家目录换成 `~`、工作区换成 `<ws>`）。（原始数据与脚本不进公开仓库：其中有本机临时目录和一个不在公开清单里的仓库的 SHA，复核 539 C4；留在统筹机器的 `~/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.data/`，提交 db3d14d9。）

## 1. 三类计数

| 类 | 总数 | 可自动清 | 只报不删 | 要 Owner 定 | 不计（在用 / 主 checkout / 别人的） |
|---|---|---|---|---|---|
| Gitea `agent/**` | 27 | 1（agentd 规则内，分支头在 main） | 7（规则内到期、提交只在本分支上的 6 条，加上 M-27 Q07 分不清哪次被收下的另一条） | 19（D-L5） | — |
| Gitea 人的分支 | 53 | — | — | 29（分支头是 main 的祖先，D-L1）+ 24（有提交不在 main，D-L2） | — |
| Gitea `land/**`（4.1） | 0 | — | — | — | 归 4.1 的落地循环 |
| GitHub 冻结分支 | 157 | — | — | 157（D-L3；119 个分支头已在 Gitea 引用上，38 个不在，要先保全） | — |
| 本地分支 | 489 | 132 | 111 | — | 246（检出在 worktree 里，跟 worktree 走） |
| 本机 worktree | 334（另 11 个主 checkout） | 0 | 252 | 76（D-L8：内容全在 Gitea，缺结束证据） | 5 在用 + 1 本线 |
| 复核目录里的缓存子目录 | 33（16.32 GiB） | 20（10.05 GiB） | 13（6.27 GiB） | — | — |
| 复核记录（缓存以外） | 495 个目录，2.11 GiB | — | — | 全部（D-L4） | — |
| 共享 `.cache` | 43 项 | 3 个缓存根（18.96 GiB），只按上限修剪 | 40 项（1.29 GiB），含引号目录 | — | — |
| 分支备份 bundle | 30 个 | — | 30（168 个引用的提交已不在 Gitea 上，这些包是最后的副本） | 归档位置随 D-L4 | — |
| `cicd` PipelineRun | 306 | 现有 7 天 CronJob 照跑 | — | 换成 Owner 10-10 的规则：只差批 apply（D-L7） | — |
| `cicd` 单独 TaskRun | 475（423 个超过 2 天，122 个超过 7 天） | — | — | D-L7 同一张单 | — |
| `cicd` PVC | 285 | 随 PipelineRun 级联 | — | 4 个属于 06-19 单独 TaskRun 的随 D-L7 | 3 个数据卷 `gitea-backup`、`gitea-data`、`registry-data` |

和第 1 稿相比：worktree 的「可自动清」295 → 0，本地分支 437 → 132，人的远端分支「已合入」41 → 29（分支头是 main 祖先的才算），GitHub「已在 main」130 → 119，
`agent/**` 规则内到期的 7 条里只有 1 条的对象在 main 上，复核缓存「可自动清」16.3 → 10.05 GiB。

## 2. 复核 534 列出的反例，逐条复查

| 反例 | 第 2 稿实测 | 判定 |
|---|---|---|
| `~/agent-work/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-platform` — A1：detached HEAD `8d5135fdf9d3` 不在任何引用上；main 上同 Change-Id 的是拆分后的 `710074d70654` | HEAD 独有 1；被忽略 5 | 只报不删 |
| `~/agent-work/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-platform` — A2：HEAD 在 main，reflog 有独有提交 | reflog 独有 2；被忽略 5 | 只报不删 |
| `~/agent-work/w31-25-release/bifrost-platform` — A2：旧提交 `95ba98d4` 只在这个 worktree 的 HEAD reflog 里 | reflog 独有 3；被忽略 4 | 只报不删 |
| `~/agent-work/td384/bifrost-platform` — A2：reflog 独有 19（复核数） | reflog 独有 19；被忽略 4 | 只报不删 |
| `~/agent-work/blocked-card/bifrost-platform` — A2：reflog 独有 11（复核数） | reflog 独有 11；被忽略 3 | 只报不删 |
| `$TMPDIR/push-main.XrTZfq/bifrost-trade-infra` — A5：12 处 tracked 删除 | 未提交改动 12（删除 12） | 只报不删 |
| `~/agent-work/td-337/bifrost-platform` — 手写的 `quiet.go` 与 6 处改动 | 未提交改动 6（删除 0）；未跟踪 7 | 只报不删 |
| `~/agent-work/chief-exam-s5/bifrost-platform` — 手写的未跟踪测试 | reflog 独有 3；未跟踪 1 | 只报不删 |
| `~/agent-work/gate-a-t33/bifrost-platform` — 手写的未跟踪目录 | 未跟踪 1 | 只报不删 |
| `~/agent-work/td-310/bifrost-platform` — 4 条 `+`，由 `origin/w31/td-310-anchor` 包含 | 被忽略 4 | 只报不删 |
| `<ws>/.worktrees/w32-platform` — 两项未跟踪 node_modules | 未跟踪 2；被忽略 2 | 只报不删 |
| `~/agent-work/codex-ops-ui/bifrost-platform` — 复核时有 cwd 匹配 | reflog 独有 2；被忽略 3；有进程在用 | 暂留（在用） |
| infra 本地分支 `td-lane-aa-2026-10-04` — A1：第 1 稿靠同标题判已合入 | 分支头独有 4，连 reflog 8 | 只报不删 |
| 第 1 稿 110 条「可清但原快照有本地独有提交」的本地分支 — A1 | 第 2 稿只按可达性：本地分支可自动清 132，只报 111（分支头独有 87、只有 reflog 独有 24） | 见 §5 |
| GitHub 157 个分支头 — D-L3：38 个确切的头不被 Gitea 引用覆盖 | 重算：38 个不被覆盖（同名分支在 Gitea 上的 0 个） | D-L3 先保全这 38 个 |
| `agent/**` 规则内到期的 7 条 — A3：各有 `git cherry +`、只由自己的分支包含 | 重算：7 条里 6 条有只在本分支上的提交，`t_01M50FZ…/a2` 的头在 main 上 | 6 条只报，1 条可自动清（agentd） |
| STG M-27 Q07 两次尝试哪次被收下 — A3 | 没查到（要读 STG 的 `verification`），两条都只报 | 只报不删 |
| 共享 `.cache` 里的 `api-new.go`、`pools-new.go`、`cut25.md` — A4 | 都在；`.cache` 里 40 项不是已知工具的缓存布局 | 只报不删 |
| 引号目录 `.cache/go-build GOMODCACHE=` — A4 | 是一串单子目录 `Users/…/go-mod AGENTRT_TEST_PG='…' AGENTRT_TEST_REQUIRED=1`，末端才是 Go 构建缓存（README、trim.txt、两位十六进制目录）；第 2 稿的类型检查不认这种形状 | 只报不删（S1 对它做专门校验） |
| `codex-review-506/tmp` — A4 | 里面是 `.tmp*`、`tsx-501`、`xcrun_db`，不是已知工具的布局 | 只报不删 |
| 分支备份覆盖 / 90 天 — A7 | 4 个日期 30 个包都能 `git bundle verify`；**其中引用的提交有 168 个已不在 Gitea 上**（以前按 Change-Id / 标题判已合入删掉的分支），这些包就是最后的副本 | 只报不删；R12 不能按 90 天删 |
| `bifrost-finance` 独立克隆 | status 空、没有本地独有提交、stash 空；它的被忽略数据没审 | 不按 R10 整个删 |

## 3. Gitea 分支

### 3.1 `agent/**`（27 条）

| 仓库 | 分支 | 运行时 / mission | 任务状态 | 分支头在 main | 只在本分支上的提交 | 判定 | 依据 |
|---|---|---|---|---|---|---|---|
| platform | `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a1` | STG M-1 | cancelled 10-20 21:17Z | N | 1 | 只报不删 | 规则内已到期，但提交只在这条分支上；S5 给 agentd 加「删前归档」后才删 |
| platform | `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a2` | STG M-1 | cancelled 10-20 21:17Z | Y | 0 | 可自动清 | agentd 规则内（任务取消超过 24 小时），分支头在 main 上 |
| platform | `agent/t_01M50M1CZSDN8PNHRH8C2241RS/a1` | STG M-2 | accepted 10-15（UniFi 测试，演练） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M511RV9S41AEW9CDA76024Q3/a1` | PROD M-1 | accepted 10-16（一段注释） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M51EHZ92V5F2PRB7JCZVHTQ3/a1` | PROD M-2 | accepted 10-16（一段注释） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M55AN78GPF9V6NFZFS4KJP8N/a1` | PROD M-3 | accepted 10-17（safego 测试，2.3 演练） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M55AN78M1MX9NF9Q958T96Z3/a1` | PROD M-3 | accepted 10-17（statefile 测试，2.3 演练） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M56J5QPAAQQP53KV4MQYCW5Q/a1` | PROD M-4 | accepted 10-18（一段注释） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M57YSQN6B43ZFNESD9VQ2HA9/a1` | STG M-13 | cancelled 10-20 23:22Z | N | 1 | 只报不删 | 规则内已到期，但提交只在这条分支上；S5 给 agentd 加「删前归档」后才删 |
| platform | `agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a2` | STG M-16 | accepted 10-19（T26 返工演练） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5B37AYBAHQTM6RMQZZHE3AT/a1` | STG M-23 | accepted 10-19（隔离版 agentd 走查） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5B6KKPMM15HZB4BC0ZWVJ5R/a1` | STG M-24 | accepted 10-19（TD-382 走查） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSBEZ7J3BQM0EV7SG3NB2N/a1` | STG M-26 | accepted 10-20（Gate B 实测） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSPFV3S9ET52X3JT76HJFS/a1` | STG M-27 | accepted 10-20（基准题 Q04） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSPFV8JBH908TR6M58S6Q9/a1` | STG M-27 | accepted 10-20（基准题 Q06） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a1` | STG M-27 | accepted 10-20（基准题 Q07）；两次尝试，哪次被收下没查 | N | 1 | 只报不删 | 两次尝试各有独有提交；被取代的那条规则内到期，同样等 S5 的归档 |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a2` | STG M-27 | accepted 10-20（基准题 Q07）；两次尝试，哪次被收下没查 | N | 1 | 只报不删 | 两次尝试各有独有提交；被取代的那条规则内到期，同样等 S5 的归档 |
| platform | `agent/t_01M5BSPFVDY1N34EGQ5THXYMMD/a1` | STG M-27 | accepted 10-20（基准题 Q18） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSTGPP9FC3PCF4NF5PM7GD/a1` | PROD M-13 | accepted 10-20（Gate B 实测） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BSTYPZ54K9NV1F1S8HSVYZ/a1` | PROD M-14 | cancelled 10-20 19:03Z | N | 1 | 只报不删 | 规则内已到期，但提交只在这条分支上；S5 给 agentd 加「删前归档」后才删 |
| platform | `agent/t_01M5BSTYPZ54K9NV1F1S8HSVYZ/a2` | PROD M-14 | cancelled 10-20 19:03Z | N | 1 | 只报不删 | 规则内已到期，但提交只在这条分支上；S5 给 agentd 加「删前归档」后才删 |
| platform | `agent/t_01M5BV3W403F0SYH6HF8RAFNJ0/a1` | PROD M-15 | accepted 10-20（基准题 Q04） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BV3W43ETJPVBT55T2XYW30/a1` | PROD M-15 | accepted 10-20（基准题 Q06） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BV3W45NDSBHBTEFY4RMT97/a1` | PROD M-15 | accepted 10-20（基准题 Q07） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| platform | `agent/t_01M5BV3W48B5HGHZB5JJKHE81G/a1` | PROD M-15 | accepted 10-20（基准题 Q18） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |
| trade-infra | `agent/t_01M5B8BF2B5K3QPRTC1GMBBJQ6/a1` | PROD M-9 | accepted 10-20；收下的 a2 已作为 d989dde 进 main、分支已删；a1 是被叫停的上一次尝试 | N | 1 | 只报不删 | 规则内已到期，但提交只在这条分支上；S5 给 agentd 加「删前归档」后才删 |
| trade-infra | `agent/t_01M5G4W33CRXXVX4C7GJTCJ3VR/a1` | STG M-103 | accepted 10-21（T24/T34 演练） | N | 1 | 要 Owner 定 | D-L5：收下没进 main（先归档，再按 mission 定 no_merge） |

规则内到期却没删的原因：`store/prune.go:204-205` 要求运行时记下的尝试、ref、提交和 Gitea 上的分支完全对得上，否则静默保留——被叫停的尝试多半没记下推送的提交。没读库核实，归 S5。
平台的检查点补丁（`agentd/checkpoint.go`，运行中每 5 分钟、≤1 MiB 的 `git diff`）不是最终提交对象，不能当归档。

### 3.2 人的分支（53 条）

**分支头是 Gitea main 的祖先（29 条，D-L1）**：
- platform（17）：`codex/ops-ui-v2`、`fix/checklist-prober-rollout-gap`、`w31/25-slice5`、`w31/agentd-drop-push-base`、`w31/bi1-1-data-r2`、`w31/bi1-1b-card-text-guard`、`w31/bi1-2-api`、`w31/ci-fix-paints`、`w31/ci-follow-infra-prod`、`w31/owner-signoff`、`w31/plan-artifact-path`、`w31/plan-follows-newest-round`、`w31/plan-signoff-usable`、`w31/r3-35-online`、`w31/t32-seat-route`、`w31/td-420-421`、`w31/td-425-not-started-r2`
- platform-plugin（1）：`cursor/w33d-plugin`
- platform-plugin-flex-query（2）：`cursor/k-flex`、`w31/w56-flex-freeze`
- platform-plugin-market-data（1）：`cursor/w-market-data`
- trade-infra（5）：`w31/gate-a-freeze-drill`、`w31/gate-a-t33-done`、`w31/gate-a-t33-pass`、`w31/release-speedup`、`w31/td-411-pipeline`
- trade-worker（3）：`cursor/t2-worker`、`cursor/t3-worker`、`cursor/x-worker`

**有提交不在 main 上（24 条，D-L2）**——第 1 稿把其中 12 条按 Change-Id / 标题算作「已合入」：

| 仓库 | 分支 | 分支头 | 只在本分支上的提交（不在 Gitea 其他引用上） |
|---|---|---|---|
| platform | `w31/25-review-488` | 2026-10-21 | 3 |
| platform | `w31/25-slice5-gaps` | 2026-10-21 | 7 |
| platform | `w31/bi1-1-data` | 2026-10-23 | 4 |
| platform | `w31/td-310-anchor` | 2026-10-11 | 4 |
| platform | `w31/td-411-applied` | 2026-10-21 | 1 |
| platform | `w31/td-425-not-started` | 2026-10-23 | 1 |
| platform | `w31/w55-ddl-allowlist` | 2026-10-10 | 3 |
| trade-infra | `cursor/m2-infra` | 2026-10-08 | 1 |
| trade-infra | `w31/25-slice5-t24` | 2026-10-21 | 0 |
| trade-infra | `w31/gate-a-closeout` | 2026-10-20 | 1 |
| trade-infra | `w31/gate-a-freeze-drill-fix` | 2026-10-21 | 1 |
| trade-infra | `w31/gate-a-t32` | 2026-10-21 | 4 |
| trade-infra | `w31/gate-a-t32-t36` | 2026-10-21 | 1 |
| trade-infra | `w31/gitea-primary-leftovers` | 2026-10-23 | 4 |
| trade-infra | `w31/owner-signoff-docs` | 2026-10-21 | 3 |
| trade-infra | `w31/td-310-anchor` | 2026-10-11 | 4 |
| trade-infra | `w31/td-312` | 2026-10-11 | 1 |
| trade-infra | `w31/td-411-dryrun` | 2026-10-22 | 10 |
| trade-infra | `w31/w56-gates` | 2026-10-10 | 3 |
| trade-infra | `w31/w56-matrix` | 2026-10-11 | 13 |
| trade-infra | `w31/w56-slice-a` | 2026-10-11 | 2 |
| trade-infra | `w31/w66-lane` | 2026-10-11 | 3 |
| trade-infra | `w31/w66-lane-v2` | 2026-10-11 | 7 |
| trade-infra | `w31/w66-shadow` | 2026-10-12 | 2 |

`commits_only_here` 为 0 的那条（`w31/25-slice5-t24`）被另一条人的分支包含；两条同时删时它也没有副本。

### 3.3 GitHub（157 条，D-L3）

| 仓库 | 总数 | 分支头已在 Gitea 引用上 | 不在（要先保全） |
|---|---|---|---|
| platform | 75 | 64 | 11 |
| platform-plugin | 1 | 1 | 0 |
| platform-plugin-flex-query | 2 | 2 | 0 |
| platform-plugin-market-data | 1 | 1 | 0 |
| research | 2 | 2 | 0 |
| trade-api | 2 | 2 | 0 |
| trade-core | 4 | 3 | 1 |
| trade-frontend | 5 | 3 | 2 |
| trade-infra | 62 | 38 | 24 |
| trade-worker | 3 | 3 | 0 |

不被覆盖的 38 个：`platform:cursor/b-platform`、`platform:cursor/d1-platform`、`platform:cursor/n-platform`、`platform:cursor/p2-platform`、`platform:cursor/rp-platform`、`platform:w31/td-306-307`、`platform:w31/td-306-b`、`platform:w31/td-306-c`、`platform:w31/td-312`、`platform:w31/td-313-gate-proof`、`platform:w31/w62-slice4`、`trade-core:fix/w4-snapshot-stale-accounts`、`trade-frontend:cursor/t3-frontend`、`trade-frontend:fix/data-gap-wording`、`trade-infra:cursor/a1-infra`、`trade-infra:cursor/a2-infra`、`trade-infra:cursor/a3-infra`、`trade-infra:cursor/a5-infra`、`trade-infra:cursor/a6-infra`、`trade-infra:cursor/a6r-infra`、`trade-infra:cursor/a7-infra`、`trade-infra:cursor/b2-infra`、`trade-infra:cursor/b3-infra`、`trade-infra:cursor/b4-infra`、`trade-infra:cursor/d1-infra`、`trade-infra:cursor/e1-infra`、`trade-infra:cursor/m-infra`、`trade-infra:cursor/phase3-lane-c-report`、`trade-infra:cursor/rp-infra`、`trade-infra:cursor/t2-infra`、`trade-infra:cursor/w32-infra`、`trade-infra:cursor/w33-infra`、`trade-infra:cursor/w33b-infra`、`trade-infra:cursor/w33c-infra`、`trade-infra:cursor/w33d-infra`、`trade-infra:cursor/w33r-infra`、`trade-infra:w31/prod-api-recreate`、`trade-infra:w31/w61-notify-resolve`

## 4. 本机 worktree

| 仓库 | worktree | 可自动清 | 只报不删 | 要 Owner 定（D-L8） | 在用 / 本线 |
|---|---|---|---|---|---|
| platform | 178 | 0 | 139 | 38 | 1 |
| platform-plugin-flex-query | 1 | 0 | 0 | 1 | 0 |
| platform-plugin-market-data | 3 | 0 | 3 | 0 | 0 |
| research | 5 | 0 | 3 | 0 | 2 |
| trade-frontend | 5 | 0 | 4 | 0 | 1 |
| trade-infra | 117 | 0 | 79 | 36 | 2 |
| ui | 25 | 0 | 24 | 1 | 0 |

只报不删的 252 个，按第一道拦住它的条件：只有被忽略的内容（node_modules、dist、.venv 之类，没有登记为缓存） 93；只有 reflog 里的提交不在 Gitea 引用上（打包验证后可转） 73；HEAD 有提交不在 Gitea 引用上 54；有未跟踪内容 28；未提交改动（含删除） 4

### 4.1 D-L8 清单（76 个：HEAD 与 reflog 全在 Gitea 引用上、没有任何未跟踪或被忽略的内容、没有进程在用，但没有会话已结束的正面证据）

全深度遍历（跳过 `.git`、`node_modules`）的最新文件时间：3 个在 24 小时内、9 个在 72 小时内有改动——这几个多半还在用。

| 仓库 | 路径 | 分支 | 最新文件 |
|---|---|---|---|
| platform | `~/agent-work/r4-planimport-tool` | `(detached)` | 2026-10-23 23:45 |
| trade-infra | `~/agent-work/r4-plan` | `w31/r4-plan` | 2026-10-23 23:45 |
| platform | `~/agent-work/bi1-1` | `w31/bi1-1-data` | 2026-10-23 11:14 |
| platform | `~/agent-work/bi1-1b` | `w31/bi1-1b-card-text-guard` | 2026-10-23 00:49 |
| trade-infra | `~/agent-work/w31-23-slice5/bifrost-trade-infra` | `w31/23-work-pointer` | 2026-10-21 21:37 |
| platform | `~/agent-work/gate-a-t32/bifrost-platform` | `w31/t32-seat-route` | 2026-10-21 20:43 |
| trade-infra | `~/agent-work/w31-25-slice5-infra` | `w31/owner-signoff-docs` | 2026-10-21 17:05 |
| trade-infra | `~/agent-work/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-trade-infra` | `(detached)` | 2026-10-21 14:00 |
| trade-infra | `~/agent-work/exam-fp-4f336302` | `(detached)` | 2026-10-21 13:42 |
| platform | `~/agent-work/gate-a-flake/bifrost-platform` | `w31/stateevents-liveness` | 2026-10-20 18:51 |
| trade-infra | `~/agent-work/exam-doc/bifrost-trade-infra` | `(detached)` | 2026-10-20 18:24 |
| platform | `~/agent-work/td392/bifrost-platform` | `(detached)` | 2026-10-20 15:44 |
| platform | `~/agent-work/prune-1d/bifrost-platform` | `(detached)` | 2026-10-20 14:46 |
| platform | `~/agent-work/td378-ratchet/bifrost-platform` | `(detached)` | 2026-10-20 12:56 |
| trade-infra | `~/agent-work/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-trade-infra` | `(detached)` | 2026-10-20 12:28 |
| platform | `~/agent-work/plan-import/platform` | `(detached)` | 2026-10-19 22:50 |
| platform | `~/agent-work/night-recorder/bifrost-platform` | `w31/night-recorder` | 2026-10-19 18:45 |
| platform | `~/agent-work/w31-report-mask` | `w31/report-mask` | 2026-10-19 17:54 |
| platform | `~/agent-work/w31-confine-codex` | `w31/confine-codex` | 2026-10-19 11:40 |
| platform | `~/agent-work/w31-24-chief` | `w31/24-chief` | 2026-10-18 14:33 |
| platform | `~/agent-work/w31-24-pools` | `w31/24-pools` | 2026-10-18 13:43 |
| platform | `~/agent-work/cos-slice23/bifrost-platform` | `w31/cos-plan` | 2026-10-15 22:03 |
| platform | `~/agent-work/cos-slice1/bifrost-platform` | `w31/cos-claude-executor` | 2026-10-15 20:42 |
| platform | `~/agent-work/agentrt-22r/bifrost-platform` | `w31/agentrt-22-lineage-agents` | 2026-10-15 16:24 |
| platform | `~/agent-work/agentrt-22o/bifrost-platform` | `w31/agentrt-22-cursor-memory` | 2026-10-15 14:34 |
| platform | `~/agent-work/agentrt-22m` | `w31/mcp-stg-key` | 2026-10-15 13:34 |
| trade-infra | `~/agent-work/agentrt-22/bifrost-trade-infra` | `(detached)` | 2026-10-14 20:11 |
| platform | `~/agent-work/agentrt-22g/bifrost-platform` | `w31/agentrt-22-agentd` | 2026-10-14 18:01 |
| platform | `~/agent-work/agentrt-22h/bifrost-platform` | `w31/agentrt-22-sources` | 2026-10-14 17:31 |
| platform | `~/agent-work/agentrt-22j/bifrost-platform` | `w31/agentrt-22-adopt` | 2026-10-14 17:15 |
| platform | `~/agent-work/agentrt-21-merge/bifrost-platform` | `(detached)` | 2026-10-14 10:09 |
| trade-infra | `~/agent-work/td-339/bifrost-trade-infra` | `(detached)` | 2026-10-13 22:51 |
| platform | `~/agent-work/td-329/merge` | `(detached)` | 2026-10-13 12:56 |
| platform | `~/agent-work/guard-6/merge` | `(detached)` | 2026-10-13 03:37 |
| platform | `~/agent-work/td-325/merge` | `(detached)` | 2026-10-13 00:48 |
| trade-infra | `~/agent-work/td-325/bifrost-trade-infra` | `(detached)` | 2026-10-12 23:16 |
| platform | `~/agent-work/guard-5/merge/bifrost-platform` | `(detached)` | 2026-10-12 21:08 |
| trade-infra | `~/agent-work/guard-5/merge/bifrost-trade-infra` | `(detached)` | 2026-10-12 21:08 |
| platform | `~/agent-work/guard-5/bifrost-platform` | `w31/guard-5-pin` | 2026-10-12 20:45 |
| trade-infra | `~/agent-work/guard-5/bifrost-trade-infra` | `(detached)` | 2026-10-12 19:41 |
| trade-infra | `~/agent-work/guard-1a/bifrost-trade-infra` | `w31/td-317-client` | 2026-10-12 15:14 |
| trade-infra | `~/agent-work/td-316-317/bifrost-trade-infra` | `w31/td-316-tests` | 2026-10-12 13:02 |
| platform | `~/agent-work/td-318/bifrost-platform` | `w31/td-318` | 2026-10-12 07:20 |
| platform | `~/agent-work/td-310-s1/bifrost-platform` | `w31/td-310-s1` | 2026-10-12 06:49 |
| platform | `~/agent-work/lessons-inventory/bifrost-platform` | `(detached)` | 2026-10-11 21:05 |
| trade-infra | `~/agent-work/lessons-inventory/bifrost-trade-infra` | `(detached)` | 2026-10-11 21:05 |
| trade-infra | `~/agent-work/td-310-design/bifrost-trade-infra` | `w31/td-310-design-r3` | 2026-10-11 20:26 |
| trade-infra | `~/agent-work/td-312/bifrost-trade-infra` | `w31/td-312` | 2026-10-11 15:26 |
| ui | `~/agent-work/w66-recorder-s1/bifrost-ui` | `(detached)` | 2026-10-11 14:35 |
| trade-infra | `~/agent-work/w62-slice4/bifrost-trade-infra` | `(detached)` | 2026-10-11 11:43 |
| trade-infra | `~/agent-work/td-306-307/bifrost-trade-infra` | `(detached)` | 2026-10-11 08:24 |
| trade-infra | `~/agent-work/w65-integration/bifrost-trade-infra` | `(detached)` | 2026-10-11 08:17 |
| platform-plugin-flex-query | `~/agent-work/w56-flex-freeze/bifrost-platform-plugin-flex-query` | `w31/w56-flex-freeze` | 2026-10-11 08:17 |
| trade-infra | `~/agent-work/w65-1b/bifrost-trade-infra` | `(detached)` | 2026-10-11 05:10 |
| trade-infra | `~/agent-work/w65-1a/bifrost-trade-infra` | `w31/w65-1a-guard` | 2026-10-11 03:55 |
| trade-infra | `~/agent-work/w65-slice0/bifrost-trade-infra` | `(detached)` | 2026-10-11 03:00 |
| trade-infra | `~/agent-work/w62-slice3/bifrost-trade-infra` | `(detached)` | 2026-10-11 01:33 |
| trade-infra | `~/agent-work/w62-slice2/bifrost-trade-infra` | `(detached)` | 2026-10-11 00:14 |
| platform | `~/agent-work/w56-gates/bifrost-platform` | `(detached)` | 2026-10-10 23:27 |
| trade-infra | `~/agent-work/w62-progress/bifrost-trade-infra` | `w31/w62-progress` | 2026-10-10 23:09 |
| trade-infra | `~/agent-work/w61-approval-page/bifrost-trade-infra` | `(detached)` | 2026-10-10 20:05 |
| trade-infra | `~/agent-work/ci-green/bifrost-trade-infra` | `(detached)` | 2026-10-10 14:55 |
| trade-infra | `~/agent-work/s0-0-all/bifrost-trade-infra` | `w31/s0-0-all` | 2026-10-10 13:53 |
| trade-infra | `~/agent-work/w54-fix/bifrost-trade-infra` | `w31/w54-fix` | 2026-10-10 13:08 |
| platform | `~/agent-work/w55-ddl/bifrost-platform` | `w31/w55-ddl-allowlist` | 2026-10-10 12:06 |
| trade-infra | `~/agent-work/s0-0-int/bifrost-trade-infra` | `w31/s0-0-int` | 2026-10-10 11:13 |
| platform | `~/agent-work/w48-s0-0a` | `w31/w48-s0-0a` | 2026-10-10 09:41 |
| platform | `~/agent-work/w51-s0-0d` | `w31/w51-s0-0d` | 2026-10-10 09:44 |
| platform | `~/agent-work/w54-s0-21-platform` | `w31/w54-s0-21` | 2026-10-10 09:53 |
| trade-infra | `~/agent-work/w51-s0-0d-infra` | `w31/w51-s0-0d` | 2026-10-10 09:44 |
| platform | `~/agent-work/w49-s0-0b` | `w31/w49-s0-0b` | 2026-10-10 03:00 |
| platform | `~/agent-work/w31-console-int` | `(detached)` | 2026-10-10 02:37 |
| trade-infra | `~/agent-work/w38-s0-14` | `cursor/w38-s0-14` | 2026-10-10 02:19 |
| trade-infra | `<ws>/.worktrees/w33c-report` | `(detached)` | 2026-10-09 11:21 |
| trade-infra | `<ws>/.worktrees/w32-report` | `cursor/w32-report` | 2026-10-08 17:32 |
| trade-infra | `<ws>/bifrost-trade-infra-a6r-report` | `cursor/a6r-report` | 2026-10-08 16:58 |

### 4.2 在用（5 个，有进程打开着其中的文件或以它为 cwd）

- `~/agent-work/codex-ops-ui/bifrost-platform`（`codex/ops-ui-v2`）：reflog 独有 2；被忽略 3；有进程在用
- `~/agent-work/r4-b4`（`w31/r4-w68-b4`）：HEAD 独有 1；有进程在用
- `~/agent-work/rules-symbols`（`codex/rules-symbols`）：reflog 独有 1；未跟踪 1；被忽略 3；有进程在用
- `~/agent-work/data-integrity-main-research`（`codex/data-integrity-main`）：未跟踪 1；被忽略 54；有进程在用
- `~/agent-work/td-172-142-research`（`codex/td-304`）：HEAD 独有 4；被忽略 56；有进程在用

### 4.3 工作区根下的旧目录与 `.worktrees/`

| 目录 | 分支 | 判定 | 拦住它的条件 |
|---|---|---|---|
| `<ws>/.worktrees/w32-infra` | `cursor/w32-infra` | 只报不删 | HEAD 独有 1 |
| `<ws>/.worktrees/w32-platform` | `cursor/w32-platform` | 只报不删 | 未跟踪 2；被忽略 2 |
| `<ws>/.worktrees/w32-report` | `cursor/w32-report` | 要 Owner 定（D-L8） | 内容全在 Gitea 引用上（HEAD 与 reflog），但没有会话已结束的正面证据 |
| `<ws>/.worktrees/w33c-infra` | `cursor/w33c-infra` | 只报不删 | HEAD 独有 1；被忽略 1 |
| `<ws>/.worktrees/w33c-platform` | `cursor/w33c-platform` | 只报不删 | reflog 独有 3；被忽略 1 |
| `<ws>/.worktrees/w33c-report` | `(detached)` | 要 Owner 定（D-L8） | 内容全在 Gitea 引用上（HEAD 与 reflog），但没有会话已结束的正面证据 |
| `<ws>/bifrost-platform-d1` | `cursor/d1-platform` | 只报不删 | HEAD 独有 1；被忽略 1 |
| `<ws>/bifrost-platform-e1` | `cursor/e1-platform` | 只报不删 | reflog 独有 3；被忽略 1 |
| `<ws>/bifrost-platform-phase3-int` | `cursor/phase3-platform` | 只报不删 | 未跟踪 2；被忽略 4 |
| `<ws>/bifrost-platform-phase3-s1` | `cursor/phase3-s1` | 只报不删 | 未跟踪 3；被忽略 1 |
| `<ws>/bifrost-platform-phase3-s2` | `cursor/phase3-s2` | 只报不删 | reflog 独有 1；未跟踪 1；被忽略 4 |
| `<ws>/bifrost-platform-phase3-s3` | `cursor/phase3-s3` | 只报不删 | 被忽略 4 |
| `<ws>/bifrost-platform-phase3-s4` | `cursor/phase3-s4` | 只报不删 | reflog 独有 1；被忽略 4 |
| `<ws>/bifrost-platform-phase3-s5` | `cursor/phase3-s5` | 只报不删 | 被忽略 4 |
| `<ws>/bifrost-trade-infra-a6r` | `cursor/a6r-infra` | 只报不删 | HEAD 独有 1；被忽略 5 |
| `<ws>/bifrost-trade-infra-a6r-report` | `cursor/a6r-report` | 要 Owner 定（D-L8） | 内容全在 Gitea 引用上（HEAD 与 reflog），但没有会话已结束的正面证据 |
| `<ws>/bifrost-trade-infra-d1` | `cursor/d1-infra` | 只报不删 | HEAD 独有 2 |
| `<ws>/bifrost-trade-infra-e1` | `cursor/e1-infra` | 只报不删 | HEAD 独有 3；被忽略 2 |
| `<ws>/bifrost-trade-infra-phase3-report` | `cursor/phase3-lane-c-report` | 只报不删 | HEAD 独有 2 |
| `<ws>/bifrost-platform-phase3-notes` | — | 只报不删 | 不是 git，5 份 10-07 的笔记 |

完整的 334 行（每行的改动数、删除数、未跟踪、被忽略、HEAD 独有、连 reflog 独有、在用）在 `INVENTORY-lifecycle-2026-10-24.data/worktrees.tsv`。

## 5. 本地分支

| 仓库 | 总数 | 可自动清 | 只报不删 | 跟着 worktree |
|---|---|---|---|---|
| platform | 231 | 44 | 38 | 149 |
| platform-plugin | 2 | 0 | 2 | 0 |
| platform-plugin-flex-query | 10 | 5 | 4 | 1 |
| platform-plugin-market-data | 10 | 3 | 4 | 3 |
| research | 17 | 4 | 8 | 5 |
| trade-api | 7 | 4 | 3 | 0 |
| trade-core | 11 | 5 | 6 | 0 |
| trade-frontend | 12 | 4 | 3 | 5 |
| trade-infra | 181 | 57 | 41 | 83 |
| trade-worker | 6 | 5 | 1 | 0 |
| ui | 2 | 1 | 1 | 0 |

可自动清 = 没有检出在任何 worktree 里，分支头和分支 reflog 里的提交全能从 Gitea 现有引用走到；删的时候用 `git update-ref -d refs/heads/<b> <旧 sha>`。

## 6. 缓存

### 6.1 复核目录里的缓存候选（名字只用来找候选，判定看布局和 `run.done`）

| 复核 | 子目录 | 布局 | GiB | run.done | 判定 |
|---|---|---|---|---|---|
| codex-review-109 | `go-cache` | go-build | 1.31 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-335 | `go-cache` | go-build | 1.15 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-334 | `.gocache` | go-build | 1.15 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-436 | `cache` | go-build | 1.14 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-331 | `go-build` | go-build | 1.14 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-442 | `.cache` | go-build | 1.12 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-440 | `.cache` | go-build | 1.12 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-437 | `go-cache` | go-build | 1.10 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-424 | `cache` | go-build | 1.10 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-145 | `.review-cache` | - | 0.88 | Y | 只报不删：名字像缓存，内容不是已知工具的布局 |
| codex-review-144 | `.review-cache` | - | 0.87 | Y | 只报不删：名字像缓存，内容不是已知工具的布局 |
| codex-review-422 | `cache` | go-build | 0.47 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-423 | `.gocache` | go-build | 0.44 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-452 | `cache` | go-build | 0.39 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-420 | `.cache` | - | 0.38 | Y | 只报不删：名字像缓存，内容不是已知工具的布局 |
| codex-review-351 | `gocache` | go-build | 0.36 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-108 | `go-cache` | go-build | 0.27 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-152 | `review-cache` | go-build | 0.26 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-151 | `.review-cache` | go-build | 0.26 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-127 | `go-cache` | go-build | 0.21 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-124 | `go-cache` | go-build | 0.20 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-107 | `go-cache` | go-build | 0.16 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-112 | `go-cache` | go-build | 0.13 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-114 | `go-cache` | go-build | 0.13 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-113 | `go-cache` | go-build | 0.12 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-311 | `gocache` | go-build | 0.07 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-315 | `gocache` | go-build | 0.07 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-146 | `.review-cache` | - | 0.07 | Y | 只报不删：名字像缓存，内容不是已知工具的布局 |
| codex-review-312 | `gocache` | go-build | 0.07 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-310 | `gocache` | go-build | 0.07 | N | 只报不删：类型确认（go-build），但没有 run.done（没有复核已结束的证据） |
| codex-review-416 | `go-cache` | go-build | 0.07 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-418 | `go-cache` | go-build | 0.07 | Y | 可自动清：类型确认（go-build），run.done 在，没有进程打开 |
| codex-review-506 | `tmp` | - | 0.00 | N | 只报不删：名字像缓存，内容不是已知工具的布局 |

### 6.2 共享 `.cache`

- `go-build` 18.64 GiB：可自动清（只按上限修剪）（共享缓存约定的根（BRIEF 模板），类型确认 go-build）
- `go-mod` 0.25 GiB：可自动清（只按上限修剪）（共享缓存约定的根（BRIEF 模板），类型确认 go-mod）
- `npm` 0.07 GiB：可自动清（只按上限修剪）（共享缓存约定的根（BRIEF 模板），类型确认 npm）
- 其余 40 项只报：`api-new.go`、`cut25.md`、`docker-pruned-at`、`gates-pa`、`gates-pa2`、`gates-pa3`、`gates-signoff`、`gates-signoff-go`、`gates-signoff2`、`gates-su`、`gates-su2`、`go-build GOMODCACHE=`、`pa-ctl`、`paints-fix-1.log`、`paints-fix-1.rc`、`paints-fix-2.log`、`paints-fix-2.rc`、`paints-gates`、`paints-scratch`、`pools-new.go`、`push-pa.log`、`push-su.log`、`push-t24r.log`、`r488-build.log`、`r488-ctl`、`r488-gates`、`r488-gates2`、`r488-gates3`、`r488-push.log`、`r488-t1.log`、`r488-t2.log`、`review518`、`signoff-ctl`、`su-build.log`、`su-ctl`、`su-t1.log`、`tmp`、`zh-build.log`、`zh-t1.log`、`zh-t2.log`

## 7. 分支备份 `~/bifrost-backups/git-branches`

| 日期 | 仓库 | 引用数 | 其中提交已不在 Gitea 上 | `git bundle verify` |
|---|---|---|---|---|
| 2026-10-05 | platform-plugin-flex-query | 16 | 2 | Y |
| 2026-10-05 | platform-plugin-market-data | 3 | 0 | Y |
| 2026-10-05 | platform-plugin | 7 | 0 | Y |
| 2026-10-05 | platform | 19 | 4 | Y |
| 2026-10-05 | research | 49 | 8 | Y |
| 2026-10-05 | trade-api | 57 | 27 | Y |
| 2026-10-05 | trade-core | 46 | 10 | Y |
| 2026-10-05 | trade-frontend | 69 | 15 | Y |
| 2026-10-05 | trade-infra | 58 | 25 | Y |
| 2026-10-05 | trade-worker | 12 | 0 | Y |
| 2026-10-05 | ui | 5 | 0 | Y |
| 2026-10-07 | platform-plugin-flex-query | 4 | 4 | Y |
| 2026-10-07 | platform-plugin-market-data | 5 | 3 | Y |
| 2026-10-07 | platform-plugin | 2 | 2 | Y |
| 2026-10-07 | platform | 10 | 8 | Y |
| 2026-10-07 | research | 8 | 4 | Y |
| 2026-10-07 | trade-api | 2 | 2 | Y |
| 2026-10-07 | trade-core | 4 | 2 | Y |
| 2026-10-07 | trade-frontend | 8 | 0 | Y |
| 2026-10-07 | trade-infra | 14 | 12 | Y |
| 2026-10-07 | trade-worker | 2 | 1 | Y |
| 2026-10-07 | ui | 3 | 1 | Y |
| 2026-10-19 | platform | 50 | 3 | Y |
| 2026-10-19 | trade-infra | 47 | 18 | Y |
| 2026-10-20 | platform | 10 | 8 | Y |
| 2026-10-20 | research | 2 | 0 | Y |
| 2026-10-20 | trade-api | 2 | 0 | Y |
| 2026-10-20 | trade-core | 4 | 1 | Y |
| 2026-10-20 | trade-frontend | 5 | 2 | Y |
| 2026-10-20 | trade-infra | 6 | 6 | Y |

## 8. 这台 Mac 的其余部分（第 1 稿的数，没重测）

数据卷 926 GiB，可用 363 GiB（00:3x）；默认 Go 缓存约 12 GiB；Docker 镜像 19.8 GiB、构建缓存 21.3 GiB；Cursor `state.vscdb` 51.4 GiB；会话 scratchpad 3.35 GiB；本地 Time Machine 快照 22 个。

## 9. 集群（00:3x 只读 get）

| 对象 | 数量 | 说明 |
|---|---|---|
| PipelineRun | 306 | `tekton-pipelinerun-ttl`（建于 2026-08-10，infra `73e181f`；10-24 04:20Z 最近一次成功）删 7 天前结束的 |
| TaskRun | 3030 | 单独的 475：近 7 天每天新增 34–94 个（10-18 37、10-19 53、10-20 94、10-21 88、10-22 34、10-23 39）；423 个超过 2 天、122 个超过 7 天 |
| PVC | 285 | 无主的 3 个：`gitea-backup`、`gitea-data`、`registry-data`（第 1 稿把 `gitea-backup` 误写成 `gitea`）；4 个属于 06-19 的单独 TaskRun |
| `tekton-pipelinerun-ttl` 的 Role | — | 只能 get/list/delete `pipelineruns`、`taskruns`，list/delete `pods`；按发布记录判断要再给 `configmaps` 的 get/list |

**没查到**：06、两台 mini（Agent 登不上，没有主机指标）；local-path 卷的实际占用；PROD / STG 事件流里的 `prune_refused` / `prune_failed`；M-27 Q07 收下的是哪次尝试；NAS 上有没有可用的归档。
