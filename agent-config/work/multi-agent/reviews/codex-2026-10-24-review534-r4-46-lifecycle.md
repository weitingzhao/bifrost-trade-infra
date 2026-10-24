**Review 534 — W-31 第 4 轮 4.6，只读复核**

结论：先改。盘点有价值，R1 已有的交接保护也有代码支撑；但“可自动清”尚不能作为删除授权。实际样本中存在不在任何远端分支上的 detached 提交，以及只由待删 worktree 的 reflog 保存的历史。自动清理还会遇到缓存误认、并发写入和备份覆盖问题。D-L5 可以处理已确认的历史演练，但不能代替 4.1 对当前计划有效性的检查。

审查基线：infra worktree `/Users/vision-mac-trader/agent-work/r4-lifecycle`，HEAD 确认为 `2d7958346101e75535d4ef6866e1f6211e6cf450`；platform 代码均通过 `git show origin/main:<path>` 读取，本地 `origin/main` 为 `82b3e9d798f098bbb2ce0bd4ed925892e116199e`。4.1 对照稿位于 `r4-landing`，HEAD 为 `047ea5ca04cf`。本次本地检查在 2026-10-24 00:10 CDT 起进行。

文中 `CUT` 指 [CUT-lifecycle-2026-10-24.md](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md)，`INV` 指同目录的 [INVENTORY-lifecycle-2026-10-24.md](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md)，`LAND` 指 [CUT-landing-2026-10-24.md](/Users/vision-mac-trader/agent-work/r4-landing/agent-config/work/multi-agent/CUT-landing-2026-10-24.md)。infra 代码行号以审查 worktree 为准，platform 行号以以上 `origin/main` 为准。`AW` = `~/agent-work`，`WS` = `~/Desktop/stocks`。

**A：必须先修的丢失工作风险（7 项）**

**A1．“同 Change-Id / 同标题”不能证明原提交可恢复；库存已经把无远端副本的 detached HEAD 算进可清。**

位置：[CUT:77](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:77)、CUT:80、95、100、170；[INV:5](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:5)、INV:160、268。

实测 `AW/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-platform` 的 HEAD 是 `8d5135fdf9d3`：status 空，`branch -r --contains HEAD` 空，`for-each-ref --contains HEAD` 也空；它不是 `origin/main` 祖先，`git cherry origin/main HEAD` 有一条 `+`。main 上的 `710074d70654` 与它同 Change-Id，但 patch-id 分别为 `8432b57d…`、`9f4c1898…`，两个树相差测试文件拆分。提交说明证实 main 接收的是拆分后的版本。因此“这件活已落地”成立，“这个 HEAD 原样可从 main 恢复”不成立。`merge_accepted.py:485–503` 本来就会在 detached checkout 上 cherry-pick、amend；不能像 R11 那样认定这个工具留下的 checkout 都是 main 的祖先。

当前 `prune-merged-branches.sh:163–170` 只打包待删分支 refs，没有打包仅由 worktree HEAD 保有的提交。照新规则删该目录，只记 SHA，之后对象 GC 即无法恢复。另抽查库存中 110 条“可自动清、但原快照 local_only > 0”的本地分支，13 条仍有 `git cherry` 的 `+` 提交；其中 infra 的 `td-lane-aa-2026-10-04` 依赖同标题匹配。这里不把 patch 等价或已审阅的拆分称为功能丢失，但它们绝不是原对象仍有副本的证明。

最小修改：将“工作已合入”和“原对象有可恢复副本”分开记录。自动删除至少要求确切提交被一个**不在本轮删除集合内**的持久 ref 包含，或该确切 HEAD 及其完整历史已进入验证过的归档。Change-Id、标题只作人工定位线索；有 `+`、合并提交特有改动、读取失败时不得据此判安全。detached HEAD 必须纳入备份，不能只记字符串。重新生成受此判据影响的 295 / 437 / 130 三组数量。

**A2．只检查当前 HEAD，漏掉删除 worktree 时一起消失的 reflog。**

