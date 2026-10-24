**Review 532 — W-31 第 4 轮 4.3，设计第一轮复核**

结论：**先改**。D2 A 的方向可以保留：每个应用串行，不同应用并行，共享资源互斥。当前稿还不能保证这个承诺，主要问题在操作生命周期、入口覆盖和旧窗口迁移；并非单个 ConfigMap 的比较交换不可行。S1 的纯影子部分可以独立落地，但不能按现有顺序在 S2 开放并发。

本文引用约定：`D` = `/Users/vision-mac-trader/agent-work/r4-lanes/agent-config/work/multi-agent/DESIGN-release-lanes-2026-10-24.md`；`I/` = 同一 worktree 的根目录；`P/` = `/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/`，全部平台代码通过 `git show origin/main:<path>` 读取。已核实设计 HEAD 为 `836b65081174e8c900b8de1e9e8dcefbe952cf0c`，平台 origin/main 为 `82b3e9d798f098bbb2ce0bd4ed925892e116199e`。以下“会发生”指按设计规则可构造的失败场景，不声称本次在集群重现。

**A — 会出错的地方，需在实现前修改**

**A1．租约到期和 PipelineRun 终态都不能直接释放整次发布的锁。**

位置：`D:148`、`D:154`、`D:172`、`D:218`、`D:262`。

场景一：Research 持有 `db:golden_source(x)`，流水线还在迁移时平台升级或失联，5 分钟后租约过期。设计只用“本应用仍有 run”挡住下一次 Research；market-data 没有自己的在途 run，便可能拿到同一数据库的独占锁。这正是跨应用并发新增的风险。只保留 lane 占用、不保留完整资源集合不够。

场景二：PipelineRun 失败、超时或成功结束后，Argo 仍在同步，或发布操作还在观察、核对、自动回滚。`D:172` 此时释放车道，第二次发布进入；第一次的回滚又写回旧摘要，覆盖第二次。现有 pin-sync 的超时返回明确承认 Application 可能已经被修改且仍在同步：`I/k8s/cicd/tekton/task-argocd-pin-sync-platform.yaml:251`。此外，“发布记录器看到终态”不能直接复用当前逻辑：`P/api/internal/releases/service.go:165` 跳过所有不成功的 run。

最小修法：把锁归于持久的**发布操作**，有效占用为“活租约，或尚未完成/未确认停止的操作及其全部资源”。API、workers 重启不改变该占用；失联后进入待接管状态，不能靠 TTL 宣告空闲。记录 run UID、Argo 同步身份、阶段及恢复目标，直到核对/观察/必要的回滚结束才释放。创建结果不明、取消、失败而副作用未收敛也必须保留占用。定义 60 分钟是单次续期上限还是总操作期限；到限不能把仍在写的操作当作不存在。验收应包括“平台与 workers 同时停掉、跨 TTL 后另一个应用迁移同一库”和“run 已终态但 Argo 仍在同步”。

**A2．随机 token 解决同机身份碰撞，却没有把一次授权绑定到一个确定的操作。**

位置：`D:143`、`D:150`、`D:154`、`D:170`、`D:171`、`D:275`。

场景：同一会话因重试用一个 token 启动两个 research run；两者都满足“有持有者、token 相等、未过期”。按 `D:154`，属于当前租约的 run 又被排除在忙碌检查之外。也可以先按无 DDL 的提交拿锁，再将同一 token 交给不同 revision、不同环境或带迁移的 run；三条检查没有要求实际输入与算锁时的输入相同。`run` 在创建后才补记，还留下“创建成功、写回前崩溃”的间隙。

最小修法：拿锁时绑定不可变的操作 ID、应用/环境、逐仓 SHA、构建输入、目标及资源集合、登记表版本/哈希；启动时验证实际参数摘要。以操作 ID 确定 run 名，CAS 认领具体步骤，重试返回已有 run；同一操作需要多个 build/deploy run 时，明确它们的允许顺序和唯一在途步骤。任务验证自己的 UID/步骤及当前代次，不能只验 bearer token。运行时接管须更新可强制执行的代次，旧尝试不能拿旧 token 继续启动、续租或释放。W-56 已有可复用的一次性消费约束：`I/agent-config/work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md:92`。

**A3．“推即部署”的归属只看目录前缀，漏掉真实渲染依赖，也没有覆盖异步同步的生命周期。**

位置：`D:76`、`D:120`、`D:121`、`D:169`、`D:173`、`D:181`。

