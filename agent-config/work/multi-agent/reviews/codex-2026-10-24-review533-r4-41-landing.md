# Review 533 — 4.1 自动落地切法复核

结论：先改。D4 A 的方向可以保留，但本稿还不能作为可签署、可直接实现的授权边界。主要阻断是：自动上 STG 后仍可取得 Gitea 管理员权限；禁止路径存在决定卡旁路；第三次落地失败走不到所写的卡住卡；退回链、发布重试和重启恢复没有闭合。

本次只读源码，未改被审仓库。版本核对：cut worktree HEAD 为 `047ea5ca04cf39407e550438a040aa44d9e56b87`；platform 的本地 `origin/main` 为 `82b3e9d798f098bbb2ce0bd4ed925892e116199e`。platform 代码均用 `git show origin/main:<path>` 读取，没有使用可能落后的工作树文件。

下文路径缩写：

- `CUT`：`/Users/vision-mac-trader/agent-work/r4-landing/agent-config/work/multi-agent/CUT-landing-2026-10-24.md`。
- `I/`：`/Users/vision-mac-trader/agent-work/r4-landing/`，infra 基线为 `639edc9`。
- `P/`：`/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/` 的上述 `origin/main` 对象，行号属于该对象。
- `LANES`：`/Users/vision-mac-trader/agent-work/r4-lanes/agent-config/work/multi-agent/DESIGN-release-lanes-2026-10-24.md`。

几个正确的部分应保留：`CUT:102-106` 先形成最终重放提交 R、再对 R 跑 CI、最后推同一个 R；这不是直接拿原 accepted 提交的 CI 放行。普通非强制 push 与 main 禁止强推能防止覆盖并发的人手提交，抢输应重放。现有 workers 清单确实是单副本、Recreate（`I/k8s/base-platform/manifest.yaml:83-108`），不应误报成普通滚动升级必然双控制器。platform 的 CI 也确实包含 code-health 和要求真实 PG/Redis 的测试（`I/k8s/cicd/tekton/pipeline-ci-platform.yaml:151-176,283-292`）。

## A — 按本稿实现会出错的地方

### A1 · 高：STG 自动执行的新代码可以拿到更强的凭证，“只有 Owner 批过的 PROD 代码能推 main”不成立

**位置**：`CUT:75,89-96,167,214`；`I/k8s/platform-rbac/10-stg.yaml:137-143`、`00-clusterroles.yaml:98-104`；`P/api/internal/delivery/service.go:1292-1306`。

STG 的 `bifrost-platform` SA 可以 GET `cicd/gitea-bootstrap`，代码明确把其中的 `gitea_admin_token` 当管理员凭证使用。自动落地的 Go 代码随后自动在 STG 的 API/workers 执行；它不需要读新建的 PROD lander Secret，已经可以读旧的管理员 Secret。故“PROD 要发布单”没有隔断这条提权路径。这个旧权限在扩大自动发布范围后成为设计前提上的缺口，不能用“原本就有”消除。

**最小修法**：把撤销 STG 对管理员凭证的访问列为 S2/S5 的前置条件，给其 Gitea 读取功能独立的只读身份；STG 演练写身份另设、不得进入 main/标签名单。保留 PROD lander Secret 仅挂 workers、git 子进程不执行仓库脚本的方案。验收必须覆盖 STG 程序身份、执行任务和 review 任务无法读取或间接使用 main 写权限，不能只测新 token 本身。线上实际绑定与令牌范围本次未核实。

### A2 · 高：预检失败的“合”按钮能够跳过不可绕过的底线

**位置**：`CUT:101,129,179,228`；`I/agent-config/CLAUDE.md:230-231`。

第 129 行把“禁止路径、超上限、依赖或迁移改动”统一变成推荐“合”的决定卡，并从第 3 步继续，跳过预检。第 179 行却说 `k8s/**`、治理、发布闸门等是规则也改不动的底线，S6 又要求即使规则允许也永不自动合。按前一条执行，Owner 点普通问题卡就能让 lander 推 infra PROD overlay，Argo 随即改 PROD；按后一条执行，卡承诺的“合”又不能兑现。现行规则还明确区分问题回答和动作审批。