位置：[CUT:80](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:80)、CUT:94–96、170、188；[INV:210](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:210)、INV:278–280。

25 个可清样本中，10 个的 HEAD reflog 含有现存 refs 不可达的提交。例如 `AW/w31-25-release/bifrost-platform` 当前 HEAD `19b3a253f2a3` 确实在 main，但旧提交 `95ba98d4d04760e6933c7d1ab06569c73df16077` 没有 ref 包含；逐文件查到它仅出现在 `.git/worktrees/bifrost-platform68/logs/HEAD`。`td384/bifrost-platform` 的同类历史有 19 个，`blocked-card/bifrost-platform` 有 11 个。删当前 worktree 会删它的管理目录及 HEAD reflog；给当前分支头打 bundle 不会自动包含这些旁支历史。

最小修改：删除前盘点 worktree HEAD reflog 和待删 branch reflog；未被保留 refs/归档覆盖的对象先建立归档引用并打包验证，否则只报。登记“工作结束”不等于可以丢弃历史草稿。验收加入“HEAD 已进 main、旧提交只在该 worktree reflog”的反例，并确认恢复命令能恢复旧提交。

**A3．R2 的自动放弃与 D-L5 没有保住原对象；“记 SHA”“标记可撤”不是回退。**

位置：[CUT:91](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:91)、CUT:172–174、191、222；[INV:34](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:34)、INV:59、62–64。

代码 `api/internal/agentd/prune.go:126–155` 在一个空 bare 仓库执行带 SHA lease 的删除，没有 fetch/bundle 备份。平台的删除记录是任务、ref、commit 和原因，不是 Git 对象备份。实测库存中拟自动清的 STG M-1/a1（`bce320adea8b`）、STG M-13/a1（`96afc753b359`）、PROD M-14/a1、a2（`0e63738b501a`、`b3757a74879a`）、infra PROD M-9/a1（`d4c00c5b795c`）都有 `git cherry +`，在本地远端引用里仅各自的 `origin/agent/...` 包含它。STG M-27 Q07 的 a1、a2 也各有独立提交；库存尚未明确哪一个是被取代的尝试。不能从“任务取消/被取代”推出“代码另有副本”。

新增“没有记录 pushed_commit，7 天后按放弃删”还会移除 `store/prune.go:204–205` 的关键保护：现在只有任务、仓库、attempt、ref、commit 全部对应才可清。若推送成功但上报失败，或同名分支后来被写入别的工作，终态和名字无法证明应放弃的是该分支当前内容。

D-L5 的时间也写错了：`store/prune.go:225–227` 对 `no_merge` 从 **accepted 事件**计时，不从新增标记计时。这里的任务早已满 24 小时，标记后下一轮就可能进入删除，不能承诺再等 24 小时。原对象删掉以后，撤回 `no_merge` 不会使它复活。

最小修改：删除唯一 ref 前，明确并验证完整 Git 对象的持久归档，记录归档位置、校验值和恢复 ref；仅 SHA 不算。缺 pushed_commit 的条目继续只报，先补全交接证据及确切对象身份，再讨论放弃。D-L5 先列 env、mission、task、accepted attempt、SHA、放弃理由、归档位置，归档完成后再标记，并如实说明可能立即进入清理。已上 main 且能证明原对象保留的分支可走较短路径。

**A4．缓存名单按名字决定可删除，会把未提交材料当作缓存；普通 status 还漏 ignored 文件。**

位置：[CUT:78](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:78)、CUT:97–99、120–121、128、187；[INV:19](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:19)、INV:210、342。

`cache`、`.cache`、`tmp`、`.venv` 和名字含空格或 `=` 都不是内容类型。实查共享 `.cache` 内有 `api-new.go`、`pools-new.go`、`cut25.md` 和多处草稿；库存自己也承认这种用法。R9 对这处共享目录有例外，但 §4.1 把同一名字名单推广到所有复核、lane、worktree，没有证明别处同名目录全可生成。若一个停止复核把手写探针或未提交补丁放进 `tmp/`，24 小时后会直接删；一个合法草稿目录包含空格也会被 R9 命中。

