**Review 539 — W-31 / 4.6 第二轮，仅复核 534 的问题及第二稿引入的缺口**

结论：**先改**。第二稿已解决“同 Change-Id 就能恢复”、遗漏 detached HEAD、未提交删除和备份到期丢失的主要设计问题；B1–B4 也已纳入。但“可自动清”的分类仍比规则宽：读取 reflog 失败会当成空历史，缓存检查会漏掉内部材料，结束证据没有贯穿本地分支和已登记 worktree，新增的 `worktree lock` 也不能实现文中承诺的删除流程。这些条目目前不能当作删除清单。

这是最后一轮技术意见，不要求自动再开第三轮。文末给出 Owner 可直接选择的处置方案。

基线：`r4-lifecycle` 的 HEAD 为 `db3d14d9877995a91598049b00d84c46830ceb55`，工作树检查前后干净；比较范围为 `df91bfee..db3d14d9`。已读 534 的 REPORT、RESPONSE，以及第二稿 CUT、INVENTORY 和全部证据文件。辅助核对的 platform `origin/main` 为本地已有的 `82b3e9d798f098bbb2ce0bd4ed925892e116199e`，没有更新远端。

下文 CUT、INV、DATA 分别指第二稿的 [切法](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md)、[盘点](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.md) 和 `INVENTORY-lifecycle-2026-10-24.data/`。**“关闭”指本轮切法层面已吸收，不代表 S1–S7 已实现或生产验收通过。**

**A1–A7 逐项裁定**

| 项 | 裁定 | 依据与边界 |
|---|---|---|
| A1 原对象副本 | **关闭** | CUT:98–101、179–180 已改为确切对象可达或持久归档，排除本轮待删引用；标题、Change-Id 只作线索。全部 132 条本地候选的 tip 与 reflog 可达性复算通过。原 detached 反例仍有 HEAD 独有 1、连 reflog 独有 3，第二稿确实留住它。 |
| A2 reflog | **原问题已补，带新洞** | CUT:102、180、232 要求归档 reflog；原样本 `w31-25-release`、`td384`、`blocked-card` 分别复得 3、19、11 个不被 Gitea 快照覆盖的提交，均只报。但新 `inv2.py:79–81` 把读取失败转成空列表，见 F1。 |
| A3 agent 分支及 D-L5 | **关闭** | CUT:121、235、265 明确原对象保全、缺推送证据不删、按 mission 处置，并纠正为标记后可能立即清理。唯一自动候选 a2 的原 SHA 确在快照 main 历史中。最终仍须 agentd 核对 task/repo/attempt/ref/commit；本轮不能证明运行时这组字段已齐全。 |
| A4 缓存及 ignored | **未关闭** | `status --ignored` 和对旧反例的保留已纳入；但 CUT:103、161 仍允许“登记**或**布局”，未达到本次 BRIEF 的“registered cache roots only”。新布局函数又只验外壳，见 F2。 |
| A5 未提交删除 | **关闭** | 原则 5、R11 与 S2 明确有删除仍只报、不加 force；实际 `push-main.XrTZfq` 仍有 12 项 tracked 删除，第二稿没有把它列入可清。R11 末栏“除非完整归档了差异”应理解为人工后续处置入口，不能覆盖原则 5、不能仅凭一份 diff 转成自动清。 |
| A6 会话结束及竞争 | **未关闭，修订又引入锁语义问题** | 未登记 worktree 降为 D-L8 是正确改动，分支删除的 old-SHA/lease 也正确。但 132 条本地分支没有结束证据检查，已登记 worktree 也只检查登记文件存在；`worktree lock` 与非 force 删除相冲突。见 F3、F4。 |
| A7 bundle 覆盖及最后副本 | **关闭** | CUT:110–111、132、183、214、232、264 联合覆盖唯一 run 目录、先验证、不覆盖、独有归档永久保留及验收；没有发现另一条新规则授权绕过这些保护。30 个旧包的核验及计数校正在下文。 |

**剩余问题：全部对应上表的原问题，或由本次新增实现引入**

**F1 — A2：错误被当作“没有历史”，新盘点程序不是遇错保留。**