**最小修法**：区分硬拒绝与可申请例外。硬底线只显示拒绝原因及正规发布/治理变更入口，不能由 landing 决定卡放行。若要支持软上限例外，定义独立、明确授权的单次审批，绑定 repo、accepted SHA、最终候选 SHA、规则版本、例外项及有效期；候选变化要失效。卡的推荐项不能把两种权限混在一起。

### A3 · 高：规则收紧没有在最后一道闸完整重算，规则换版还会遗失已排队的任务

**位置**：`CUT:100-105,174-181,208`；`P/api/internal/agentrt/rules/tighten.go:16-23`。

第 6 步只检查规则有效、仍含仓库、mission 未 stopped/paused。CI 跑着时把 `core` 改 false、增 deny、缩 allow/文件上限，仓库仍在，候选就仍可被推。`no_merge` 后加也未列入重查；STG 发版前同样没有明确重读 `stg_release: none`。`max_landings_per_day` 写进规则却没有计数、预留和最终核验步骤。

另一个问题是第 1 步把“收下时间不早于规则生效时间”直接绑定当前规则。正常发布第 2 版或收紧规则时 `effective_at` 更新为新的生效时间，上一版下已收下、尚未落地的任务可能全部被排除；这与只排除首次启用前的演练任务不是同一件事。

**最小修法**：在准备、推 main 前、起 STG 前分别按当前规则完整判定权限；推前在一次受锁保护的决策中处理当日额度。持久记录首次纳入自动落地的时间/规则身份，把历史演练截止线与每次规则换版分开。收紧后失去权限的在途任务应有明确暂停状态，恢复后按新规则重判。加入 CI 期间收紧 deny/core、撤销发布、换版仍保留排队任务的用例。

### A4 · 高：第三次失败调用 `failWork` 会报状态错误，卡住卡不会出现

**位置**：`CUT:121-125,210`；`P/api/internal/agentrt/store/kernel.go:132-143,180-192`。

落地只处理 accepted 任务，所以原任务、第一次和第二次修复任务在落地失败时都是 accepted。`failWork` 使用原来的 `taskMoves` 转到 blocked，而该表没有 accepted 的出边；第三次调用得到 `ErrState`。本稿明确选择 R3 来避免改状态机，不能同时借用一条不存在的状态转换。并且 `failWork` 会给执行者记工作失败，CI 基础设施或 main 竞争并不都应计入执行者成绩。

**最小修法**：为落地操作的终止失败创建独立、幂等的问题卡/issue，不改 accepted 任务状态；卡绑定根任务和退回次数，Owner 能选择停止或再试。若要复用 blocked 任务机制，应明确创建哪个非终态任务并在同一事务中阻塞它。补“连续三次落地失败只出现一张可操作卡”的测试。

### A5 · 高：R3 的替代关系没有接到依赖、关闭与清理，子任务落地后原链仍可能永久等待

**位置**：`CUT:100,123-127,129,150,192`；`P/api/internal/agentrt/store/prune.go:377-408`、`close.go:40-45`、`propose.go:754-777`。

例：B 依赖 A；A accepted 后冲突，生成 A′，A′ 改好并落地。A 的原 accepted 提交没有落地，`RecordLandings` 只查“原 task + 原 accepted commit”，不会把 A′ 当 A 的落地；第 1 步仍要求 B 的依赖 A 已落地，B 就卡住。`parent_task_id` 只说明来源，本稿没有定义依赖如何跟随替代结果。原尝试分支的保留期也不能靠“不改 RecordLandings”自然开始。

此外，“不合”记 declined 后，第 127 行只豁免 landed/returned，该任务仍可能让 mission 永远 active；反过来，returned 和新任务若分开写，关闭循环可能在两次写之间把 mission 关掉，子任务派不出去。