此外，`git status --porcelain` 空不表示没有未归档的 ignored 文件。常规 `git worktree remove` 不加 force 也不是 ignored 文件备份机制。当前样本里看到了 ignored 的构建产物；没有宣称其中存在丢失的私密文件，但现有判据无法区分缓存和 ignored 的手写材料。先删“生成文件”再做非 force remove 会先发生不可逆损失。

最小修改：只有创建工具登记的具体 cache root 和用途，或经类型检查确认的历史缓存，才允许删。名字仅用于发现候选；对空格/`=` 禁止通配删除，已知错误目录也先验格式和占用。全量列出 untracked 与 ignored，未分类项只报；不跟随软链接或跨出登记根。S1/S2 测试加入同名目录中的手写文件、ignored 材料、普通带空格目录和嵌套 Git 仓库，要求保留。

**A5．R11 把有未提交删除的目录列为可清，依据只是对系统清理的猜测。**

位置：[CUT:100](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:100)、CUT:170、188；[INV:236](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:236)。

复跑 `$TMPDIR/push-main.XrTZfq/bifrost-trade-infra`：HEAD `bf132671786d` 在 main，status 确有 12 条 tracked 删除。没有证据证明这些删除都是 macOS 造成的，而不是未提交工作。当前写法承诺 S2 后把它算进自动清理，与“有未提交改动只报”和“不加 --force”相冲突。名字叫 push-main、目录超过一天，均不能判断未提交改动是否可放弃。

最小修改：R11 与 R5 使用完全相同的内容、占用、reflog 和备份门槛，取消 dirty 例外；这个具体条目继续只报，除非完整归档了差异及所有未跟踪材料，或得到针对这些内容的放弃决定。不要为了让 S2 的“残留被删”测试通过而加 force。

**A6．“24 小时没写 + 没进程 cwd”不是会话终止证明；检查到删除之间也没有保护。**

位置：[CUT:78](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:78)、CUT:92、94、97、100、138–144、150；[INV:210](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:210)。

会话可以在 workspace 根运行、经绝对路径访问 worktree；IDE 可以保留打开的文件，Agent 也可能等用户一天再继续。此时 cwd 和 mtime 都不证明它已结束。`ends_when=merged`、`until:<日期>` 也不能代替活动租约。现有盘点的 find 仅到深度 4，深层文件的原地编辑不会更新祖先目录 mtime；“24 小时内没有文件改动”的结论比实测范围更强。

删除动作还有实质竞争：`prune-merged-branches.sh:168–170` 备份后，`:186`、`:199` 用普通 `push --delete`，没有绑定备份 SHA。若另一会话在中间把分支推到新提交，脚本会删除未备份的新头；重试也一样。`:227` 的 `branch -D` 同样没有 old-SHA 条件。分支头的 committerdate 只说明提交时间，不能证明这个分支 24 小时没被使用。agentd 的 SHA lease 正确，但没有被用于这里。

最小修改：把任务/会话活动状态与清理放在同一租约或互斥协议中，删除前重新检查身份、HEAD、dirty、占用和归档。历史目录不能证明停用时只报。递归检查需完整，读取/lsof 失败必须保留。远端删除使用明确 `ref:expectedSHA` 的 lease，重试不得刷新为未经备份的新头；本地删除使用 expected-old 的原子比较，并保留 worktree 占用检查。增加“检查后发生 commit/push/恢复会话”的反例。

**A7．每小时运行会覆盖同一天的 bundle；90 天到期还会删掉已放弃分支的最后副本。**

位置：[CUT:80](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:80)、CUT:101、132、150、188、219；[INV:368](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md:368)。

脚本 `scripts/prune-merged-branches.sh:73` 仅取日期，`:169–170` 每次重写同一个 `<日期>/<repo>.refs.tsv` 和 bundle。以前人工低频跑也有问题，改成每小时跑会稳定放大：上午删 A 并归档，下午删 B 覆盖上午文件；A 若仅是同 Change-Id、或按 D-L2 放弃，随后就没有承诺的恢复包。验证第二个 bundle 成功不能证明第一个还在。

