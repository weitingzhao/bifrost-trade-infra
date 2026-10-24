# 第 4 轮 4.6 一次性盘点（只读，2026-10-24 00:00 CDT）

> 配套：`CUT-lifecycle-2026-10-24.md`。**这次什么都没删**：只用了 `git fetch`（不带 `--prune`）、`git ls-remote`、`git status`、`git cherry`、`git rev-list`、`du`、`find`、`lsof`，
> 运行时的 `get_task`（PROD、STG），Prometheus 查询，和 `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n cicd get pvc,pipelinerun,taskrun`、`kubectl get pv`（只 get）。
> 「已合入」的判据与 `scripts/prune-merged-branches.sh` 相同：分支上 main 没有的每个提交（`git cherry`），在 main 上有同一 Change-Id，没有 Change-Id 时有同一标题。
> 「在远端」= 提交都能从 Gitea **现在存在**的分支头走到（`git rev-list <sha> --not <ls-remote 的全部 sha>` 为 0）；本地陈旧的远端跟踪引用不算。
> 路径：`<ws>` = 工作区根 `~/Desktop/stocks`。完整逐条清单在本会话的 scratchpad（见 §7），一次性清理那一步会用脚本重新生成，不依赖它们。

## 1. 汇总

| 类 | 总数 | 可自动清 | 只报不删 | 要 Owner 定 | 暂留 / 不动 |
|---|---|---|---|---|---|
| Gitea `agent/**` | 27 | 7（agentd，规则内已到期却没删） | — | 20（收下没合，D-L5） | — |
| Gitea 人的分支 | 53 | （D-L1 选 A 后 31） | — | 31（已合入，D-L1）+ 12（未合入，D-L2） | 10（不到 24 小时） |
| GitHub 冻结分支 | 157 | — | — | 157（D-L3；130 已在 main，27 不在，其中 16 只在 GitHub） | — |
| 本地分支 | 489 | 437 | 37 | — | 15 |
| 本机 worktree（不含 11 个主 checkout） | 334 | 295（S2 后再 +6：5 个只多了生成文件、1 个 `push-main` 残留） | 21（S2 后 15） | — | 17 + 本线 1 |
| 复核目录 | 472 codex + 16 其他 | 缓存：35 个目录 16.3 GB | — | 记录（D-L4） | — |
| `~/agent-work/.cache` | 1 | `go-build GOMODCACHE=` 1.1 GB；`go-build` 18.6 GB 封顶到 20 GB 以下 | 草稿目录（`gates-*`、`paints-*` 等） | — | `go-mod`、`npm` |
| `~/agent-work` 普通目录 / 文件 | 75 / 69 | — | 全部（没有登记，主人只能猜） | 归档按 D-L4 | — |
| `cicd` PipelineRun | 305 | 现有 7 天 CronJob 照跑 | — | 改保留期（D-L7） | — |
| `cicd` 单独 TaskRun | 475 | — | — | 122 个超过 7 天（D-L7，`cicd` 写入） | — |
| `cicd` PVC | 284 | 277 个随 PipelineRun 删 | — | 4 个属于 06-19 的单独 TaskRun（D-L7） | 3 个数据卷（Gitea、registry） |

## 2. 分支

### 2.1 Gitea `agent/**`（27 条，逐条查了任务状态）

规则（`bifrost-platform/api/internal/agentrt/store/prune.go`）：任务取消 / 驳回、被取代、收下且已进 main、收下且 `no_merge`，满 24 小时就由 agentd 删。
10-23 23:02 时 infra 有 15 条，到 23:50 剩 2 条（13 条在这一小时内被删，见 §2.5）。