具体反例：只改 `I/k8s/base-platform/manifest.yaml`。它不在设计登记的 platform overlay 路径内，却由 PROD 的 `kustomization.yaml:8` 引入，`I/k8s/base-platform/kustomization.yaml:13` 再引入该 manifest。Argo 追踪 main 且自动同步、selfHeal：`I/k8s/cicd/applications/bifrost-platform-prod.yaml:13`、`:20`。即使未登记路径落到 `*`，也没有因此成为“必须持 platform 车道的推即部署目标”，且不会自动进入 `D:181` 的 R2 人工发布排除规则。推送后同步延迟、重试或 selfHeal 还会发生在推送命令退出之后，不能说自动同步“只从第 3 条进来”。

另一个分类反例是将整个 `agent-config/**` 当成不部署文档：这里包含正在运行的 guard、发布策略与脚本；现有签名路径表特意将 `agent-config/release-policy/**`、`agent-config/scripts/agent-guard/**` 等列为信任根路径，见 `I/agent-config/release-policy/paths.json:140`。本稿的广泛豁免会跳过它们的影响判定。

最小修法：按目标的完整渲染依赖/有效 diff 归属，登记 `base-platform` 等输入；只豁免明确的纯文档文件，并规定受保护路径优先于文档规则。推即部署是一份绑定目标提交的发布操作，持锁到同步及核对结束，冻结和授权也必须覆盖它。一次提交影响多个应用时，应原子获取所有受影响车道和资源。对无人值守 PROD，明确采用受控、固定 SHA 的同步入口，或给出自动同步同等强制的协议；不能只靠客户端 push 前查一次。

**A4．§2.3 尚未封住发布和迁移的侧门，部分侧门没有任何后续切片负责。**

位置：`D:173`–`D:176`、`D:227`、`D:366`、`D:393`、`D:416`。

具体缺口：

- 插件 Owner apply 被明确保留为“不经车道”。插件 build 持锁，并不保护稍后执行的 ConfigMap/Deployment apply；另一会话仍可在部署中改配置、滚动同一个插件。标注例外不是互斥。S6 只明确交付 Finance，没有插件部署接入的验收。
- Dagster 不是“Research k8s 推 main → Argo 部署”。`I/k8s/cicd/applications/bifrost-research.yaml:23` 明确排除 `orchestration/**`；`I/k8s/cicd/tekton/pipeline-build-research-dagster.yaml:3`–`:6` 只构建。现行发布说明另走 `apply_manifest`，见 `I/agent-config/claude/skills/research-release/SKILL.md:97`。因此 Dagster 的构建有任务闸，部署仍落在“先只审计”的旁路。
- 手动 `gitops_sync_app` 只要求 PROD 持锁，漏掉 STG；这与同应用 STG/PROD 共用车道直接冲突。还漏列 `gitops_rollback_app`，它会真实改变目标版本，动作见 `P/api/internal/actions/catalog.go:180`，执行接线见 `P/api/internal/server/actions_wire.go:284`。
- `owner_run_command` 的任意命令执行不因批准自动变成持锁操作。动作目录只有 command、reason、runner，没有应用/资源范围：`P/api/internal/actions/catalog.go:451`。单独的迁移 Job 同样必须登记：例如 platform PROD 迁移明确由 Owner Job 完成，deliver 只是验证数据库已具备迁移，见 `I/k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:526`。只从 deliver 的 diff 算库锁，保护不了先行的 Job。
- `apply_manifest` 即使不属于某个应用，也可能改共享 `cicd`/Postgres 资源。`D:176` 将这种 apply 排除，与 `D:140` 的共享资源独占要求不一致。重启本身未必是发布，但使用可变 tag 的旧插件被重启时可能换镜像，也会打断观察期，不能一概视为无关。

最小修法：补一张按**实际副作用**枚举的入口表，覆盖 build、部署、同步/回退、配置、迁移 Job、共享基础设施和受控 Owner 脚本。已知部署改走窄动作；保留 Owner 命令时，批准和执行认领须包含确定的应用/资源范围，不能靠解析任意 shell 猜测。无法接入的入口应暂停与相关车道并发，或继续由全局维护操作包住，并明确不进入自动策略。将这些接入及冻结演练排在“开放对应应用并发/无人值守”之前。

**A5．M1 的兼容镜像并不“只会偏严”，双对象也不是一个原子锁。**

位置：`D:242`、`D:246`、`D:357`、`D:366`。