即使修了覆盖，D-L2 本来允许归档未合并结果，R12 又不分内容地删除 90 天前全部备份，90 天后最后副本仍会消失。当前实查四个日期目录均未满 90 天，抽验两个旧 bundle 可通过 `git bundle verify`；这不能证明未来保留规则安全。

最小修改：按机器、仓库、唯一 run ID 保存不可覆盖的包和清单，归档成功后才删除，运行间互斥。区分“已在持久保留 refs 上的冗余恢复包”和“独有工作/审计材料归档”；90 天只能清前者。后者先迁到验证过的持久存储，或另有明确的不可恢复放弃决定。S2 加入同日两轮不同删除集、独有提交超过 90 天仍能恢复的验收。

**B：D-L1 至 D-L7 与 4.1 的决定**

| 决定 | 是否需要 | 对推荐的判断与最小调整 |
|---|---|---|
| D-L1（CUT:218） | 需要确定谁负责远端分支清理。 | 倾向 A，才能满足零手工清理；但必须先修 A1、A6、A7，清理范围需显式区分 `agent/**`、人的分支、4.1 的 `land/**`。不能把当前脚本原样挂定时器。 |
| D-L2（CUT:219） | 需要决定未合并成果的保留用途。 | A 仅在归档是持久的、查引用覆盖实际台账和活跃会话时成立。30 天与“没搜到引用”不等于内容无价值。当前 12 条只有约 2–14 天历史，不应以未来 30 天规则直接批量淘汰。保留的材料应有明确 hold/归档理由，否则数量目标无法解释。 |
| D-L3（CUT:220） | 需要决定公开历史分支迁移与删除。 | 先保全再删的顺序正确。迁移按 SHA/可达性验收，不能只看 Gitea 是否有同名分支。本次离线重算 157 个 GitHub 快照分支头，38 个确切头不被当时 Gitea heads 覆盖：16 个属于文档列出的未合入独有分支，另 22 个被按 patch/Change-Id/标题算作已合入。不是说这 22 个功能都未落地，而是删除全部远端和本地副本前也要保全原对象。凭证和现时远端状态未核验。 |
| D-L4（CUT:221） | 需要决定记录的长期存储位置；30 天不是正确性的必要阈值。 | A 可降低本机占用，但“NAS 中保持相对路径，原引用还能找到”不成立：台账引用的是 `~/agent-work/codex-review-…/REPORT.md`，打包后该路径会失效。先建立可读的稳定索引/跳转或改引用，归档须校验、试读；有引用、hold 标记、归档失败的一律保留。抽查 TECH_DEBT:2847、2861、2874、2916 所引用的 268、277、278、286、288、290、292–294 等报告，本机均存在，reviews 目录未找到同编号归档。NAS 未访问，不能断言已有可用副本。 |
| D-L5（CUT:222） | 需要处置已确认的历史演练和不再落地的成果；不是启用 4.1 的唯一前置办法。 | 逐项确认属于演练/明确放弃后，标 `no_merge` 有意义；“20 条一律标”不能仅凭远端库存决定。`no_merge` 存在 mission scope，影响该 mission 的所有任务；应按环境和 mission 汇总核对，不能按分支条数机械写。先完成 A3 的保全，纠正立即可清的时间语义；还必须增加下文 B1 的持续闸门。 |
| D-L6（CUT:223） | 需要决定非 agentd 主机的上报路径；跨 Mac/mini 的一致性确有需求。 | 推荐 A 合理，可以复用平台指标和权限边界。应一次决定接口的身份、机器/卷标识、采样时间、失效处理与安装方式，而不是先选 A、实现中再补关键条件。platform 当前 `store/hostdisk.go:55–112` 只保存阈值跨越事件，不能把它当作持续的最新磁盘读数。新指标需保存最近样本并显式表示未观测/过期。 |
| D-L7（CUT:224） | 保留政策已由 Owner 于 10-10 决定，没必要把同一政策再作为开放选项；本次具体 cicd 写入仍需批准。 | A 与既有决定一致。实现须仅删终态对象，按真实 ownerReference 级联 PVC，保留数据卷；发布证据应匹配该 run/repo/SHA。现 Role 没有读 ConfigMap 权限，若通过 release-record 判断必须一起补最小权限。原 pass 2 仍会在两天后删失败 run 的 Pod，需说明“失败保留 7 天”是否也包括日志可访问性，并相应改 pass 2。 |