| 仓库 | 分支 | 运行时 | mission | 任务状态 | 分支头日期 | 判定 |
|---|---|---|---|---|---|---|
| platform | `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a1` | STG | M-1 | cancelled 10-20 21:17Z | 2026-10-15 | 可自动清（agentd；规则内已到期，未删） |
| platform | `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a2` | STG | M-1 | cancelled 10-20 21:17Z | 2026-10-15 | 可自动清（agentd；规则内已到期，未删） |
| platform | `agent/t_01M50M1CZSDN8PNHRH8C2241RS/a1` | STG | M-2 | accepted 10-15（UniFi 测试，演练） | 2026-10-15 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M511RV9S41AEW9CDA76024Q3/a1` | PROD | M-1 | accepted 10-16（一段注释） | 2026-10-15 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M51EHZ92V5F2PRB7JCZVHTQ3/a1` | PROD | M-2 | accepted 10-16（一段注释） | 2026-10-15 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M55AN78GPF9V6NFZFS4KJP8N/a1` | PROD | M-3 | accepted 10-17（safego 测试，2.3 演练） | 2026-10-17 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M55AN78M1MX9NF9Q958T96Z3/a1` | PROD | M-3 | accepted 10-17（statefile 测试，2.3 演练） | 2026-10-17 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M56J5QPAAQQP53KV4MQYCW5Q/a1` | PROD | M-4 | accepted 10-18（一段注释） | 2026-10-17 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M57YSQN6B43ZFNESD9VQ2HA9/a1` | STG | M-13 | cancelled 10-20 23:22Z | 2026-10-18 | 可自动清（agentd；规则内已到期，未删） |
| platform | `agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a2` | STG | M-16 | accepted 10-19（T26 返工演练） | 2026-10-18 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5B37AYBAHQTM6RMQZZHE3AT/a1` | STG | M-23 | accepted 10-19（隔离版 agentd 走查） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5B6KKPMM15HZB4BC0ZWVJ5R/a1` | STG | M-24 | accepted 10-19（TD-382 走查） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSBEZ7J3BQM0EV7SG3NB2N/a1` | STG | M-26 | accepted 10-20（Gate B 实测） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSPFV3S9ET52X3JT76HJFS/a1` | STG | M-27 | accepted 10-20（基准题 Q04） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSPFV8JBH908TR6M58S6Q9/a1` | STG | M-27 | accepted 10-20（基准题 Q06） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a1` | STG | M-27 | accepted 10-20（基准题 Q07）；两次尝试 | 2026-10-19 | 两条中被取代的一条已到期（agentd）；另一条要 Owner 定（D-L5） |
| platform | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a2` | STG | M-27 | accepted 10-20（基准题 Q07）；两次尝试 | 2026-10-19 | 两条中被取代的一条已到期（agentd）；另一条要 Owner 定（D-L5） |
| platform | `agent/t_01M5BSPFVDY1N34EGQ5THXYMMD/a1` | STG | M-27 | accepted 10-20（基准题 Q18） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSTGPP9FC3PCF4NF5PM7GD/a1` | PROD | M-13 | accepted 10-20（Gate B 实测） | 2026-10-19 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BSTYPZ54K9NV1F1S8HSVYZ/a1` | PROD | M-14 | cancelled 10-20 19:03Z | 2026-10-19 | 可自动清（agentd；规则内已到期，未删） |
| platform | `agent/t_01M5BSTYPZ54K9NV1F1S8HSVYZ/a2` | PROD | M-14 | cancelled 10-20 19:03Z | 2026-10-19 | 可自动清（agentd；规则内已到期，未删） |
| platform | `agent/t_01M5BV3W403F0SYH6HF8RAFNJ0/a1` | PROD | M-15 | accepted 10-20（基准题 Q04） | 2026-10-20 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BV3W43ETJPVBT55T2XYW30/a1` | PROD | M-15 | accepted 10-20（基准题 Q06） | 2026-10-20 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BV3W45NDSBHBTEFY4RMT97/a1` | PROD | M-15 | accepted 10-20（基准题 Q07） | 2026-10-20 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| platform | `agent/t_01M5BV3W48B5HGHZB5JJKHE81G/a1` | PROD | M-15 | accepted 10-20（基准题 Q18） | 2026-10-20 | 要 Owner 定（D-L5：标 no_merge 或合并） |
| trade-infra | `agent/t_01M5B8BF2B5K3QPRTC1GMBBJQ6/a1` | PROD | M-9 | accepted 10-20；收下的 a2 已作为 d989dde 进 main、分支已删；a1 是被叫停的上一次尝试 | 2026-10-19 | 可自动清（agentd；被取代，已到期，未删） |
| trade-infra | `agent/t_01M5G4W33CRXXVX4C7GJTCJ3VR/a1` | STG | M-103 | accepted 10-21（T24/T34 演练） | 2026-10-21 | 要 Owner 定（D-L5：标 no_merge 或合并） |

按规则早该删的 7 条：取消超过 24 小时的 5 条（STG M-1 两条、STG M-13 一条、PROD M-14 两条），被取代的 2 条（STG M-27 Q07 两次尝试里没被收下的一条；PROD M-9 的 a1）。
为什么还在：**没查到**（要读事件流里的 `prune_refused` / `prune_failed` 和尝试的 `pushed_ref`）。推测之一：被叫停或主机被停的尝试没记下推送的提交，规则对「分支指向的不是该尝试推送的提交」一律保留——归 S5。
PROD M-9、M-13、M-15 没有 `no_merge` 标记，10-20 的 TD-383 已写明「补要写 PROD 库，留给 Owner」。

### 2.2 Gitea 人的分支（53 条）

**未合入（12 条，D-L2）**

| 仓库 | 分支 | 分支头 | main 没有的提交数 | 最新提交 |
|---|---|---|---|---|
| platform | `w31/td-310-anchor` | 2026-10-11 | 4 | fix(releasepolicy): a freeze has an identity that never repeats; the g |
| platform | `w31/w55-ddl-allowlist` | 2026-10-10 | 3 | W-55: treat a comment as whitespace and refuse shadowable types |
| trade-infra | `cursor/m2-infra` | 2026-10-08 | 1 | fix(release): make hold interruptible on SIGTERM (TD-269) |
| trade-infra | `w31/td-310-anchor` | 2026-10-11 | 4 | ci(platform): the Go tests wait for the infra checkout (TD-310) |
| trade-infra | `w31/td-312` | 2026-10-11 | 1 | docs(secrets): after rotating the admin token, sign in again in every  |
| trade-infra | `w31/td-411-dryrun` | 2026-10-22 | 10 | scratch: W-31 3.4 the pin task at e318a80 renamed for a server dry-run |
| trade-infra | `w31/w56-gates` | 2026-10-10 | 3 | docs(release): platform PROD promote (W-56) |
| trade-infra | `w31/w56-matrix` | 2026-10-11 | 13 | fix(release): a request record has a closed shape and each expected re |
| trade-infra | `w31/w56-slice-a` | 2026-10-11 | 2 | fix(release): the PROD write matrix never under-reports: uncertain is  |
| trade-infra | `w31/w66-lane` | 2026-10-11 | 3 | fix(agent-config): a lane step runs only while its driver is alive; ex |
| trade-infra | `w31/w66-lane-v2` | 2026-10-11 | 7 | test(agent-config): a mutation test over the lane's evidence: no mutan |
| trade-infra | `w31/w66-shadow` | 2026-10-12 | 2 | Record a shadow step through bookkeeping when rec.py has no run. |

**已合入、超过 24 小时（31 条，D-L1）**：
- platform（13）：`codex/ops-ui-v2`、`w31/25-review-488`、`w31/25-slice5`、`w31/25-slice5-gaps`、`w31/ci-fix-paints`、`w31/ci-follow-infra-prod`、`w31/owner-signoff`、`w31/plan-artifact-path`、`w31/plan-follows-newest-round`、`w31/plan-signoff-usable`、`w31/t32-seat-route`、`w31/td-411-applied`、`w31/td-420-421`
- platform-plugin（1）：`cursor/w33d-plugin`
- platform-plugin-flex-query（2）：`cursor/k-flex`、`w31/w56-flex-freeze`
- platform-plugin-market-data（1）：`cursor/w-market-data`
- trade-infra（11）：`w31/25-slice5-t24`、`w31/gate-a-closeout`、`w31/gate-a-freeze-drill`、`w31/gate-a-freeze-drill-fix`、`w31/gate-a-t32`、`w31/gate-a-t32-t36`、`w31/gate-a-t33-done`、`w31/gate-a-t33-pass`、`w31/owner-signoff-docs`、`w31/release-speedup`、`w31/td-411-pipeline`
- trade-worker（3）：`cursor/t2-worker`、`cursor/t3-worker`、`cursor/x-worker`

**已合入、不到 24 小时（10 条，暂留）**：`fix/checklist-prober-rollout-gap`、`w31/agentd-drop-push-base`、`w31/bi1-1-data`、`w31/bi1-1-data-r2`、`w31/bi1-1b-card-text-guard`、`w31/bi1-2-api`、`w31/r3-35-online`、`w31/td-425-not-started`、`w31/td-425-not-started-r2`、`w31/gitea-primary-leftovers`

### 2.3 GitHub 冻结分支（157 条，公开，D-L3）

| 仓库 | 总数 | 已在 main（祖先） | 已在 main（同 Change-Id / 标题） | 不在 main | 其中 Gitea 也没有 |
|---|---|---|---|---|---|
| platform | 75 | 62 | 3 | 10 | 8 |
| platform-plugin | 1 | 1 | 0 | 0 | 0 |
| platform-plugin-flex-query | 2 | 2 | 0 | 0 | 0 |
| platform-plugin-market-data | 1 | 1 | 0 | 0 | 0 |
| research | 2 | 2 | 0 | 0 | 0 |
| trade-api | 2 | 2 | 0 | 0 | 0 |
| trade-core | 4 | 3 | 0 | 1 | 1 |
| trade-frontend | 5 | 3 | 1 | 1 | 1 |
| trade-infra | 62 | 29 | 18 | 15 | 6 |
| trade-worker | 3 | 3 | 0 | 0 | 0 |

不在 main 的 27 条（★ = GitHub 是唯一的远端副本）：

| 仓库 | 分支 | 分支头 | Gitea 有没有 |
|---|---|---|---|
| platform | `cursor/d1-platform` ★ | 2026-10-07 | 没有 |
| platform | `cursor/n-platform` ★ | 2026-10-08 | 没有 |
| platform | `w31/td-306-307` ★ | 2026-10-11 | 没有 |
| platform | `w31/td-306-b` ★ | 2026-10-11 | 没有 |
| platform | `w31/td-306-c` ★ | 2026-10-11 | 没有 |
| platform | `w31/td-310-anchor` | 2026-10-11 | 有 |
| platform | `w31/td-312` ★ | 2026-10-11 | 没有 |
| platform | `w31/td-313-gate-proof` ★ | 2026-10-11 | 没有 |
| platform | `w31/w55-ddl-allowlist` | 2026-10-10 | 有 |
| platform | `w31/w62-slice4` ★ | 2026-10-11 | 没有 |
| trade-core | `fix/w4-snapshot-stale-accounts` ★ | 2026-10-06 | 没有 |
| trade-frontend | `fix/data-gap-wording` ★ | 2026-10-06 | 没有 |
| trade-infra | `cursor/m2-infra` | 2026-10-08 | 有 |
| trade-infra | `cursor/rp-infra` ★ | 2026-10-07 | 没有 |
| trade-infra | `cursor/w33-infra` ★ | 2026-10-08 | 没有 |
| trade-infra | `cursor/w33b-infra` ★ | 2026-10-09 | 没有 |
| trade-infra | `cursor/w33c-infra` ★ | 2026-10-09 | 没有 |
| trade-infra | `cursor/w33d-infra` ★ | 2026-10-09 | 没有 |
| trade-infra | `cursor/w33r-infra` ★ | 2026-10-08 | 没有 |
| trade-infra | `w31/td-310-anchor` | 2026-10-11 | 有 |
| trade-infra | `w31/td-312` | 2026-10-11 | 有 |
| trade-infra | `w31/w56-gates` | 2026-10-10 | 有 |
| trade-infra | `w31/w56-matrix` | 2026-10-11 | 有 |
| trade-infra | `w31/w56-slice-a` | 2026-10-11 | 有 |
| trade-infra | `w31/w66-lane` | 2026-10-11 | 有 |
| trade-infra | `w31/w66-lane-v2` | 2026-10-11 | 有 |
| trade-infra | `w31/w66-shadow` | 2026-10-12 | 有 |

没有一条 `agent/` 分支在 GitHub 上（9.1 的同步只推 main 和标签，成立）。

### 2.4 本地分支（489 条）

| 仓库 | 总数 | 可自动清 | 只报不删 | 暂留 |
|---|---|---|---|---|
| platform | 231 | 205 | 18 | 8 |
| platform-plugin | 2 | 2 | 0 | 0 |
| platform-plugin-flex-query | 10 | 10 | 0 | 0 |
| platform-plugin-market-data | 10 | 9 | 1 | 0 |
| research | 17 | 15 | 2 | 0 |
| trade-api | 7 | 6 | 1 | 0 |
| trade-core | 11 | 8 | 3 | 0 |
| trade-frontend | 12 | 9 | 2 | 1 |
| trade-infra | 181 | 165 | 10 | 6 |
| trade-worker | 6 | 6 | 0 | 0 |
| ui | 2 | 2 | 0 | 0 |

可自动清的依据：已合入 main（同 Change-Id / 标题），或提交都在 Gitea 现有分支上，并且没有检出在要留的 worktree 里。

只报不删、没有检出在任何 worktree 里的（有只在本地的提交）：

| 仓库 | 分支 | 分支头 | 只在本地的提交数 |
|---|---|---|---|
| platform | `cursor/n-platform` | 2026-10-08 | 1 |
| platform | `w31/25-release-lane` | 2026-10-19 | 2 |
| platform | `w31/td-306-307` | 2026-10-11 | 4 |
| platform | `w31/td-306-b` | 2026-10-11 | 2 |
| platform | `w31/td-306-c` | 2026-10-11 | 1 |
| platform | `w31/td-313-gate-proof` | 2026-10-11 | 2 |
| platform | `w31/td-313-proof` | 2026-10-11 | 1 |
| trade-api | `td-lane-ae-2026-10-04` | 2026-10-04 | 3 |
| trade-core | `fix/w4-snapshot-stale-accounts` | 2026-10-06 | 1 |
| trade-core | `keep/ceff454-core-0.36.2` | 2026-10-03 | 1 |
| trade-core | `td-lane-aj-2026-10-04` | 2026-10-04 | 2 |
| trade-frontend | `fix/data-gap-wording` | 2026-10-06 | 3 |
| trade-infra | `cursor/rp-infra` | 2026-10-07 | 1 |
| trade-infra | `cursor/w33-infra` | 2026-10-08 | 1 |
| trade-infra | `cursor/w33b-infra` | 2026-10-09 | 3 |
| trade-infra | `cursor/w33d-infra` | 2026-10-09 | 1 |
| trade-infra | `cursor/w33r-infra` | 2026-10-08 | 1 |
| trade-infra | `w31/chief-exam-s5` | 2026-10-20 | 1 |

另有 19 条检出在只报不删的 worktree 里，跟着 §3.2 的判定走。

### 2.5 13 条 infra `agent/` 分支在 10-23 23:02 – 23:50 之间消失

`agent/t_01M5B8BF2B5K3QPRTC1GMBBJQ6/a2`、`t_01M5BKDPRSBWXJYZVES8KEETR0/a1`、`t_01M5BKDPS0DYA4WNABCFQ1RJVB/a1`、`t_01M5BSPFVFY0MY6J7NABB6SR5C/a1,a2`、`t_01M5BSPFVJZFBAZ2XES6GPFTTM/a1,a2`、
`t_01M5BV3W4AHSAB5XXNJWT3FWJD/a1,a2,a3`、`t_01M5BV3W4CCAPD00XXEB4PKYJY/a1,a2,a3`。剩下的两条正是规则要留（收下没合）或可能没记推送提交的那类，所以多半是 agentd 按规则删的；删除记录没读。

## 3. 工作目录（worktree）

### 3.1 按仓库与判定

| 仓库 | worktree（不含主 checkout） | 可自动清 | 只报不删 | 暂留 |
|---|---|---|---|---|
| platform | 178 | 157 | 12 | 9 |
| platform-plugin-flex-query | 1 | 1 | 0 | 0 |
| platform-plugin-market-data | 3 | 2 | 1 | 0 |
| research | 5 | 3 | 2 | 0 |
| trade-frontend | 5 | 3 | 1 | 1 |
| trade-infra | 117 | 105 | 5 | 7 |
| ui | 25 | 24 | 0 | 1 |

按位置：agent-work · 只报不删 16；agent-work · 可自动清 280；agent-work · 暂留（在用） 17；agent-work · 本线（自己） 1；other · 只报不删 1；root-.worktrees · 只报不删 1；root-.worktrees · 可自动清 5；workspace-root · 只报不删 3；workspace-root · 可自动清 10

大小（`du`，含其中的 node_modules 与缓存）：可自动清 8.8 GB；暂留（在用） 1.1 GB；只报不删 5.5 GB；本线（自己） 0.0 GB

可自动清的依据：HEAD 已合入 main，干净，24h 无改动：285；HEAD 在远端分支上，干净，24h 无改动：10（`git status --porcelain` 除未跟踪的 `node_modules` 外为空、24 小时内没有文件改动、`lsof -d cwd` 里没有进程）。

### 3.2 只报不删（21 个）

| 仓库 | 路径 | 分支 | 原因 | 大小 | 最近改动 | 备注 |
|---|---|---|---|---|---|---|
| platform | `<ws>/bifrost-platform-d1` | `cursor/d1-platform` | 1 个提交只在本地、main 上没有同 Change-Id/标题 | 74 MB | 2026-10-07 |  |
| platform | `<ws>/bifrost-platform-phase3-int` | `cursor/phase3-platform` | 未提交改动 tracked=0 untracked=2 | 332 MB | 2026-10-07 | 未跟踪的只有 `.husky/_`、`tsbuildinfo`，S2 后可清 |
| platform | `<ws>/bifrost-platform-phase3-s1` | `cursor/phase3-s1` | 未提交改动 tracked=0 untracked=2 | 15 MB | 2026-10-21 | 未跟踪的只有 `.husky/_`、`tsbuildinfo`、`node_modules`，S2 后可清 |
| platform | `~/agent-work/agentrt-22k/bifrost-platform` | `w31/agentrt-22-mission-card` | 4 个提交只在本地、main 上没有同 Change-Id/标题 | 15 MB | 2026-10-14 |  |
| platform | `~/agent-work/chief-exam-s5/bifrost-platform` | `w31/chief-exam-s5` | 未提交改动 tracked=0 untracked=1 | 20 MB | 2026-10-20 | 未跟踪 `zz_calib_local_test.go`（手写的校准测试） |
| platform | `~/agent-work/gate-a-t33/bifrost-platform` | `(detached)` | 未提交改动 tracked=0 untracked=1 | 20 MB | 2026-10-20 | 未跟踪 `api/cmd/zz-progress/` |
| platform | `~/agent-work/td-312/bifrost-platform` | `w31/td-312` | 2 个提交只在本地、main 上没有同 Change-Id/标题 | 75 MB | 2026-10-11 |  |
| platform | `~/agent-work/td-329/bifrost-platform` | `w31/td-329-action-outlives-request` | 未提交改动 tracked=0 untracked=1 | 961 MB | 2026-10-13 | 未跟踪的只有 `.cache/`（Go 缓存），S2 后可清 |
| platform | `~/agent-work/td-333/bifrost-platform` | `w31/td-333-334-approval-exec` | 未提交改动 tracked=0 untracked=1 | 2262 MB | 2026-10-13 | 未跟踪的只有 `.cache/`（Go 缓存），S2 后可清 |
| platform | `~/agent-work/td-337/bifrost-platform` | `w31/td-337-quiet-hours` | 未提交改动 tracked=6 untracked=6 | 1308 MB | 2026-10-13 | 6 处改动 + 新文件 `approvalnotify/quiet.go` |
| platform | `~/agent-work/w31-25-slice5-platform` | `w31/25-plan-zh` | 1 个提交只在本地、main 上没有同 Change-Id/标题 | 358 MB | 2026-10-21 |  |
| platform | `~/agent-work/w62-slice4/bifrost-platform` | `w31/w62-slice4` | 10 个提交只在本地、main 上没有同 Change-Id/标题 | 75 MB | 2026-10-11 |  |
| platform-plugin-market-data | `~/agent-work/td-305-market-data` | `codex/td-305` | 4 个提交只在本地、main 上没有同 Change-Id/标题 | 9 MB | 2026-10-11 |  |
| research | `~/agent-work/data-integrity-main-research` | `codex/data-integrity-main` | 未提交改动 tracked=0 untracked=1 | 19 MB | 2026-10-11 | 未跟踪的只有 `.venv`，S2 后可清 |
| research | `~/agent-work/td-305-research` | `codex/td-305-gate` | 1 个提交只在本地、main 上没有同 Change-Id/标题 | 8 MB | 2026-10-11 |  |
| trade-frontend | `~/agent-work/td-274-frontend` | `codex/td-274` | 未提交改动 tracked=1 untracked=0 | 25 MB | 2026-10-10 | `package-lock.json` 有改动，另有 1 个本地提交但已合入 |
| trade-infra | `<ws>/.worktrees/w33c-infra` | `cursor/w33c-infra` | 1 个提交只在本地、main 上没有同 Change-Id/标题 | 6 MB | 2026-10-09 |  |
| trade-infra | `~/agent-work/night-td374/bifrost-trade-infra` | `night/td374-ci-timeout` | 1 个提交只在本地、main 上没有同 Change-Id/标题 | 14 MB | 2026-10-19 |  |
| trade-infra | `~/agent-work/td-305-infra` | `codex/td-305` | 13 个提交只在本地、main 上没有同 Change-Id/标题 | 9 MB | 2026-10-11 |  |
| trade-infra | `~/agent-work/w56-slice-a/bifrost-trade-infra` | `w31/w56-slice-a` | 未提交改动 tracked=0 untracked=1 | 8 MB | 2026-10-11 | 未跟踪测试数据目录 |
| trade-infra | `$TMPDIR/push-main.XrTZfq/bifrost-trade-infra` | `(detached)` | 未提交改动 tracked=12 untracked=0 | 15 MB | 2026-10-21 | `push-main.sh` 被杀时漏下的临时 checkout；HEAD 在 main 上，12 处「删除」多半是 macOS 清 `$TMPDIR` 旧文件造成的（推测）；R11 可清 |

### 3.3 暂留（正在用，17 个）

| 仓库 | 路径 | 分支 | 依据 |
|---|---|---|---|
| platform | `~/agent-work/bi1-1` | `w31/bi1-1-data` | 24 小时内有文件改动 |
| platform | `~/agent-work/bi1-1b` | `w31/bi1-1b-card-text-guard` | 24 小时内有文件改动 |
| platform | `~/agent-work/bi1-2` | `w31/bi1-2-api` | 24 小时内有文件改动 |
| platform | `~/agent-work/codex-ops-ui/bifrost-platform` | `codex/ops-ui-v2` | 有进程以它为 cwd |
| platform | `~/agent-work/coord-platform` | `w31/plan-follows-newest-round` | 24 小时内有文件改动 |
| platform | `~/agent-work/r3-35` | `w31/r3-35-online` | 24 小时内有文件改动 |
| platform | `~/agent-work/r4-planimport-tool` | `(detached)` | 24 小时内有文件改动 |
| platform | `~/agent-work/td-420-421/bifrost-platform` | `w31/td-420-421` | 24 小时内有文件改动 |
| platform | `~/agent-work/td-425` | `w31/td-425-not-started` | 24 小时内有文件改动 |
| trade-frontend | `~/agent-work/rules-symbols` | `codex/rules-symbols` | 有进程以它为 cwd |
| trade-infra | `~/agent-work/coord-infra2` | `(detached)` | 24 小时内有文件改动 |
| trade-infra | `~/agent-work/r4-b4` | `w31/r4-w68-b4` | 24 小时内有文件改动 |
| trade-infra | `~/agent-work/r4-coord` | `w31/r4-coordinator-placement` | 24 小时内有文件改动 |
| trade-infra | `~/agent-work/r4-landing` | `w31/r4-landing-cut` | 24 小时内有文件改动 |
| trade-infra | `~/agent-work/r4-lanes` | `w31/r4-release-lanes` | 24 小时内有文件改动 |
| trade-infra | `~/agent-work/r4-plan` | `w31/r4-plan` | 24 小时内有文件改动 |
| ui | `~/agent-work/td-420-421/bifrost-ui` | `(detached)` | 24 小时内有文件改动 |

### 3.4 可自动清：最大的 20 个（共 295 个）

| 仓库 | 路径 | 分支 | 大小 | 最近改动 | 依据 |
|---|---|---|---|---|---|
| research | `~/agent-work/td-172-142-research` | `codex/td-304` | 816 MB | 2026-10-10 | HEAD 已合入 main，干净，24h 无改动 |
| research | `~/agent-work/td-92-94-research` | `codex/td-92-94` | 759 MB | 2026-10-10 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/w31-23-t12/bifrost-platform` | `w31/23-t12-waits` | 357 MB | 2026-10-21 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-platform` | `(detached)` | 314 MB | 2026-10-21 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-platform` | `(detached)` | 313 MB | 2026-10-20 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `<ws>/bifrost-platform-phase3-s4` | `cursor/phase3-s4` | 275 MB | 2026-10-07 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `<ws>/bifrost-platform-phase3-s3` | `cursor/phase3-s3` | 275 MB | 2026-10-07 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `<ws>/bifrost-platform-phase3-s5` | `cursor/phase3-s5` | 274 MB | 2026-10-07 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/w31-td415/platform` | `w31/td-415-disk` | 142 MB | 2026-10-21 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/td-411-schema/bifrost-platform` | `w31/td-411-schema` | 92 MB | 2026-10-21 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/guard-1a/bifrost-platform` | `w31/td-317-platform` | 91 MB | 2026-10-12 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/blocked-card/bifrost-platform` | `w31/card-rule-all-kinds` | 91 MB | 2026-10-20 | HEAD 已合入 main，干净，24h 无改动 |
| ui | `~/agent-work/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-ui` | `(detached)` | 82 MB | 2026-10-20 | HEAD 已合入 main，干净，24h 无改动 |
| ui | `~/agent-work/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-ui` | `(detached)` | 82 MB | 2026-10-21 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/td384/bifrost-platform` | `w31/td383-nomerge-prune` | 81 MB | 2026-10-20 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/w31-25-g2/bifrost-platform` | `w31/25-g2` | 81 MB | 2026-10-20 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/w31-25-release/bifrost-platform` | `w31/22b-nav-slice2` | 80 MB | 2026-10-19 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/td-310/bifrost-platform` | `w31/td-310-anchor` | 75 MB | 2026-10-11 | HEAD 在远端分支上，干净，24h 无改动 |
| platform | `~/agent-work/td-306-307/bifrost-platform` | `w31/td-306-merge` | 75 MB | 2026-10-11 | HEAD 已合入 main，干净，24h 无改动 |
| platform | `~/agent-work/w65-integration/bifrost-platform` | `(detached)` | 75 MB | 2026-10-11 | HEAD 已合入 main，干净，24h 无改动 |