**最小修法**：定义根任务→当前替代任务→有效落地结果的解析规则，依赖和清理统一使用它，不能伪造“原 accepted 提交已进入 main”。创建替代任务、写 returned 关系、保住 mission active 必须同一事务且幂等。明确 declined 的关闭语义，以及规则撤销后的任务是否算完成。验收至少包括 A→B 依赖链、两层退回、拒绝合入、关闭循环并发。

### A6 · 高：CI 等待会盯住已经过时的 M0，且限速不等于有界恢复

**位置**：`CUT:104-105,115,193,201-206`。

候选 CI 失败，M0 的 CI 也红，于是一直等 M0；人手修好了 main 成为 M1，但“main 动了就重放”只在第 6 步，而第 5 步没有成功便到不了它。旧 M0 的失败记录不会因 M1 变绿而改变。M0 没有 run、运行中、查询失败也不能都解释为“main 红”。45 分钟没有 CI 只记 note 接着等；每小时六次后停一小时仍可无限循环，且早到的一件会占着仓库唯一在途位置。`merge_accepted.py list` 是被动审计，不是自动恢复。

**最小修法**：所有等待态每轮先检查 main、规则及任务终止条件；M0 过时立即废弃候选。把 Missing/Unknown/Running/Failed 分开处理，补跑 CI 有持久化的一次性标记。给整次落地定义总时限、重放总上限、下次重试时间和超时 issue；暂停一件后让后面的独立任务能被考察。旧 main 永红、新 main 已绿必须是验收用例。

### A7 · 高：STG 检查的是一个 SHA，流水线却可能构建另一个 SHA 和另一版 UI

**位置**：`CUT:140-141`；`P/api/internal/delivery/run_spec.go:25-42`；`I/k8s/cicd/tekton/pipeline-deliver-platform.yaml:15-23,48-70`；`pipeline-ci-platform.yaml:29-36`。

先读 main=M 并确认 M 的 CI 绿，再等窗口，最后用 `revision=main` 起流水线；等待期间的人手提交 N 会在 clone 时被取走，即使 N 的 CI 还没通过。接口确实接受 main，并没有自动固定成前面查过的 M。最终“落地提交是 deployed 的祖先”只证明包含历史，不证明所发头的 CI 通过。`uiRevision` 默认也为 main，CI 与构建可能使用不同 UI 提交。

**最小修法**：持到窗口后确定发布快照，固定 platform SHA 和独立的 UI SHA，把所用 CI、infra 闸门版本与发布记录关联；没有匹配证据就先补检查。向 delivery 传完整 SHA，检查 clone result、实际三类工作负载镜像摘要及启动结果。对“上次 STG→目标 SHA”的整个发布差异判定权限；批次中人手落地的变更不能因为其中有一件自动落地任务便自动取得授权。不能只检查当前任务的小 patch。

### A8 · 高：已进 main 的工作可能永远不上 STG，mission 却已经 done

**位置**：`CUT:127,140-142,187,227`。

发布要求整个仓库队列为空且最近一次落地已过五分钟。持续有新任务，或队尾一件卡 CI/窗口，就会让已经成功落地的工作长期不发布。最后一件的发布若失败，文档只等“下一次落地再发”；再没有新任务时，★ 验收永远不完成。按第 127 行关闭 mission 又只等 main，不等该 mission 承诺的 STG 结果，Owner 会看到已完成，但功能尚不可用。

**最小修法**：把“尚未验证上 STG 的最高落地提交”作为独立、可恢复的待发布记录；允许有界攒批，设置最长等待，不依赖落地队列清空。失败后针对该固定快照有界重试；超过上限保留失败状态与 issue，不靠新落地唤醒。发布型目标必须在 STG 核验后完成，或在 Console 明确分开“已合入”和“目标已交付”，不能把前者呈现成后者。

### A9 · 中高：现有窗口适配并非只换两个函数，释放权限和 4.3 的契约都缺项

**位置**：`CUT:105,115-116,141-143,258`；`P/api/internal/delivery/window_store.go:155-163,183-211`；`I/k8s/platform-rbac/00-clusterroles.yaml:83-104`、`20-prod.yaml:127-134`；`LANES:135-154,169-186`。

有三个具体问题：