**B1．D-L5 不足以挡住“新的 accepted，已经过时的工作”。这是 4.1 的上线阻断项。**

位置：CUT:109、222；LAND:100–105；platform `api/internal/agentrt/store/planchange.go:540–570`。

4.1 草案已经要求 `accepted_at >= effective_at`，所以不是完全没有历史屏障。应让两个 cut 统一为：生效前结果默认不自动落地，历史 `no_merge` 用于解释与清理，而不是二选一、仅靠这 20 个分支兜住所有历史。运行时任务全集也不能由尚存在的远端分支全集替代。

另一个能从现有代码直接推导的失效路径是：规则生效后任务被收下 → Owner 撤掉其计划步骤 → 任务仍是 accepted、mission 仍是 active/done → 4.1 仍将它入队。`dropStep` 明确把 accepted 排除在 unfinished 之外，只把 plan_node 改为 dropped，不改该任务。LAND:100 只检查任务、mission、时间、落地 note 和依赖，没有检查所属步骤是否已撤销。它即使 cherry-pick 无冲突、patch-id 相同、CI 全绿，也是在落地已经被撤销的工作。删除旧 20 条对此毫无帮助。

还存在入队后变化：CI 等待期间新增 `no_merge` 或撤掉步骤，LAND:105 只写了 mission stopped/paused、规则、窗口和 main 头的复查，没有重复完整的落地资格检查。以及人手落地后很快 revert、早于 RecordLandings 观察：没有 landed note 不等于从未落地；现 `merge_accepted.py:464–466` 还丢弃了 `landed()` 返回的“曾落地后被撤销”理由。不能把这种任务再自动恢复成旧补丁。

最小修改：入队与最后推送前共用一条资格判定，绑定环境、mission scope、任务/accepted attempt/SHA、计划步骤及版本；dropped/被取代、不再绑定到有效计划的结果停止自动落地并记原因。`no_merge`、returned/declined、人工撤销在推送前重查；已 revert 的成果需新的显式落地决定。计划变更与最终落地需有版本比较/互斥顺序，不能仅靠一次读取。验收至少包括：生效后 accepted 再 drop_step；CI 期间改 no_merge；人手合入并 revert 尚未写 landed note。均不能推 main。

**B2．本地清扫命令会同时删远端，当前切片没有隔离 D-L1。**

位置：CUT:124、150、165–171、187–189。它把 `prune-merged-branches.sh --apply --local` 叫作“本地部分”，但脚本参数说明及 `:177–227` 表明 `--local` 是“额外清本地”，远端删除始终执行。D-L1 尚未批准时，S1/S2/S7 就可能触发远端清理。最小修改是增加真正互斥的 `--local-only` / `--remote-only`，让定时配置按已定权限显式启用；两种模式分别验证不会触达另一侧。S7 也应依赖 S3 登记接线，不能只要求 S1/S2 合入就开始清理历史目录。

**B3．当前验收能掩盖持续增长，且只给 Mac 设了完整基线。**

位置：CUT:8–9、196–206。Mac 357 GB 是清理前基线；一次腾出约 26 GB 后，即使这一周又吃掉约 36 GB，仍可能满足“不低于基线减 10 GB”。人的分支也允许回涨到清理前 80 的总背景，`land/**` 没有单独计数；跨主机移走资料会让 Mac 变小、总量仍变大。

最小修改：S7 后立即建立每台 Agent 主机的基线，区分活动工作、可再生成缓存、待处置独有材料和持久归档；七天每天记录用量及各类分支净变化、自动处理/拒绝数、人工处理数。容许的短期缓存波动要有上限及期末回落条件，不能用一次性清理的收益抵消新的增长。把 4.1 的在途/失败 `land/**`、06 遗留目录、未来 mini 同时纳入；未观测的机器不得算通过。