### 3.5 工作区根下的旧目录（14 个）与 `.worktrees/`

| 目录 | 仓库 | 分支 | 判定 | 依据 |
|---|---|---|---|---|
| `<ws>/.worktrees/w32-infra` | trade-infra | `cursor/w32-infra` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/.worktrees/w32-platform` | platform | `cursor/w32-platform` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/.worktrees/w32-report` | trade-infra | `cursor/w32-report` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/.worktrees/w33c-infra` | trade-infra | `cursor/w33c-infra` | 只报不删 | 1 个提交只在本地、main 上没有同 Change-Id/标题 |
| `<ws>/.worktrees/w33c-platform` | platform | `cursor/w33c-platform` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/.worktrees/w33c-report` | trade-infra | `(detached)` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-d1` | platform | `cursor/d1-platform` | 只报不删 | 1 个提交只在本地、main 上没有同 Change-Id/标题 |
| `<ws>/bifrost-platform-e1` | platform | `cursor/e1-platform` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-phase3-int` | platform | `cursor/phase3-platform` | 只报不删 | 未提交改动 tracked=0 untracked=2 |
| `<ws>/bifrost-platform-phase3-s1` | platform | `cursor/phase3-s1` | 只报不删 | 未提交改动 tracked=0 untracked=2 |
| `<ws>/bifrost-platform-phase3-s2` | platform | `cursor/phase3-s2` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-phase3-s3` | platform | `cursor/phase3-s3` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-phase3-s4` | platform | `cursor/phase3-s4` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-phase3-s5` | platform | `cursor/phase3-s5` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-trade-infra-a6r` | trade-infra | `cursor/a6r-infra` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-trade-infra-a6r-report` | trade-infra | `cursor/a6r-report` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-trade-infra-d1` | trade-infra | `cursor/d1-infra` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-trade-infra-e1` | trade-infra | `cursor/e1-infra` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-trade-infra-phase3-report` | trade-infra | `cursor/phase3-lane-c-report` | 可自动清 | HEAD 已合入 main，干净，24h 无改动 |
| `<ws>/bifrost-platform-phase3-notes` | — | — | 只报不删 | 不是 git，5 份 10-07 的笔记（48 KB） |