[inv2.py:79](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.data/inv2.py:79) 的 `reflog()` 在任何非零返回码下返回 `[]`。接着本地分支用 `[tip] + rl` 判断，tip 已在远端且未检出时，直接在 :231–232 标成可自动清。这使“reflog 无法读取”与“已证明没有独有 reflog 提交”不可区分。:214–215 对 `worktree list` 的返回码也没有处理，读取失败时会把占用集合当成空。

只在内存注入 `git reflog` 返回码 128，原函数确实返回 `[]`，证据见 [semantic-evidence.json](./semantic-evidence.json)。本次实际 132 个样本的读取均成功，没有声称它们已经触发了此错误。

最小处理：读取结果保留成功/失败状态；reflog 或 worktree 枚举出错、输出无法解析时，该仓库相关候选一律只报。补两条读取失败反例即可，不需要改可达性算法。

**F2 — A4：布局确认提前返回，内部手写文件、嵌套 Git 和软链接均可能漏过。**

[inv2.py:244](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.data/inv2.py:244) 只在当前层查 symlink 和 `.git`；看到 Go `README` 与十六进制桶名就于 :255 返回。它不会检查桶内部。Go module 与 npm 分支也在检查内部内容前返回。这不符合 CUT:161 的“遇到嵌套 `.git`、手写文件、不认识的条目，整个候选只报”。

用同一函数做三个纯内存反例：`cache/00/draft.go`、`cache/00/.git/`、`cache/00/outside` 软链接，三个均返回 `go-build`，访问记录都只有 `cache` 一层。没有向真实缓存植入任何材料。证据同上。

本轮 BRIEF 明确要求只处理登记缓存根；第二稿却把仅有布局、`run.done` 的 20 个历史目录直接列成“可自动清”。**这些实际样本的完整遍历没有发现上述异常，不等于该算法能保证别的或之后的候选安全。**

最小处理：布局只用于识别、审查和登记候选；删除仍要求明确的缓存根及用途登记。检查实际根及全深度内容，不跟随链接、不跨根；出现未知内容或检查失败就保留。若 Owner 要接受“历史缓存无需登记、仅按类型识别”的例外，必须把它列成有明确风险的选择，不能称为已符合本次规则。S1 的反例要放进十六进制桶内部，不能只测缓存根目录。

**F3 — A6：会话结束门槛没有贯穿分类。**

[inv2.py:194](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.data/inv2.py:194) 只要 `bifrost-owner` 文件存在、内容条件通过，就标“登记且内容全在 Gitea”。没有读取 `ended_at`、`lease_until` 或会话状态。S3 一旦开始给活跃 worktree 创建登记，这个分支就可能把仍在使用的干净 worktree 放进可清；不能以“今天还没有登记”作为重跑脚本的长期保护。

本地分支的 [R6 / CUT:126](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:126)、`inv2.py:210–236` 和 INV:303 也只检查未检出与对象可达，没有任何结束证据。132 条对象都能恢复这一点已证实；**它们的所属会话都已结束这一点没有证据**。临时切离一个分支，不代表其主人已完成工作。

最小处理：分开记录“对象已有副本”和“满足删除条件”；未提供结束证据的本地分支降为待确认。已登记 worktree 解析并验证结束记录与有效租约，恢复会话必须撤销结束状态。D-L8 中的提交尾注只用于找线索，不能单凭 HEAD 的作者会话推断当前使用者已结束。

**F4 — A6：新增的 `git worktree lock` 不是写入锁，而且会阻止文中要求的删除。**

[CUT:107](/Users/vision-mac-trader/agent-work/r4-lifecycle/agent-config/work/multi-agent/CUT-lifecycle-2026-10-24.md:107)、R5、:182 与 S2 要求“先 worktree lock、复查、不加 force 删”。本机 Git 手册明确：这个锁防止管理目录被 prune、worktree 被移动或删除；删除 locked worktree 需两次 force。它不禁止用户编辑或 commit。因此照文中流程执行会拒绝删除；若实现者临时 unlock 或加 force，又没有解决原 A6 的并发写入问题。

机器级 `.lifecycle.lock` 当前只约束清扫器，CUT:173 的会话续租没有声明要参与同一个互斥协议。单独的 old-SHA 删除也不能防止另一使用者刚好把同一 SHA 的分支检出。