**B4．停派闸门依赖每小时旧状态，可能在磁盘已经不足时继续派活。**

位置：CUT:119、123、150、156–159、190。清扫后才写 JSON，30 GB 以下仅提示、15 GB 以下才拦；旧脚本 `disk-guard.sh:5–7、40–41` 原本规定低于 30 GB 就不发新复核/npm ci。新稿无解释地放宽了这一层。几个并发构建可在一小时内吃完旧样本的余量；文件缺失、格式坏或来自上一台机器也未定义。

最小修改：派活入口实时读取目标卷余量，或要求非常短时效的有效样本；未知/过期明确停新活并报告原因。保持已定的 30/15 GiB 分级语义，若要改另列决定；明确并发预算。监控的 15 分钟无报告告警与每小时上报需按主机类型匹配，Mac 睡眠的无数据也不能被表示成“磁盘充足”。

**C：较小的事实与表述修正**

1. CUT:108 把保留 `Agentrt-Task` 说成足够。`api/internal/lineage/mainresults.go:55–69` 实际按 task 加原结果 SHA 查找：cherry-pick 后还需要 `(cherry picked from commit <原 SHA>)` 行。LAND 已沿用消息改写规则，应在两份 cut 中写全，否则会出现功能已合入而分支永远不清。Change-Id 被手工合入改掉是观测到的一次事件，不是所有 cherry-pick 的必然行为。
2. INV:378 的无主 PVC 名字写成 `gitea`；保存的原始 `pvc.json` 是 `gitea-backup`、`gitea-data`、`registry-data`。三者都应保留，修正名字以免后续按名称造清单。保存的快照可复算 305 PipelineRun、3021 TaskRun、475 个 standalone TaskRun、284 PVC，和主要统计一致；这是旧快照复算，不是本次集群实查。
3. CUT:8 的“磁盘余量……不涨”方向与目标相反，应是“磁盘占用不持续增长/余量不持续下降”。统一 GB/GiB，避免 `df -g`、Go 的 `15 << 30` 和表格相互混用。
4. INV:385–393 的完整库存只放在自动清理的 scratchpad，后续重跑不能重现本次分类依据。应把脱敏的原始清单、命令、时间、输入 refs 和分类规则版本留作本次证据；不必保留庞大的缓存。当前审查已保存抽查结果到本目录。

**抽查记录与覆盖范围**

本次没有运行任何清扫脚本，即使它标称 dry-run 也没有运行：现 prune 脚本会 fetch/prune 并写临时文件。自行调用只读命令，设 `GIT_OPTIONAL_LOCKS=0`、`GIT_NO_LAZY_FETCH=1`，不 fetch、不 ls-remote、不访问 API。

每个抽查 worktree 重跑 `git status --porcelain`、`git branch -r --contains HEAD`、`git cherry origin/main HEAD`、祖先检查、`git stash list`；各本机仓库另跑 `git log --branches --not --remotes`。补查 ignored 文件、HEAD reflog、其对象对 refs 的可达性、worktree locked、mtime 和 `lsof -d cwd`。远端可达性用原盘点已保存的 heads SHA 重新计算，**仅能证明原快照**；本地 tracking refs 也不代表现时远端。

完整输出见 [readonly-evidence.json](./readonly-evidence.json)、[branch-evidence.json](./branch-evidence.json)、[semantic-evidence.json](./semantic-evidence.json)，对应只读程序为 [audit_readonly.py](./audit_readonly.py)、[audit_branches_readonly.py](./audit_branches_readonly.py)。共检查 50 个 worktree：25 个可自动清、21 个只报不删（全部）、3 个暂留、1 个本线；另核对 80 个 Gitea 快照分支、157 个 GitHub 快照分支和 147 条本地分支（110 条可清但有原始独有提交，37 条只报）。这不等于批准这些对象删除。