## 4. `~/agent-work`（868 项，58.1 GB）

| 类 | 数量 | 大小 |
|---|---|---|
| `.cache` 共享缓存 | 1 | 20.2 GB |
| `codex-review-*` | 472 | 18.2 GB |
| lane（含 worktree） | 228 | 14.2 GB |
| 普通目录 | 75 | 5.2 GB |
| `claude-review-*` / `cursor-review-*` | 16 | 0.3 GB |
| 软链接与克隆（`bifrost-finance` 是真克隆） | 7 | 0.0 GB |
| 文件 | 69 | 0.0 GB |

### 4.1 复核目录里的可再生成缓存

| 子目录名 | 个数 | 大小 | `disk-guard.sh` 认不认 |
|---|---|---|---|
| `go-cache` | 12 | 4.91 GB | 不认 |
| `cache` | 4 | 3.10 GB | 不认 |
| `.cache` | 3 | 2.63 GB | 不认 |
| `.review-cache` | 4 | 2.07 GB | 不认 |
| `.gocache` | 2 | 1.59 GB | 不认 |
| `go-build` | 1 | 1.14 GB | 不认 |
| `gocache` | 5 | 0.63 GB | 认 |
| `review-cache` | 1 | 0.26 GB | 不认 |
| `tmp` | 1 | 0.00 GB | 认 |
| `node_modules` | 2 | 0.00 GB | 不认 |