最小处理：明确清扫与登记使用者共同遵守的租约/互斥状态，持有它直到最后复查和删除结束；有使用者恢复就退出清理。Git 的保护锁与这个协议分开：原有的他人锁始终跳过，只能在仍持有应用层互斥时解除清扫器自己的锁，再非 force 删除。加入“复查后恢复会话/检出同一 SHA”的反例。不能把 `worktree lock` 本身写成已解决竞争。

手册证据：[git-worktree.1:164](/Library/Developer/CommandLineTools/usr/share/man/man1/git-worktree.1:164)、[同文件:248](/Library/Developer/CommandLineTools/usr/share/man/man1/git-worktree.1:248)。没有运行任何 remove、unlock 或删除试验。

**实际复查：153 条自动候选，另核对 30 个包和 5 个旧反例**

主批检查时间为 2026-10-24 05:42:56–05:43:06 UTC。远端证据使用 DATA 保存的 **05:24:40Z 快照**，不是现时 Gitea。所有 Git 检查均设置 `GIT_OPTIONAL_LOCKS=0`、`GIT_NO_LAZY_FETCH=1`，没有 fetch 或 ls-remote。

- **全部 132 条本地分支**：当前 tip 与库存一致，当前 worktree 列表无检出；tip 加 `reflog show` 的提交对快照 refs 的 `rev-list --count ... --not ...` 均为 0。额外读原始 reflog 的 old/new SHA，复算也全部为 0。127 条 tip 在快照 main 上；另 5 条由保留中的人的分支覆盖。这 5 条后续进入 D-L2 时必须继续遵守先归档，不能把本次结果理解为可以同时删两处副本。
- **全部 20 个复核缓存**：重跑稿件的类型函数、检查 `run.done`、`du -sk`，并完整遍历 83,745 个文件项（包括三个 `go/` 包装目录）。合计 **10.0481 GiB**；均符合 Go 构建缓存文件布局，没有发现手写异名文件、嵌套 `.git` 或软链接。没有检查每个构建产物的内容或重建它；布局结果不能代替登记。
- **进程检查有局限**：`lsof -nP -Fn` 返回 0，没有上述 20 个缓存的路径匹配，但同时报告一个外部 SMB 挂载的 stat 警告及“输出可能不完整”。因此只记录“未观察到占用”，不签发“无进程使用”的删除许可；没有访问该挂载。
- **唯一 agent 候选** `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a2`：SHA `6ce6e8e95fef818ca8cb1debce71a1cae691b1bb` 是快照 main 的祖先，去掉自身 ref 后独有提交数为 0。任务状态及 pushed 字段未联网重查；保留 R2 运行时条件。

下面列出 15 个实际复查条目，完整逐条结果见 [readonly-evidence.json](./readonly-evidence.json)，程序见 [audit_readonly.py](./audit_readonly.py)。表中通过只表示对应的内容检查通过，仍受 F1–F4 和现时复查约束。

| 类别 / 仓库 | 分支或路径 | tip / 结果 |
|---|---|---|
| local / platform | `cursor/a-platform` | `1cf4d2c94a82`；tip+reflog 独有 0、未检出 |
| local / plugin-flex-query | `cursor/c-flex` | `cbe8f6c172bb`；同上 |
| local / plugin-market-data | `cursor/w-market-data` | `21dfe0479109`；同上 |
| local / research | `cursor/e2-research` | `481c96cbd3d9`；同上 |
| local / trade-api | `cursor/t2-api` | `1d001b6fe23e`；同上 |
| local / trade-core | `cursor/f-core` | `3eccebd449c3`；同上 |
| local / trade-frontend | `cursor/h-frontend` | `70ffac510b0b`；同上 |
| local / trade-infra | `cursor/c-infra` | `28066b351259`；同上 |
| local / trade-worker | `cursor/lane-g` | `7cddef467ee7`；同上 |
| local / ui | `cursor/td-ui-build` | `b65af130898f`；同上 |
| review cache | `codex-review-109/go-cache` | Go 布局、run.done；9,343 个文件项 |
| review cache | `codex-review-424/cache/go` | Go 布局、run.done；7,969 个文件项 |
| review cache | `codex-review-440/.cache/go` | Go 布局、run.done；8,078 个文件项 |
| review cache | `codex-review-452/cache` | Go 布局、run.done；3,906 个文件项 |
| agent / platform | `t_01M50FZ…/a2` | `6ce6e8e95fef`；main 祖先、去掉自身后仍可达 |