以下 25 条是库存中“可自动清”的实际样本。`status` 为原始输出行数；`reflog 独有` 指当前 refs 不可达、但该 worktree HEAD reflog 可达的提交数，不等于新增功能数。所有这些样本当次浅层 mtime 检查无近期项、无匹配 cwd、无 locked；仍有上述证明范围与竞争限制。

| 库存候选路径 | 实测 HEAD | status | main / 远端检查 | reflog 独有 |
|---|---|---:|---|---:|
| `AW/td-172-142-research` | `16f784143d48` | 0 | 非祖先；cherry 全为 `-` | 0 |
| `AW/td-92-94-research` | `d628fa6bd913` | 0 | 非祖先；cherry 全为 `-` | 0 |
| `AW/w31-23-t12/bifrost-platform` | `afb8e27ce2b8` | 0 | main 祖先 | 0 |
| `AW/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-platform` | `93e2bd70f968` | 0 | main 祖先 | 2 |
| `AW/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-platform` | `8d5135fdf9d3` | 0 | 非祖先；1 条 `+`；无远端包含 | 2 |
| `WS/bifrost-platform-phase3-s4` | `2e86b38d54c3` | 0 | main 祖先 | 1 |
| `WS/bifrost-platform-phase3-s3` | `c5eee58e5e22` | 0 | main 祖先 | 0 |
| `WS/bifrost-platform-phase3-s5` | `4949b92a45ff` | 0 | main 祖先 | 0 |
| `AW/w31-td415/platform` | `309c7fa948af` | 0 | 非祖先；cherry 全为 `-` | 3 |
| `AW/td-411-schema/bifrost-platform` | `75022097b012` | 0 | main 祖先 | 0 |
| `AW/guard-1a/bifrost-platform` | `fb1bd6f74cb3` | 0 | main 祖先 | 0 |
| `AW/blocked-card/bifrost-platform` | `39fa7813f048` | 0 | main 祖先 | 11 |
| `AW/merge-accepted/t_01M5D3K2YYDHJ4JWBBQXKEMFF0/bifrost-ui` | `c83f40b40e65` | 0 | main 祖先 | 0 |
| `AW/merge-accepted/t_01M5FV0BVYGD02MZNXJN6YGKY5/bifrost-ui` | `c83f40b40e65` | 0 | main 祖先 | 0 |
| `AW/td384/bifrost-platform` | `4536e62734a9` | 0 | main 祖先 | 19 |
| `AW/w31-25-g2/bifrost-platform` | `cc8d8c51b45d` | 0 | main 祖先 | 8 |
| `AW/w31-25-release/bifrost-platform` | `19b3a253f2a3` | 0 | main 祖先 | 1 |
| `AW/td-310/bifrost-platform` | `66585501d0a1` | 0 | 4 条 `+`；由 `origin/w31/td-310-anchor` 包含 | 0 |
| `AW/td-306-307/bifrost-platform` | `cf15298ff1df` | 0 | main 祖先 | 0 |
| `AW/w65-integration/bifrost-platform` | `6524330d9269` | 0 | main 祖先 | 3 |
| `WS/.worktrees/w32-platform` | `d917f162094e` | 2 | main 祖先；两项未跟踪 node_modules | 0 |
| `WS/.worktrees/w33c-platform` | `61d859567716` | 0 | main 祖先 | 3 |
| `WS/.worktrees/w32-report` | `262e81b74b98` | 0 | main 祖先 | 0 |
| `WS/.worktrees/w33c-report` | `e2101e05e7a5` | 0 | main 祖先 | 0 |
| `WS/.worktrees/w32-infra` | `07d19dd1eeb0` | 0 | 非祖先；cherry 全为 `-` | 0 |

逐类覆盖及反例：