合计 35 个目录、16.3 GB。其中没有 `run.done` 的 9 个（codex-review-310、codex-review-311、codex-review-312、codex-review-315、codex-review-331、codex-review-334、codex-review-335、codex-review-351、codex-review-506）占 4.07 GB；`disk-guard.sh` 认得名字的 0.63 GB 全在这 9 个里，而 `sweep` 只清有 `run.done` 的，所以一样清不掉。
`run.done`：420 有、52 没有。报告已抄进 `work/multi-agent/reviews/` 的复核号 132 个，只在本机的约 315 个；仓库文档按 `~/agent-work/codex-review-<n>/` 路径引用的 31 个（所以记录不能直接删，D-L4）。

### 4.2 `.cache`

`go-build` 18.64 GB · `go-build GOMODCACHE=`（引号写错留下的目录）1.12 GB · `go-mod` 0.25 GB · `tmp` 0.16 GB · `npm` 0.07 GB；另有 30 多个不是缓存的草稿目录与文件（`gates-pa*`、`gates-signoff*`、`gates-su*`、`paints-*`、`pa-ctl`、`review518`、`api-new.go`、`cut25.md` 等），只报。

### 4.3 普通目录：最大的 10 个（没有登记，除注明的外只报）

| 目录 | 大小 | 最近改动 |
|---|---|---|
| `r3-35-scratch` | 1620 MB | 2026-10-23 |
| `bi1-1-scratch` | 888 MB | 2026-10-23 |
| `merge-accepted`（里面是 `merge_accepted.py` 留下的 main 上的 detached worktree，按 R11 可清） | 823 MB | 2026-10-21 |
| `bi1-2-scratch` | 745 MB | 2026-10-23 |
| `td-172-142-evidence` | 736 MB | 2026-10-10 |
| `agentd-build` | 280 MB | 2026-10-21 |
| `pgci` | 55 MB | 2026-10-14 |
| `status` | 51 MB | 2026-10-21 |
| `build` | 44 MB | 2026-10-15 |
| `codex-audit-td298` | 16 MB | 2026-10-10 |