1. 当前持锁用 who 判身份，固定 `agentrt-prod` 会让旧发布与重启后的新操作被视为同一持有者；有在跑 PipelineRun、续租失败、旧进程迟到释放时，不能仅凭 who 判断谁有权继续。发布 run 可以比 workers 存活更久。
2. 当前版本的仓库 RBAC 给平台 `configmaps` 的 create/update/patch，却没有 delete；现有释放函数执行 Delete。按这些清单运行，持有和续期可行，主动释放会失败，只能等 TTL。本稿“最后放窗口”缺实际接线。即使补 delete，当前删除不带 resourceVersion/UID 前提，过期读或迟到释放也可能删除刚续好的窗口。
3. 4.3 要按实际改动路径决定应用和共享资源，并传 token、session/fencing；`blocks(repo)`/`hold(app)` 表达不了这些。第 116 行第三次自己持应用窗口，第 105 行若仍按“该应用有窗口就挡”会挡住自己。4.3 的等待上限三十分钟回队列，也与本稿三十分钟仅记 note 不同。

**最小修法**：现在就约定带 operation ID、目标 SHA/路径、持有凭据的 acquire/check/renew/release 接口，全局窗口是它的第一版适配。释放使用条件更新使自己的窗口到期，或限定对象的 delete 权限加 CAS 前提；重启先认领/核对在跑的 run，再决定新建。把“读取窗口后、push 前有人取得窗口”的 TOCTOU 写清楚：仅两次读取不构成互斥；若要求严格不在发布中推 main，应让推送入口共用短时的最终推进锁，不必在整段 CI 期间占用全局窗口。4.3 的路径判定与自持锁豁免不能留到只改函数体时才发现。

### A10 · 中高：note 方案缺少外部副作用的幂等操作协议，重启可能重建、误退回或重复发布

**位置**：`CUT:103,106-107,123-124,186,192,207`；`P/api/internal/delivery/service.go:282-285,332-363`。

推 `land/**` 后才记 replay note，两个动作之间重启会留下没有记录的分支；重建提交会因提交时间等元数据不同得到另一 SHA，同一个 k 的分支不再能普通快进。main push 成功后，人手很快再推一个后继，`ls-remote == R` 会失败，但 R 实际已经落地；这应是对账，不应重放/退回。起 STG 的请求返回不确定时，直接下一轮再调用 delivery 默认会用新的时间戳 run 名，可能重复建 run。现有 `RecordLandings` 只补一条 landed，不能代替发布、额度、退回任务及分支清理的恢复。

**最小修法**：X3 可以继续选 note，但必须定义持久化 operation ID、准备/发送/不确定/已确认状态，以及按 repo 串行领取的事务规则。外部动作先存意图；同一次动作复用候选对象、稳定 run 身份和已记录请求，返回不确定先查结果。main 确认允许 R 是当前头的仍有效祖先；各轮 land 分支用 SHA 条件删除。复用 delivery 已有的 `CreateAttemptFrom` 身份机制。补每个“外部成功、记账之前”断点的恢复用例，不能只有一次 Pod 重启的笼统验收。

### A11 · 中：被 revert 的提交仍是祖先，会被误报为已在 STG 生效

**位置**：`CUT:100,141,192,211`；`P/api/internal/agentrt/store/prune.go:364-383`；`I/scripts/agentrt/merge_accepted.py:342-363`。

R 已落地后被人 revert 成 V；发布 V 时，R 仍是 V 的祖先。第 141 行因此会给已经撤销的功能写 `phase: stg`。原 landed note 永久保留、`RecordLandings` 跳过它，依赖判断也可能继续把撤销的能力视为可用。“不再自动重合”是对的，但还不够表达回滚后的当前状态。

**最小修法**：保留“曾经落地”的历史事实，另加 reverted/superseded 的当前结果。STG 核验和后继依赖需检查结果仍有效；可复用已有对标准 revert 的识别，不要以祖先关系替代。坏落地的最小操作手册应写明：停止该仓库后续落地/发布、在最新 main 上提交受检的 revert 或修复、按固定 SHA 重新发 STG；若 lander 自己不可用，由不依赖它的 Owner/既有发布入口恢复，禁止 reset/强推 main。PROD 恢复仍走原审批政策。