五个旧反例的重跑结果另存 [counterexample-evidence.json](./counterexample-evidence.json)：detached 原对象、三个 reflog 样本及 12 项 tracked 删除全部仍被第二稿的只报分类覆盖。

**30 个旧 bundle：保全通过，计数要按原始含义阅读**

全部 30 个 `git bundle verify -q` 返回 0；包头没有 prerequisite；`bundle list-heads` 与相邻 `.refs.tsv` 的 ref/SHA 全部对应。保存了每个包的 SHA-256，没有解包、恢复或写原仓库。

“168”是 **168 条引用记录，不是 168 个去重提交，也不是 30 个包各自都有独有内容**：复算得到 126 个不同的 `(repo, tip SHA)`，分布在 23 个包中；另 7 个包的清单头全部可从快照 refs 到达。其历史中的独有祖先总数并不是这 126 这个数。

其中 28 条引用的目标对象当前已不能从本机原仓库读取。没有沿用 `inv2.py:334` 把未知直接算独有的办法；本轮另从所有保留 refs 完整枚举可达提交，再做 SHA 集合比较，30 次图枚举均成功，仍准确复得 168 条不被快照覆盖的记录。这也说明旧包确有必须保留的价值。

| 可能触及旧包的规则 | 第二稿是否保护最后副本 |
|---|---|
| 新一轮分支备份（原则 8、S2） | 是。改用机器/仓库/run-id，不再复用旧日期路径；同日两轮验收要求两个包都在。旧脚本尚未修好，不能提前挂定时器。 |
| 90 天清理（原则 8、R12） | 是。必须证明包内每个提交仍在持久引用上；这 23 个含独有头的包不满足，不能到期删除。未知情况同样必须保留。 |
| 一次性清理 §4.6 步骤 1 | 是。对旧包最后副本只写“打进本次归档、verify”，明确“归档只加不删”，没有授权顺手删源包。 |
| 迁移 D-L4 | 是。独有包永久归档、校验试读，失败留本机；B 是永远留本机。不能将“副本也超过 90 天”当作永久归档的到期理由。 |
| 本地缓存、worktree 及远端清扫 | 没有新规则把备份根列为这些删除对象；R12 的保护仍是专门规则。 |

因此 A7 在切法层面关闭。无法仅凭离线快照证明它们是全世界仅存的一份；这里的“最后副本”指没有找到可替代的 Gitea 快照副本，按保守规则永久保护。

**B1–B4 与原决定项**

| 项 | 是否纳入 / 代价是否说清 |
|---|---|
| B1 落地资格 | **已纳入** CUT:140–147：入队、最终推送共用资格判定，计划有效性、版本、no_merge、退回、revert、effective_at 与三例验收都在；D-L5 不再代替持续闸门。这是交给 4.1 的实现和上线条件，不是本轮已验证 4.1 生效；需要同步作者并实现版本比较。 |
| B2 本地/远端分离 | **已纳入** CUT:181、194、209、234：互斥的两个模式、分别验证不触另一侧，S4 依赖 D-L1，一次性清理依赖 S1–S3。不能把现有 `--local` 当新模式使用。 |
| B3 分机器增长验收 | **已纳入** CUT:241–248：清理后基线、四类用量、分支净变化、零人工、所有机器有数据。1 GiB/天及第七天不超过 +5 GiB 是显式容差，Owner 应知道它不是严格零增长；不能抵扣一次性清理收益。06/mini 的观测缺口没有被当成通过。 |
| B4 实时停派 | **已纳入** CUT:199–204、236：实时 statfs、30/15 GiB 分级、未知即停、并发预留、主机样本失效和睡眠未观测。D-L6 如实列出新接口/存储、身份、机器/卷标识和安装成本。 |

D-L1 已限定人的 main 祖先分支；D-L2 是先归档、现在不删；D-L3 先保全 38 个确切头、只删已覆盖的 119 个；D-L4 增加索引、校验、引用保留及永久保留选项；D-L5 写明 mission 影响范围和可能立即清理；D-L6 列出架构成本；D-L7 不再重新问已定保留政策，只等待具体 apply。与 534 对这些选择的要求一致，本轮不追加其他决定项。