## 5. 这台 Mac 的其余部分

| 东西 | 大小 | 现在谁管 | 判定 |
|---|---|---|---|
| 数据卷 `/System/Volumes/Data` | 926 GB，可用 357–365 GB | — | 基线 |
| 默认 Go 缓存 `~/Library/Caches/go-build` | 12 GB | `disk-guard.sh`：超过 30 GB 且没有 Go 构建时清 | 不动 |
| Docker | 镜像 19.8 GB、构建缓存 21.3 GB（328 项）、匿名卷 1.1 GB | `disk-guard.sh`：每周删 7 天前的构建缓存与悬空镜像 | 不动 |
| Cursor `state.vscdb` | 51.4 GB | `disk-guard.sh` 每小时提醒 | 只报（Cursor 关着时 Owner 压缩） |
| 会话 scratchpad `/private/tmp/claude-501` | 3.35 GB（109 个目录） | macOS 自己清 `/private/tmp` | 不动 |
| 分支备份 `~/bifrost-backups/git-branches` | 104 MB（10-05、10-07、10-19、10-20） | 没有保留期 | 可自动清（R12，90 天） |
| 本地 Time Machine 快照 | 22 个 | `disk-guard.sh`：清扫后仍低于 15 GB 时瘦身 | 不动 |
| `npm` 缓存 `~/.npm` | 1.1 GB | — | 不动 |