## B — Owner 签规则前还需要知道的取舍

### B1 · patch-id 只证明补丁形状；最终 CI 也不能证明原评审结论仍成立

`CUT:102,109,200` 应明确区分原 accepted commit A 与最终提交 R：评审证据原来绑定 A，CI 绑定 R；即使 patch-id 相同，也不能把 A 的语义评审自动改成“已评审 R”。

本目录离线探针 `probe_patch_identity.py` 用同一个补丁把 `value <= LIMIT` 改成 `value < LIMIT`；旧基线的 LIMIT=10，新基线在另一个文件里改成 100。两边 `git apply --check` 都通过，patch-id 同为 `4fdd2546e68fe08dd1c26759ff256b6fb2f5aa15`，已有的 permits(0) 检查都通过，但 permits(10) 从 false 变成 true。没有创建 Git 提交。证据在 `probe-data/result.json`。

签署时应二选一：M0 不等于原 base 时，为最终候选增加独立的集成复核；或明确接受“原补丁评审 + 最终完整 CI”的剩余语义风险，并限制首版改动范围。不能把 patch-id 当作前一种保障。若新增复核，检查后也不得再 amend、rebase 或重做提交；变了 SHA 就重走最终检查。

### B2 · X1–X5 的建议及隐藏工作量

| 选择 | 建议 | 签前需补齐 |
|---|---|---|
| X1 执行位置 | 保留 A，PROD workers；不把 main 凭证交同 UID 的 agentd | A1 的 STG/CI 凭证链必须先切断。git 独立干净 clone、禁 hooks/外部 filter/config、固定 remote；不在有 main 凭证的进程里运行候选测试。现有 `isolatedGit` 只禁全局/系统配置，不能把它的名字当作完整沙箱（`P/api/internal/agentd/workspace.go:389-392`）。|
| X2 退回 | R3 可以，不为此扩任务状态 CHECK | 必须补 A4/A5 的独立落地失败卡、替代关系和原子创建。它不是仅多一行任务的成本。|
| X3 状态 | note 可以做第一版 | 不建表不等于不要状态机；需唯一操作键、合法阶段、重放 reducer、原子额度/领取、外部结果对账。`landing` 不能只是任意 `kAny` 数据。|
| X4 STG 演练 | 保留只推 `land/stg/**` | 演练能测重放/CI，不能证明 PROD main 白名单、标签保护、真实 push 失败恢复有效。S4 必须另有真实身份的正反测试；STG 不得借旧管理员凭证完成“演练”。|
| X5 infra CI | 在扩展到 infra 前建 `bifrost-ci-infra` | 不只是加 YAML：要加入触发器、`isCIPipeline`、CI 事实索引、repo 输入/镜像预检和手工 `push-main.sh` 的 CI 名单。当前 `P/api/internal/delivery/ci_run.go:11-17,21-53`、`release_policy_facts.go:258-260`、`I/scripts/release/push-main.sh:117,472-481` 都只认旧三条流水线。漏接会永远等不到 infra 的绿灯。|

`Sources.Deployed("stg")` 的未核实项可以关闭一半：`P/api/internal/server/agentrt_sources.go:23-34,87-98,186-218` 确实读 platform lane 的 bifrost-platform SHA，并核对 API/workers/console 的镜像摘要；不是 Trade SHA。但它不是启动日志/功能探针检查，不能独自满足 `CUT:66` 的完整核验要求。workers 已有 delivery service，可调用 `StartPipelineRun`；窗口写函数目前是 delivery 包内函数/HTTP handler，仍需窄接口接线，见 A9。

### B3 · `landing:dev` 内容需要补成可判定的契约

`CUT:155-181,250` 中的样例还不能直接签。至少明确：