反例：新接口已给 Research 分配车道，旧 ConfigMap 的 what 包含 `bifrost-research`。旧 Research Task 只检查集合相交，不检查 token/会话；同仓库的第二个旧 run 仍通过。多个应用的仓库并集会同时放行这些应用的旧 run，而不会给它们补上新资源锁。代码是 `I/scripts/release/window_decision.py:101` 和 `I/k8s/cicd/tekton/task-release-window.yaml:128`。本次用现有 Python 函数离线调用，两次 research 判定及一次 market-data 判定均返回 ALLOW。

另有双写间隙：新车道写成、旧镜像尚未写成时进程退出，旧读者可能读到无窗口；反向次序可能留下永久阻塞。旧 GET/DELETE 还可删除旧镜像。两个 ConfigMap 上各自带 resourceVersion，并不使两者共同原子。S2 先更换客户端、S3 才更换任务与审批执行器，正好暴露这个过渡区。

最小修法：M1 只做影子/适配，所有活动仍按 `*` 串行；在旧 run 排空、所有写入口和任务已能识别绑定操作的新协议后，再打开跨应用并发。旧接口必须调用同一权威，不能仅靠仓库并集模拟安全性。回退先停新认领并排空/接管已有操作，再收紧到 `*`；不能在多个发布仍在写时直接切回旧单窗口。把旧接口、旧 Task、旧客户端、新服务混用的正反例列为 S2/S3 联合切换验收。

**A6．“R1 应用代码”不等于可自动恢复；目前的小改动定义省掉了 W-56 已定的兼容性条件。**

位置：`D:202`–`D:219`、`D:233`、`D:383`–`D:390`、`D:413`。

场景：只改普通 Go/Python 代码，写出新的 JSON 状态格式、改变 Redis 值的语义，或改变新旧 API/Console 的契约。没有 SQL、没有迁移路径，按当前文字是 R1；新版本启动后写入状态，再发生健康失败。旧镜像即使存在且拉得到，恢复后也可能读不了新状态。按摘要回滚解决的是产物可重复性，不证明状态和协议向后兼容。`max_changed_files` 或行数上限均不能修复这一点。

这不是要求增加未经讨论的新门槛：W-56 原计划已规定状态格式路径排除、双向状态兼容及新 API 对旧 Console 的契约测试，见 `I/agent-config/work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md:130`、`:132`、`:263`。其 `:148` 还要求策略授权有界发布动作，签入恢复条款、阶段超时、中断上限和接管者。本稿只引用第 5/6 步的名称，未明确承接这些约束，S5 验收也只有“起不来”而无“已写状态后失败”。

最小修法：将“小改动”写成“风险分类允许 **且** 可自动恢复证明通过”。用签名的路径/输入规则、完整逐仓 diff 和 CI 契约证据判定；状态格式、未知路径/输入、缺少基线或无法证明兼容均转人工，不自动恢复。恢复目标在操作开始前锁定，保留镜像及配置输入，签定阶段期限和恢复权限。独立监督器必须在写入前确认已持久化意图，并能在 api/workers 同时坏掉时直接恢复；不能只用应用自身的健康接口或 Finance 自己的告警替代。S5 增加上述状态兼容和平台整体失联演练。

**A7．原子获取避免了半持锁死锁，但“写者优先”的等待标记会造成互相阻塞。**

位置：`D:132`、`D:135`、`D:156`–`D:159`、`D:272`。

反例：资源 X、Y 当前被一个操作共享持有。请求 A 需要 X 独占、Y 共享；请求 B 需要 X 共享、Y 独占；两者被拒后分别登记 X、Y 的写者等待标记。原操作结束后，A 的 Y 共享被 B 的标记挡住，B 的 X 共享被 A 的标记挡住。若重试更新 5 分钟有效期，双方可以一直等到 24 小时过期；即使不更新，也会周期性停顿。每次发布普遍获取 `cicd`、`pg-cluster` 共享锁，使这种组合不是空想。单对象 CAS 本身不解决此调度问题。

最小修法：为整份请求建立稳定的先后次序，只允许更早的冲突请求阻挡后来者，或者先做不宣称无饥饿的有界退避。等待记录须绑定操作、全部资源、期限，定义重试不丢顺位、取消/死亡清理、自身不阻挡自身。对同一资源的 s/x 去重取 x，明确 `*` 与所有 lane/资源冲突；一项迁移触及两个数据库时一次获取两个 x，不能逐库执行再补锁。加入上述交叉 s/x 反例和双库迁移竞争用例，不能只测两个 GS 写者。