## 6. 集群

| 对象 | 数量 | 细分 | 判定 |
|---|---|---|---|
| PipelineRun（`cicd`） | 305 | 最早 10-17；ci-platform 146、deliver-platform 67、deliver-platform-prod 30、apply-manifest 28、ci-finance 15、ci-frontend 10、deliver-stg 5、deliver-prod 4；成功 275、失败 30 | 现有 `tekton-pipelinerun-ttl` 每小时删 7 天前结束的；改保留期要 Owner（D-L7） |
| TaskRun | 3021 | 属于 PipelineRun 2546；单独 475：`github-sync-bifrost-trade-infra` 243、`github-sync-bifrost-platform` 102、`bifrost-gitea-mirror-sync` 61、`mirror-sync-frontend-dev` 38、`mirror-sync-market-data` 9、其他 22；单独的里 122 个超过 7 天（最早 06-17） | 单独的没人清：D-L7 |
| PVC | 284 | local-path 282、nfs-cold 2；属于 PipelineRun 277、属于 TaskRun 4（06-19 `bifrost-refresh-dockerfile-cms`）、无主 3（`gitea-data` 20Gi、`gitea`、`registry-data`）；请求 2Gi×150、5Gi×97、3Gi×25、10Gi×9 等，合计 950 Gi；PV 在 04 169 个、05 93 个、02 15 个、01 5 个 | 随 run 走；4 个旧的 D-L7；数据卷不动 |
| 发布记录 ConfigMap | 550 | `bifrost.io/release-record` | 不动 |
| 节点根盘可用（node-exporter） | — | 01 407 GB（87%）、02 132 GB（28%）、04 132 GB（28%）、05 227 GB（49%） | 告警只覆盖 .70、.75 低于 50 GB |
| CronJob（`cicd`） | 3 | `tekton-pipelinerun-ttl`（每小时 :20，上次 Complete）、`gitea-backup`、`bifrost-github-sync-reconcile` | — |

**没查到**：06 和两台 mini（Agent 登不上，没有主机指标）；local-path 卷在节点上的实际占用（要上节点 `du`）。

## 7. 完整清单（本会话 scratchpad，系统会在几天后清掉）

目录 `/private/tmp/claude-501/-Users-vision-mac-trader-Desktop-stocks/2cd0ed15-3d3f-481f-a041-73852856a881/scratchpad/`：

- `inv/rb_all.tsv` Gitea 分支（仓库、分支、类、前缀、日期、天数、main 没有的提交数、已合入、sha、标题）
- `inv/gh_all.tsv` GitHub 分支 · `inv/lb_class.tsv` 本地分支与判定 · `inv/wt_class.tsv` worktree 与判定
- `aw_full.tsv` `~/agent-work` 每一项（类、KB、node_modules KB、目录 mtime、最新文件时间、run.done、REPORT）
- `review_caches.tsv` 复核目录里的缓存子目录 · `inv/pvc.tsv`、`inv/pr.tsv` 集群对象
- 脚本：`inv_branches.sh`、`inv_wt_one.sh`、`du_one.sh`、`newest.sh`、`gen_inventory.py`（都只读）