**C1–C4 及证据能否公开**

- **C1 关闭**：CUT:147 同时要求 task 尾注和原 SHA 的 cherry-pick 行，并纠正 Change-Id 的绝对化表述。
- **C2 关闭（文稿事实）**：三只数据 PVC 名已改为 `gitea-backup`、`gitea-data`、`registry-data`；本轮没访问集群，不对新数量作独立背书。
- **C3 关闭**：目标方向已纠正，并定义 GiB；B3 的容差如上。
- **C4 核心已纳入，复跑说明仍不完整**：原始 refs、时间、分类 TSV 和程序已进证据目录，足以复核本轮主要计数。为隐私不保存全量 lsof 是对的；但 `inv2.py:84` 必需的 `lsof_names.txt` 没有随目录提供，也没有采集/失败处理说明。不能说下载这个目录就能原样重跑。可补一份只含候选路径的脱敏占用证据、采集成功状态和离线复跑说明，不需要公开机器全部打开文件。

公开检查覆盖新增 DATA 的 **34 个文件、245,067 字节**，检查内容结构及凭证 URL、密钥、口令赋值、邮箱、本地路径等模式。未发现凭证值、私钥、账户内容、个人联系方式或私有仓库的源码/文件内容；Gitea 分支名和 SHA 是元数据，不能把它们自动称为凭证泄露。也不能把模式扫描当作绝对的秘密不存在证明。

需要处理或明确的两个边界：

1. `refs/gitea_bifrost-finance.txt:1` 含另一个独立仓库的 main SHA。它不在事实基线的公开工作区仓库清单内，离线无法确认其公开属性；本轮 132 条分支检查也不依赖它。**建议公开版不带这份无关快照，或由 Owner 明确同意公开这项元数据**；没有证据声称它已泄露私有源码。
2. `inv2.py:41` 还硬编码了本机随机临时目录前缀；其他数据已用 `~`、`<ws>`、`$TMPDIR`。这不是秘密，但应改为从环境取得前缀。真实 `/Users/<用户名>/` 在 DATA 中为 0。仓库路径棘轮仅匹配 `/Users/...` 且明确跳过 `agent-config/work/`，因此不能用它宣称这些证据已经过脱敏审查。

另直接以本地提交运行路径棘轮：父稿与本稿都因同一个既有 `scripts/benchmark/pick.py` 条目返回 1，第二稿没有新增该失败；不将它作为本轮新问题。`git diff --check df91bfee..db3d14d9` 通过。详见 [publication-evidence.json](./publication-evidence.json)。

**交给 Owner 的剩余选项**

| 选项 | 具体结果与成本 |
|---|---|
| **A，建议：保留全部候选，按已修正的切法继续实现** | F1–F4 写入 S1–S3 的实现和验收条件；历史缓存先确认登记，本地分支补结束证据；当前清单改叫“内容检查通过、待最终放行”。现在不回收所列 10.05 GiB，不删除这 132 条引用。开发和登记有成本，但不要求第三轮设计复核；实现后按反例验收。 |
| B：缩小首批自动化范围 | 先只做已登记、结束证据完整、检查成功且持锁复查通过的对象；无法证明的全部留作清单。会较慢达到分支数量和磁盘观察目标，历史目录也不会自动消失。对象保全规则不放宽。 |

D-L1–D-L7 的业务选择可以一并给 Owner 看；本报告的“先改”针对把当前自动候选直接交给清扫器，不要求无限延长设计轮次，也不把接受潜在工作丢失作为推荐选项。

**未能检查与执行边界**

没有网络、集群、MCP、SSH 调用，没有提交，没有删除任何东西，没有改被审查 worktree；仅在本审查目录写入报告、只读检查程序和证据。未执行原清扫脚本，即便其 dry-run 也会 fetch、写临时状态。

无法确认现时 Gitea/GitHub refs、任务/verification/pushed 字段、会话是否已结束、agentd 运行版本、06/两台 mini 磁盘、NAS 归档、集群数量及卷内容。没有做解包恢复、真实竞争删除、部署或七天观察；lsof 的可见性有上述警告。所有“可恢复/可达”结果受保存的远端快照和本地现有对象范围约束，实际清理必须重新核对。

先改
END OF REPORT