| 库存/规则类别 | 本次核验与边界 |
|---|---|
| R1 agentd 工作区 | 读 `disk.go:132–145`、`deliver.go:562–578、749–757`：要求 HandedOver，先确认进程组清除；不完整 checkpoint 不应清。此处比 CUT 的简写严格，保留实现约束。未观察 06 实机。 |
| R2 agent 分支 | 27 条快照全部重算 Git 可达性；上述 7 条待清涉及 8 个候选 heads，因为 M-27 哪个 attempt 被收下尚不明确。缺实时 verification/pushed_ref/prune 事件，不能宣称 7 条都已满足代码条件。 |
| R3 人的远端分支 | 53 条快照全部重跑 cherry/祖先检查，覆盖已合入过期、未合入、不到 24 小时三类。原快照中 41 条按旧算法合入、12 条未合入；当前实时分支/PR 未查。 |
| R4 GitHub | 157 个快照头全部重算；确认不能以 16 个名字覆盖所有原对象的保全要求。没有读取凭证或访问 GitHub。 |
| R5–R7 本地工作树/分支/根目录 | 覆盖上述 25 可清、全部 21 只报及活跃类。`td-337` 实见 6 处 tracked 修改及手写 quiet 文件；`chief-exam-s5`、`gate-a-t33` 有手写 untracked，继续保留。`codex-ops-ui`、`rules-symbols` 当次分别有 4、5 个 cwd 匹配。`r4-lifecycle` 自身仍有只在本地的提交，应保留。 |
| stash、tag、独立 clone | 12 个 WS 真仓库及 `AW/bifrost-finance` 的 stash list 当次均空；WS 仓库未发现仅 tags 可达、branches/remotes 均不可达的提交。**这不证明所有 tag 已推送**，也不证明可删 tag；未联网核验远端 tags。R5/R6 删除 worktree/branch 不应触碰共享 refs/stash、refs/tags。finance 是独立 clone，status/local-only/stash 检查为空，但其 gitignored 私有数据不在此次内容审查范围，不能按 R10 删整个 clone。 |
| R8 复核缓存与记录 | 原快照 35 个缓存子目录，覆盖 Go 各种命名、tmp、node_modules；实查 107/go-cache、436/cache 具有 Go 分桶形状，506/tmp 仍有临时内容。抽验有/无 run.done、有台账引用、无仓库同编号副本的记录。不能据目录名给所有内容发删除许可。 |
| R9 共享缓存 | 实查错误名字目录存在，且 `.cache` 确有手写 Go/Markdown 草稿。没有运行 go clean。 |
| R10 普通目录/文件、笔记 | 读取分类与本机目录结构；无登记的材料保持只报。包括不可凭名字判定的 scratch、笔记、独立 clone；没有全量审阅其内容。 |
| R11 工具临时 checkout | 抽查两个 merge-accepted 主仓及 ui 兄弟 worktree、push-main 残留。分别命中独有 detached/reflog 和 12 条 tracked 删除。 |
| R12 分支备份 | 四个日期目录，抽验两个 bundle 可读且含完整历史，无满 90 天样本；覆盖/最后副本问题来自被引用脚本及新规则。 |
| R13 Docker/默认缓存/快照/Cursor | 只读现有 disk-guard 代码及库存，未运行 Docker/Time Machine/Cursor 维护，未重测全卷占用。其现时大小和占用状态未确认。 |
| R14–R16 Tekton/PVC/发布证据 | 读 TTL YAML、离线复算保存的 PR/TR/PVC JSON，确认数量和所有权类别。未访问集群；发布 ConfigMap 内容、真实卷大小和日志归档可恢复性未验证。 |

**未能检查的事项**

遵守 BRIEF 的限制：没有网络、集群、MCP 或 SSH 调用，没有提交，没有删除任何东西；仅在本审查目录写入报告、只读审查程序及证据。没有改被审查 worktree，也没有写其他仓库或部署配置。

无法在本次确认现时 Gitea/GitHub refs、PR、任务/mission scope、哪次 verification 接受了 M-27 Q07、prune_failed/refused 事件、06/两台 mini 的磁盘与 agentd 运行版本；无法验证 NAS 归档、异机备份、远端 tag、发布证据和 PVC 的实际内容。进程与文件检查是一次本机快照，不是清理时的租约。没有进行删除演练、恢复写入演练或七天观察，不能把静态代码和离线快照检查说成生产验收。

先改
END OF REPORT