- `dev` 是 tenant，不是执行环境；本条由 PROD 控制器执行，STG 只能 dry-run，不能凭同名规则取得 main 权限。
- 首版建议 `core: false` 且用窄 allow。现有 core 名单只有 agentrt、agentd、cmd/agentd（`P/api/internal/agentrt/store/repos.go:84`）；实际信任边界还含 `api/cmd/platform-api`、server 接线、签名/授权/发布实现。仅一个 core 布尔值不足以描述所有自修改代码。
- migrations deny 不等于禁止 DDL：STG 的迁移 Job 用本次新 API 镜像执行 `platform-api agentrt-migrate`，并注入 `agentrt_owner_stg` 密码（`I/k8s/cicd/tekton/task-agentrt-migrate-stg.yaml:99-120`）；修改 Go 入口或迁移执行器也会以该身份运行，未必改 SQL 目录。Owner 要看见这项实际权限；首版应排除这些入口。
- glob 的 `**`、目录边界、大小写、根目录与任意层 `.env*` 的语义；rename 的旧/新路径、删除、符号链接和 submodule 如何计数和拒绝；二进制不能按 numstat 的 `-` 当零行。仅从 YAML 正则抽直接脚本名不足以证明 Tekton 间接 import/source 的文件都被覆盖。
- 三个上限按 tenant 还是 repo、UTC 日还是滑动 24 小时、成功/未知/重试如何计数；90 天是可选授权期限，不是验证结论。规则续期必须保留在途状态，过期停合也不应丢掉已发生副作用的对账。
- platform 与 infra 的 main 写权限必须分 S4/S6 发放；在 S4 不应提前拥有 infra 写权限。需要 Secret 挂载方式、可读主体、轮换与撤权步骤、HTTP 传输风险的明确说明。

“令牌泄露只能快进两个 main”（`CUT:91,213`）低估了后果：有 repo write 的身份还可能改删非保护分支，标签能否禁止取决于另建的标签保护（`I/scripts/gitea/protect-repo.sh:243-258`）。更关键的是，快进也能新增任意恶意代码、删除文件或改 infra 的 PROD overlay；路径、CI、额度限制是控制器逻辑，不是 Gitea token 的能力限制。泄露后不能只换 token，要核查泄露期间全部 ref/权限变更。角色与 token scope、CI clone 身份实际权限需用 Owner 的受控验收确认，本次没有读取任何 Secret。

### B4 · `push-main.sh` 替代范围应逐项写明，不能称为原门槛的完全等价实现

| 现有门槛 | 新方案评价 |
|---|---|
| 非强推、快进 | 保留；人手/另一落地先推进后，本候选拒绝即可，不能转 force。失败需区分 non-FF、权限拒绝和网络结果未知。|
| Change-Id + 会话血缘 | `Agentrt-Task` 替代会话尾注合理，但需验证它正好等于收下任务。不要只判断字符串存在。|
| 最终 SHA 的 CI | 保留，且禁止先 CI 后 amend；最终提交、CI run、所用闸门版本均应进审计。当前 `P/api/internal/delivery/release_policy_facts.go:241-244,298-302` 是“曾有任一成功就成功”，不是最近一次结果；旧成功、新失败或闸门版本变化时是否仍放行，须明定，不能误当成最新 CI 绿。|
| code-health | platform CI 已有，无须再在持有 main 凭证的 Pod 重跑；验收前补 TD-387 能更早反馈，但不能替代重放提交的 CI。CI 克隆的 infra main 是移动的，需记录实际基线版本；基线收紧后旧绿灯是否仍可用要规定。|
| 完整 go vet | 有缺口。push-main 运行 `go vet ./...`（`:375-376`），CI 只有 `go test ./...`（`pipeline-ci-platform.yaml:175-176`）；acceptance 的 vet 在原提交上。探针 `probe-vet` 中 go test 成功、go vet 因 self-assignment 失败，证明两者不同。最小改动是把完整 vet 加入候选的 CI，而不是在 lander 内跑测试。|
| infra 快测 | S6 应至少覆盖 push-main 的 release/agentrt/agent-host 快测加运行时检查，并统一清单；不要再维护两套逐渐漂移的列表。|
| 窗口 | 可抽共用判定，不能丢掉读失败即拒绝，也不能把“检查窗口”称为“持有互斥锁”。见 A9。|