**B — Owner 选择选项、切片前应知道的缺口**

**B1．推荐 A 合理，但 B 被过早当成必须双份存储。** `D:327`–`D:331` 引用的是 k8sstate 当前默认部署方式。代码的构造函数实际上接受 namespace：`P/api/internal/statefile/k8sstate/k8sstate.go:43`；`:123` 的 `Update` 已在冲突后重新读取并重新执行 mutate。可以为 release lanes 建一个指向 `cicd` 的专用 backend、一个 key，由 PROD 平台写、Tekton 直接读同一对象，不给 STG 创建第二份、不镜像。这等于 A 的部署拓扑加现成的 CAS 实现，是较便宜的实现选项。不能复用 `Write`，其 `:6`、`:78` 明确是旧字节重试的 last-writer-wins。C 的 PG 依赖确实与 ADR 修复链隔离冲突，当前没有必要为此选 C。

**B2．S1 可以先落地，但其“回放证明”和 S2 独立上线承诺要缩小。** `D:344`–`D:354` 的只审计纯函数不会改变当前准入，适合先做；必须保证影子错误不会影响原调用。现有审计缺少被拒请求、唯一会话、资源集合、完整部署输入和非 Tekton 操作，不能仅靠旧记录证明每个同应用重叠均拒绝；`D:424` 自己已承认历史分不出同机会话。需合成带已知答案的并发反例，并将历史回放标为有缺失项的辅助证据。S2 必须维持全局互斥到 A5 的切换完成；S3 的验收需覆盖 A1–A4。S6 退役旧接口前必须确认所有插件和 Dagster/迁移入口已迁移，不能只迁 Finance。

**B3．登记表也是互斥的信任输入，不只是放权输入。** `D:126` 说登错只会多等，与 `D:268` 承认少拿库锁相矛盾。错误地将已知迁移分给另一库、从 uses 删除资源，或以宽的文档规则遮住路径，不会落到“未知路径 → *”。策略哈希不匹配只停止自动批准，人工批准的两个发布仍可能用错误资源集合并行。最小补充是登记表变更审核/受控激活、语义校验和操作期间固定版本；变更涉及活动资源时排空或保守取新旧约束并集。是否整表签名可由 Owner 选，但不能用“最多多等”作为不签的理由。另需定义每库的普通使用是否拿 s、迁移拿 x；否则不能从 `uses` 字段推断读写冲突的实际语义。

**B4．十个待定点中，几项的选择成本还没交代完整。**

| 待定点 | 选择前应补的信息 |
|---|---|
| 1 存放 | A 可行，评估 B1 的专用 k8sstate 复用；存储独立不等于续租/恢复执行器独立。 |
| 2 登记及签名 | 补 B3；单表哈希意味着给 Finance 加一项也可能使所有应用策略失配、全部停止自动放权。明确接受全量重签，还是签应用及相关共享规则的规范化子集。 |
| 3 通用共享锁 | 可以保留安全默认；补真正执行共享变更的入口，以及 s/x 合并和等待调度。若 SQL 直接改集群而无 Git diff，仍须声明 `pg-cluster(x)`。 |
| 4 小改动 | 路径分类与“可恢复证明”分开。无需把行数当安全保证；不能省掉 A6。 |
| 5 首个应用、10 分钟 | platform 有现成摘要部署，是合理候选；前提是外部监督器、恢复权限及冻结切点验收。Finance 的告警能力本次无源码可核对，不据此确认其就绪顺序。 |
| 6 队列 | 无完整队列可接受，但写者等待标记已经承担调度职责，至少要解决 A7 的先后与过期。 |
| 7 窄动作 | `pin_argo_app` 适合 Finance；插件目前未必有 Argo Application，不能只改一个动作名就自动部署。需列出每个插件的配置、Deployment、迁移、健康探针和回退目标及迁移片。 |
| 8 ui | 已固定 SHA 时，ui main 移动不会改变在途构建，见 `D:417` 自身依据。说明究竟互斥哪种共享副作用；若只是源码推送，可缩小到共享可变产物的发布阶段。这是降低等待的选项，仍由 Owner 决定 D2 中 ui 的具体范围。 |
| 9 冻结 | 全局和应用冻结组合必须取更严格结果，缺失/读取失败如何处理应明确；冻结标识必须含作用域。冻结后的有界恢复应保留当前操作的锁及授权，不能借通用“恢复”标志放行任意版本。 |
| 10 自动合入 | 排除集合必须包括真实渲染依赖和信任配置，不能只有两个目录；与 4.1 使用同一输入和判定，包含一次提交影响多应用的情况。 |

**B5．与 W-56 旧设计的关系必须逐项说明，不能用“剩余门槛”概括。** `D:173` 保留 Argo 自动同步，`D:315` 说 PROD platform-api 是车道对象唯一写者；但所引用 W-56 的 `PLAN-w56-unattended-prod-2026-10-10.md:88`、`:90` 要求受控的完整 SHA 同步及冻结/副作用认领的串行切点，`:139` 又要求带外监督器能 CAS 接管及独立冻结。D2 A 明确推翻全局并发 1，没有据此自动推翻这些要求。写一份“已由新实现替代／继续继承／待 Owner 修改”的对照，指定 lanes 与 W-56 代次对象的单一权威和接管写权限，避免同时存在两套相互矛盾的租约。冻结刚落下而旧 token 尚有效、平台升级中 api/workers 全停、外部监督器接管后旧执行者恢复，都应有唯一结果。

**C — 小项与事实表述**

- `D:76`“agentrt 迁移在 deliver 里跑”过于笼统。PROD 当前只查已应用迁移，实际迁移是 Owner Job，见 `I/k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:526`；会影响迁移入口清单，已计入 A4。
- `D:353` 的“19 条流水线都有归属”应提供完整机器可读清单，而非固定数量。本次 infra 下找到 17 个 Pipeline 定义，其中包含 apply-manifest 和两条 smoke；补充的 flex-query 为第 18 个，Finance 源码缺失，无法核实第 19 个。`ci-python` 又是按 repo 分派，不是一条流水线永远属于一个应用。现有检查器仅收集 build/deliver，见 `I/scripts/check-release-chain.py:41`；新验收要区分发布、纯 CI 和共享写操作，不应要求所有 CI 都拿发布车道。
- `D:168` 的旧 `--what` 翻译成应用，与 `D:242`、`D:362` 的旧接口/旧 hold 一律拿 `*` 不一致。需明确协议版本，而不是同一命令在不同片具有隐含语义。
- `D:303` 删除模板里的 concurrency 不等于删除所有运行时限制；本次在生产 releasepolicy 代码中未检索到该字段的消费点，实际仍需迁移窗口适配、deliver-busy、prepare guard。`D:323` 的“一天几十次写”也未计入每分钟续租及等待标记，容量估计宜按同时活动操作数计算。
- `D:308` 的 tag 存在检查是额外的合作方防误用措施；registry 无鉴权且无条件写时，不能把先查再推称为不可覆盖保证。应强调唯一产物名/摘要部署，并在受控写入方的同一有效操作内做检查。

**逐项核对 §1.2 的入口与 §2.3 的承接**

| §1.2 入口 | 当前代码证据 | 新方案是否闭合 |
|---|---|---|
| 1 Trade release.sh | `I/scripts/release/release.sh:809` 开窗口；`:831` 查全局忙碌；`I/scripts/release/release_tool.py:97` 匹配所有 deliver | 方向正确；需 A1/A2 绑定整个操作、输入和资源，不能只改忙碌过滤条件。 |
| 2 hold | `I/scripts/release/release.sh:743`–`:763` | token 可解同机碰撞；还需输入/资源计划、续租和版本兼容语义。 |
| 3 push-main | `I/scripts/release/push-main.sh:182`、`:273`、`:558` | 当前确实全局拒绝；新方案有 A3 的依赖归属和异步同步缺口。 |
| 4 Research/插件/Dagster 的 Task | `I/k8s/cicd/tekton/task-release-window.yaml:128`；Dagster `pipeline-build-research-dagster.yaml:43` | build 入口可接；部署、迁移仍需 A4。flex-query 补充工作树 `k8s/cicd/pipeline-build.yaml:30` 也有窗口任务；未将该补充文件视为已钉定主基线。 |
| 5 Trade/platform 四条 deliver | 各 Pipeline 的 freeze-check；`I/k8s/cicd/tekton/task-prepare-deliver-stg.yaml:33` 按 STG/PROD 分组 | 加车道 Task 必要；需验证所有有副作用的 DAG 路径受其支配，并处理旧 inline PipelineRun/TaskRun。当前 prepare guard 只覆盖 Trade 同环境。 |
| 6 审批执行 | `P/api/internal/server/actions_wire.go:244`；`P/api/internal/delivery/service.go:249` | 平台自己拿锁是正确修复；需覆盖重试、创建结果不明、失败、接管及回滚，而非看到 PipelineRun 终态即释放。 |
| 7 Argo | platform-prod Application `:20` 自动；Research Application `:23` 排除 orchestration | 未闭合，见 A3/A4；手动 STG sync、rollback 和持续 reconcile 也需处理。 |
| 8 插件 Owner apply | `I/agent-config/claude/auto-mode/release-permissions.json:4`、`:5` 保留命令模式 | 明确未闭合；不能以 UI 标签替代互斥或冻结。 |
| 9 Finance | 平台 `P/api/internal/delivery/ci_run.go:13` 的确未列 Finance CI；指定 Finance 目录不存在 | Finance release.py、审批数量、摘要核对和恢复演练均未复验；不能确认“只改一处”。 |
| 10 其他写动作 | `P/api/internal/actions/catalog.go:173`、`:180`、`:397`、`:451`，`actions_wire.go:173`、`:278`、`:284` | 未闭合，尤其通用命令、手动回退、迁移 Job、共享清单；见 A4。 |