上述 Go 探针只用了本机 Go 1.26.4、离线缓存与普通文件，没有网络、PG 或端口；它证明检查集合不等价，不声称已经在项目的 Go 1.25 CI 镜像重现。

### B5 · Owner 能看到什么、什么算“统筹线程零写入”

`CUT:186-188` 的任务状态行有用，但还应能查看原 accepted SHA、实际 landed SHA、base、规则版本/例外审批、具体 CI、退回链、待发布/发布失败/已撤销、下一次重试时间。长期 waiting 必须有主动 issue/卡；不能只有必须点进 mission 才能看到的 note。STG 发布结果应有具体 run 与镜像摘要证据。

`Landed-By` 是提交文本，任何提交者都可写；只数它不是可信自动落地占比。只数 `bifrost-mbp` 推送也漏掉其他人手身份及手工创建的 run。★ 验收应以一个明确 mission 的完整事件链为准：Owner 输入目标 → 提案授权 → 实现/检查/评审 → runtime 落地操作及 Gitea 推送主体 → CI → STG run/实际镜像；记录整个窗口内协调线程所有写动作。能否取得 Gitea 推送主体，本稿自己也尚未实测（`:261`），应作为验收前置，不能等数指标时才补。

### B6 · 有更便宜的第一片

先只开放 platform 的一小块 Console 文案/纯展示组件，`core:false`，排除 API、授权/发布、迁移、依赖和构建入口；一个 repo、一个在途操作、一个小目标。继续用 PROD workers + note，不新增表，不接 infra，也暂不实现通用的多层落地修复任务。

仍须保留：精确候选 SHA 的 CI/完整 vet、最后权限复查、受限凭证、固定 SHA 的 STG 发布、持久化重试/对账、终止失败可见。冲突或检查失败先变成明确的落地 issue，成功路径自动到 STG；完成一个小目标的 ★ 后再扩 R3 自动修复与 infra。若 Owner 要求首次切片连失败修复也全程无人值守，则不能省 A4/A5；需要明确接受相应实现成本。S1/S2 单独的只读/演练结果不算 ★。

## C — 次要

1. `CUT:115` 的“第 4 轮之前”与文档已属第 4 轮冲突，应写“4.3 / D2 上线之前”，避免按轮数误开新锁策略。
2. `CUT:224` 使用 `would_land`，但 `:186` 的封闭 phase 列表没有它；将 dry-run 作为字段或补合法 phase，且永不参与真实 landed/自动占比统计。
3. `CUT:102` 沿用 `merge_accepted.py:410-445` 的消息生成，会保留“Until the release queue, the coordinator merges…”并给每个结果追加 TD-383。自动落地应改成事实正确的来源描述，保留原 Work/Change-Id，不把所有业务提交永久挂到这条技术债。
4. BRIEF 中 `agent-config/scripts/agentrt/merge_accepted.py` 路径不存在；实际文件为 `I/scripts/agentrt/merge_accepted.py`，CUT 第 34 行使用的是正确路径。

## 核验范围与限制

已完成版本、源码、清单和规则的离线交叉核对；运行了两个本目录探针。patch-id 探针通过；Go 探针的预期结果为 test 成功、完整 vet 失败。未运行项目全量构建/测试，也没有为尚未实现的 Land 循环声称测试通过。

按 BRIEF 限制，未联网、未用 MCP/SSH、未访问集群或数据库、未启动 PostgreSQL、未绑定端口、未提交 Git。无法核实在线 Secret 内容/令牌 scope、实际 RBAC 与分支/标签保护是否符合仓库清单、Gitea 推送审计查询能力、真实 CI 钩子及延迟、跨 Pod 重启与网络不确定返回的行为、STG/PROD 实际部署状态。CUT 引用的线上统计只作为该文档的历史事实，未冒充本次实测。所有产物仅在当前复核目录，Go 缓存使用指定共享缓存；没有修改技术债台账或被审设计。

先改

END OF REPORT