**设计自己提出的四个问题：真伪核对**

| 设计结论 | 复核 |
|---|---|
| 同机所有会话同一个 who | **默认情况下成立**。`I/scripts/release/release.sh:746`、`:772` 为 USER@hostname；可用环境变量或 `--who` 覆盖，故不应写成无例外。`P/api/internal/delivery/window_store.go:145`、`:155` 证明同 who 可续期且替换 what。历史上是否发生同机重叠，本次无法证明。 |
| PROD 审批不持窗口、参数没有 who | **核心缺口成立，概括需修正**。审批执行器不自动开窗口，Trade/platform 无窗口会放行：`P/api/internal/delivery/release_window.go:146`–`:153`；但 catalog `:90` 接受 who，`actions_wire.go:248` 会转发，`I/scripts/release/release.sh:554` 明确把 who 写进 PROD 审批参数。因此“参数没有 who”只能是所采样单子的事实。Research 位于 guarded 表 `release_window.go:23`，无窗口会拒绝，并非三条 PROD 都无窗口起跑。`actions_wire.go:442` 的暂时拒绝前缀也不包含 missing who；同仓窗口存在而单里缺 who，不一定会重试。四个具体历史时间本次无法复验。 |
| GET 删除过期窗口没有前提 | **成立**。`window_handler.go:16` 调用 `window_store.go:183`，后者 `:193` 用空 DeleteOptions 删除。可发生“GET 读旧过期值 → 新持有者成功 Update → GET 删除新窗口”。另外显式 DELETE 的 `window_store.go:211` 也无前提，修复应一起覆盖。现有 PUT 本身已有 create/update 冲突重试（`:108`–`:179`），不能把它说成完全非原子。 |
| 三份硬编码判定表 | **成立**。Go `release_window.go:22`、`:30`；Python `I/scripts/release/window_decision.py:12`、`:28`；Tekton `I/k8s/cicd/tekton/task-release-window.yaml:39`、`:55`。但判定语义并非完全相同：Tekton 不验 who，Go API 验；现有 `I/scripts/check-release-chain.py:137`、`:148` 仅对照 Python 与内联 Task。三份表存在不等于完全没有漂移检查。 |

**验证与限制**

本次仅做本地只读源码/设计核对，运行了 6 项针对现有 `window_decision.py` 的离线断言：仓库并集下的两个 Research Task、一个 market-data Task 都获准；无窗口的 platform PROD、Trade PROD 获准；无窗口的 Research 被拒。结果全部符合上述反例。未将这些纯函数结果冒充集群并发演练。

未联网、未访问集群/MCP/SSH、未提交、未修改被审设计或任何源码。未运行 Go 构建、完整测试套件、PostgreSQL 或监听端口。没有真实 apiserver，未验证 resourceVersion 并发、准入/RBAC、TTL 后的长 run、滚动升级中断、Argo 实际同步、冻结与认领竞争、registry 拉取/保留和自动恢复。Finance 指定目录不存在，未核实其 `0698265` 源码；设计 §1.3 的审批单、审计数字与运行态均仅为作者报告。

一次包含 `I/scripts/owner/owner-run.sh` 的只读检索被工作区 preflight 以“Owner 凭证／只给 Owner 运行的脚本”为由拦截；没有重试该读取或绕过闸门。因此未核查该脚本内部的执行细节，相关判断只依据已读动作目录及接线。本次只主动写入 `REPORT.md`。

先改

END OF REPORT
