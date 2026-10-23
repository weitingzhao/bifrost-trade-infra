# Review 519 · BI-2 Flex 插件换 Rust · 第 2 轮（最后一轮）

结论：**先修**。本轮有 **7 项 A、4 项 B**。上一轮 A1、A2、A5、A8、A9 的主要修正已在设计上闭合；A3 关闭了原泄露路径，但隔离模板留下新洞；A4、A6、A7 尚未闭合。这里的“闭合”指设计能对上指定版本的代码，不表示尚未编写的 Rust、录制器、CI 或集群清单已经通过验收。

未复议 REQUIREMENT.md。代码证据均用 `git show <sha>:<path>` 读取：插件 `bf6c61ca5318da7bdd928d4dfea782065bc48f7e`；core `a87e39f159c7aae2a4da2d5a62434c46ddec7bb0`；research `73694cca79d27e1bee07b4cb5a4ed1ac8df57338`；platform `36481b9002a93d25f978b4eaad1253c58c6b4e6f`；infra `e5db958d30937bf971e1ac8e87cff0374c3d8772`。以下 `fq/` 是插件的 `src/bifrost_flex_query/`，`core/` 是 core 的 `src/bifrost_core/`。DESIGN.md 行号按本目录文件；不以答复中的“已修”作为证据。

## A · Owner 决定前必须修正

### R2-A1 · 事务内录制的失败隔离没有成立，会把录制错误变成生产写入错误

**设计：** §2.2，DESIGN.md:222–239；§4.3，DESIGN.md:431；§10.2 #4，DESIGN.md:608。

**代码：** `core/monitor/reader/write_support.py:62–76`；`core/portfolio/reader/accounts.py:686–688,924–975,1159,1275–1304`。

`write_support.connect` 确实是可替换接缝，`golden=True` 也确实到达它；这个选点本身正确。问题是新增的序列、写前、写后查询直接运行在业务连接里。PostgreSQL 查询报权限错误、缺表或超时时，捕获异常、写一条固定 WARNING **不会恢复已失败的事务**。例如 §10.2 已承认的序列读取权限不足，会先使事务失败，再让原本有权执行的 INSERT 失败。若写后录制查询在业务 INSERT 完成后出错，直接 rollback 会撤销本次业务写入；只吞异常再调用 commit 也不能把它当正常提交。

“后台线程、64 MiB、等 30 秒”只约束写盘，不约束这些同步 SQL。连接的 `connect_timeout=10` 不是语句超时；额外 SELECT 仍可能等待表锁。发现作业被录制拖坏后再关闭开关，不满足“录制失败只少案例、生产照常”的承诺。

**最小修法：** 将可选录制 SQL 的错误与业务事务隔离，明确 savepoint、超时及恢复连接状态的规则，不替业务代码提交或整体回滚；失败后本次案例必须标为不完整。卷空间检查、发布完成标记也必须在受限的后台路径内。先用合成库验证：序列无读权限、录制 SELECT 超时、写后取证失败、卷写失败四种情况下，开关开/关的业务提交结果与业务错误完全一致。D-R10 可选“受测的代理接缝”或“core 正式钩子”；两者都不能省这组验证。

### R2-A2 · 两步判等仍缺完整起点和时间约束，且会把有效失败案例判成无效

**设计：** §2.2，DESIGN.md:228–234；§2.4，DESIGN.md:265–270；§2.5，DESIGN.md:287–289；§10.2 #4，DESIGN.md:608。

**代码：** `fq/schema/ddl.py:197–249`；`fq/worker/handlers.py:62–98,118–133`；`fq/worker/claim.py:155–210`；`core/persistence/postgres/brokerage_ddl.py:100,308`；`research/src/bifrost_research/orchestration/flex_husbandry.py:62–69`。

“Python 重放先复现生产，再比较 Rust”的顺序正确，但目前有三个具体缺口：

1. **freshness 没有完整写前状态。** §2.2 对 `record_freshness` 等只明确录语句、参数和写后行。失败分支在已有行上保留 `latest_ts`、`row_count`、`processed_rows`、`new_rows`；在空库上却 INSERT 成另一种状态。只载入业务行和认领后的 job，无法复现常见的“昨天成功、今天 not_ready”。不能拿期望写后行倒填初始状态，否则会掩盖应该验证的保留行为。
2. **时间只比有无和先后会放过业务差异。** Rust 若在失败时错误地把已有 `latest_ts` 前移，只要它仍早于 `updated_at`，就满足 DESIGN.md:268 的一般关系；这会改写消费者看到的最后成功时间。`defer_pending` 还必须验证逐行 `max(原 not_before, 本步时间+delay)`，不能统一要求与 `updated_at` 相差一个 delay。业务 `created_at=now()`、队列 `clock_timestamp()` 都是数据库时钟，插件的 clock 模块不能固定它们。需写清生产→Python→Rust 的时间映射，以及既有成功时间必须逐值不变的约束。`new_rows` 若按“所有读都注入”直接返回录到的计数，其相等只是同一输入；还须从两边实际写入状态独立核验。
3. **框架自证把正确失败也规定为无效。** DESIGN.md:289 的“业务已提交、freshness 失败”和“mark_done 失败”本来就是代码允许的生产结果。记录完整、Python 确实复现部分提交和 running/pending 状态时，案例应当有效。只有删掉提交结果、遗漏事件等破坏记录的版本才应不完整/不可判等。否则 §2.5 的 100% 有效率与“只有有证据的外部写入可排除”互相冲突，失败路径永远进不了验收。

**最小修法：** 先冻结 `case.v1` 的逐步 before/after 和时钟契约，至少补齐 job、freshness、受影响 pending 集合的必要写前状态；比较不变量必须按列、按操作列出。对失败注入区分外部故障与 SQL 自身应产生的约束错误：后者要让两边 SQL 真执行，不能直接把 Python 的错误强塞给 Rust 后就算证明了相同写入行为。每个合法失败场景增加一个“完整记录可复现”的正例，以及一个“损坏记录被拒绝”的负例。序列权限不足时也不得自动降级成“两引擎互相相等”便放行，须取得权限或另行确认并验证完整的主键映射契约。

### R2-A3 · 尝试分母仍来自案例本身，漏掉整条作业时可以全绿

**设计：** §2.2，DESIGN.md:233–241；§4.1，DESIGN.md:390；§4.2–4.3，DESIGN.md:409–430。

**代码：** `fq/scheduler/enqueue.py:33–59`；`fq/scheduler/daily.py:97–110`；`fq/worker/claim.py:57–92,95–135`；`fq/worker/loop.py:152–180`。

§4.2 的“分母 2”仍是“每个案例里有录到的作业行”；没有独立取得生产最终作业清单的步骤。可构造两段历史：两类计划作业各有一个完整 done 案例；另一段历史除此之外还有一条同日 worker 作业，在录制关闭/磁盘不足期间执行失败。因为去重只约束 pending/running，前一条 done 后同样的入队可以再建新 job。两段历史交给离线台账的案例、最终 attempts 和计划槽完全相同，后者却不应全绿。这不是加“尝试数相等”能发现的。

另外，`started/` 在 PVC 根下，而重放只挂 `subPath: cases` 和 `subPath: verdicts`；它读不到 §4.2 要检查的 started。认领提交后、写 started 前崩溃也没有标记。故仅增加 started 仍不是独立分母。

**最小修法：** 由已有生产侧连接单独导出最小、无账户内容的作业清单/日结快照：计划槽身份、job id、kind、manual 标志、最终 attempts/status、快照截止点及完整性标记；不要把它挂在“成功录成一个案例”的路径上。重放按该清单与案例对账，快照缺失就不计数，并挂入可读的 started/清单目录。明确迟到尝试、补跑、额外 enqueue 与计划槽的归属；交易日绑定被验证的计划/报表窗口，不只看尝试实际运行的当地日期。周一/节假日复跑、跨午夜重试和历史显式窗口各有反例，不能让历史窗口补成新交易日。

### R2-A4 · 候选身份没有覆盖全部生产输入，改了运行行为仍能沿用 10 天成绩

**设计：** §1.7 Q6，DESIGN.md:179；§3.4，DESIGN.md:356–368；§4.3，DESIGN.md:424–426；§六，DESIGN.md:490–491。

**代码：** 插件 `Dockerfile:18–24`、`config/schedule.yaml:8–26`；`fq/worker/loop.py:101–108,161–163`；`fq/worker/retry.py:85–97`；`fq/scheduler/daily.py:91–110`。

身份只包含两个 crate、Cargo.lock 和 rust-toolchain.toml，漏掉 `rust/Cargo.toml`、Cargo 构建配置、Dockerfile、烤进镜像的 schedule/config 及其他构建输入。最直接的反例是只改 `config/schedule.yaml` 的重试延迟或补跑宽限：worker 的实际行为变了，列出的 tree 哈希全部不变。根 workspace manifest 改 feature/profile 也不必改 Cargo.lock。记录一个新的重放镜像 digest，并不能证明它和生产镜像中的程序采用了同样的构建参数。

**最小修法：** 用覆盖全部生产源码、资源、manifest、构建配置和工具链的构建身份，绑定被测产物与拟发布产物。第一块最省事的是钉完整提交、受控构建参数/基础镜像及产物证明；宁可纯测试改动触发额外重验，也不要先做容易漏文件的白名单。若保留“只改比较器不重数”，须由独立检查证明生产输入完全未变，且重跑已有证据。给“只改 schedule”“只改 workspace manifest/feature”各做一条身份必须变化的反例。

### R2-A5 · 缩 worker 到 0 仍是停进程，不是先停领活再排空；API 同步写入也未排空

**设计：** §3.5，DESIGN.md:377；§5.2–5.5，DESIGN.md:445–466。

**代码：** `fq/worker/loop.py:151–180,211–220`、`worker/runner.py:11–18`、`worker/claim.py:95–131`；插件 `k8s/base/deployment-worker.yaml:22`、`deployment-api.yaml:13–28`；`fq/api/manual_ops.py:30–40,84–96,114–118`；`core/portfolio/reader/accounts.py:906–918,968`。

queue-summary=0 后仍可有入队和认领；当前 worker 没有停止认领、完成当前 dispatch 后再退出的协议，SIGTERM 也没有相应处理。缩到 0 可能在业务 commit 后、mark_done 前中断。扩回 1 不能继续那次执行，只能等 7200 秒 stale 回收。DESIGN.md:448 的“业务写是 upsert，所以不丢数据”还遗漏了设计自己保留的无 exec_id 且无法合成键的普通 INSERT：重跑会多插一份。

API 的 trigger/upload 是同步写入，审计 job 创建失败时仍会继续处理，所以 running=0 不是可靠的活跃请求计数。API 滚动退出宽限只有 30 秒，而 IB 请求本身可持续更久。Python API + Rust worker 的功能互通测试，不覆盖旧 API Pod 正在执行请求时被终止的情况。回滚时继续允许新的 Rust 手动写入，还会扩大正在处置的错误范围。

**最小修法：** 先建立可验证的“停止新认领/新同步写请求”入口，等待已有业务事务、审计收尾和活跃 API 写请求完成，再缩容和替换；读 API 可继续服务。无法安全排空的 running/未知提交状态单列处理，不以重跑必然幂等兜底。演练必须包含认领竞态、commit 后尚未 mark_done、超过 30 秒的手动请求、审计行创建失败和缺业务键的 INSERT。Owner 可以选窄范围写入口维护窗，或实现显式 drain 协议；单独保持 RollingUpdate 不能替代这一步。

### R2-A6 · 退役会提前销毁修复证据，且“错误最多活 1 天”覆盖不到手动写入

**设计：** §2.2，DESIGN.md:241,245；§5.4–5.7，DESIGN.md:460,473–484；D-R11，DESIGN.md:601；§九，DESIGN.md:575–576。

**代码：** `fq/api/manual_ops.py:84–96,114–118`；`core/portfolio/reader/accounts.py:1162–1178,1348–1374,1425–1446`；`core/persistence/postgres/commissions.py:108–113`。

§2.2/§5.6 要把案例保留到退役后 30 天，但 §5.7 和切片 10 在观察 5 个交易日后就删除录制卷。这会删除 before/after、私有差异和对账证据，Python 镜像仍在也无法完成 D-R11 的按案例修复。

API 手动 trigger/upload 明确不录，切换后却仍可写相同的三张表。反向重放因此不能保证这些写入在一天内被发现，也拿不到它们的 before。“A 层测试过”不能替代上线出现问题时的恢复证据。修复中的“现值等于 Rust 写后”还必须在实际 DML 的同一事务中原子校验；dry-run 时相等、审批后直接 UPDATE，会覆盖其间的 Ledger/TWS 更新。

**最小修法：** 分开“停 Python 生产进程”“停重放/录制”“销毁证据”三个时间点，保留 PVC 或经验证的等价私有归档到明确日期、未结事故关闭之后。观察期的手动写入选择临时受控暂停，或另加安全取证；若仍不录，写明它只能走 Owner/备份处置，删除“一天内全覆盖”的保证，并演练此分支。实际修复采用事务内锁定重查或带完整旧值条件的原子写，检查影响行数和跨表原子性，审批不能替代并发保护。

### R2-A7 · 隔离模板只声明 Egress，无法落实“仅 Prometheus 可入站”

**设计：** §2.6，DESIGN.md:297–310；§4.1，DESIGN.md:391–398。

**代码：** 插件 `k8s/base/network-policy.yaml:1–30`；`fq/worker/health.py:21–43`；`fq/worker/loop.py:123,128,185–186`。

修订正确地换了 part-of 标签，避开生产的 data/443 出站放行；但新策略明确写的是 `policyTypes: [Egress]`。这不能建立入站隔离，后面的“入站只放 Prometheus 到 metrics”没有对应的 Ingress 策略契约。原插件策略本来就写着 ingress unrestricted。拒绝出站连接也不能阻止进程响应别人发起的入站请求。

这条边界对私有数据有效性很重要：生产 worker 的 health 监听 `0.0.0.0`，能返回 `last_error` 原文；重放侧还会持有完整数据的 Postgres。不是断言尚未实现的引擎一定会启动 health，而是现稿既未禁止它，也未把 PG 限为回环/socket。日志金丝雀只扫描列出的出口，不验证其他 Pod 能否读取这些端口。

**最小修法：** 显式实施 Ingress + Egress 隔离，入站只开放固定 metrics 端口及明确的 Prometheus selector；PG 仅监听本 Pod 回环或 Unix socket，重放进程禁止启动生产 health/API。渲染检查要检查这几项；上线验收另有跨 Pod 连接拒绝的负例。金丝雀继续保留，但不能作为网络隔离已经成立的证明。

## B · 应修正或后置

### R2-B1 · 第一块可后置的工作：减少工具产品化，保留证据和硬门槛

**设计：** §2.3，DESIGN.md:249–259；§3.1，DESIGN.md:323–325；§5.6–5.7，DESIGN.md:476–484；§九，DESIGN.md:567–581；§11.3，DESIGN.md:657–665。

**代码：** `fq/client/flex_client.py:242–436,439–704`；`core/persistence/postgres/commissions.py:108–113`；插件 `Makefile:3–5,16–24`；`platform/api/internal/agentrt/store/repos.go:14–32,87–95`。

| 可移后 | 第一块保留什么，为什么不重开 A |
|---|---|
| 自动“真数据形状抽取→生成器”的完整工具 | 先手写公开合成向量覆盖 Q1–Q24、鉴权、回退及已发现差异；私有 B 层仍用真输入和真实生产 before/after。形状工具是增加夹具的便利，不是真实业务对照的替代品。 |
| 通用 `flex-replay repair` 自动修复命令 | 保留证据、Python 可重复重放、差异计算、备份路径；出现问题时由 Owner 审批逐案修复脚本，脚本具备 R2-A6 的原子条件。不得把它简化成“回滚进程后等自愈”。 |
| 下一服务可直接复用的 SDK、模板包装、通用台账框架 | 本块只做 Flex 的受测模块和案例格式；实际用到的隔离模板、比较器、对账及硬 lint 不后置。 |
| 删除 Python 源码、pyproject、旧测试和相关 Agent Setup | 先下线 Python 生产进程，保留离线基准与恢复能力。立即删这些文件还会撞上 §六、§七仍要求的 Python 安装和 pytest；真正删时一起迁移 CI/agentd，不要暗含第二次平台发布却宣称只接线一次。PVC 销毁必须服从 R2-A6 的保留期。 |

已后置的 cargo-chef、缓存 PVC、大范围 fuzz、core 公开接口清理继续后置。三 crate 可以先保持，不值得再为减少一个 crate 重做架构。不能后置：Python 先通过真实 B 层、Rust 同组对照、有效的 10 个交易日、隐私隔离、可靠对账、Agent 缺库必败、单条完整 CI 和回滚演练。26 个 agent 日只是估计；先做最小 Python 录制/重放试验再重估，不能用压缩验收天数来达成工期。

### R2-B2 · 切换须改最终镜像变换器；仅改 Deployment 的 image 会被旧 newTag 覆盖

**设计：** §5.3、§5.5，DESIGN.md:453–466；§六，DESIGN.md:490–491。

**代码：** 插件 `k8s/base/kustomization.yaml:25–28`、`deployment-api.yaml:31–33`、`deployment-worker.yaml:25–27`。

base 的 images 仍把 `bifrost-flex-query` 改成 registry 路径的 `0.13.2`。本轮本地最小渲染已验证：把 Deployment 改成短名 `bifrost-flex-query@sha256:…`，保留此变换器，输出仍是 Python `:0.13.2`；若 args 已换 Rust，会起不来。改为不再匹配的完整镜像名可以避开，但设计应直接明确 digest 的唯一权威位置，删除/替换旧 newTag。§5.5 要求的最终模板启动演练能发现它，因此列 B；在演练前就应加渲染断言，检查两个进程最终 digest 与 command/args，revert 后也同样检查。

### R2-B3 · 两套回退的主要修复正确，再补异常类型边界

**设计：** §1.3，DESIGN.md:83–102；§3.3，DESIGN.md:348。

**代码：** `fq/orchestration/trades.py:64–110,218–222`；`fq/orchestration/transactions.py:267–297`；`fq/client/flex_client.py:145–150,213–219`。

表中的“报错”应明确为这些分支捕获的 `ValueError`。HTTPError/URLError 在客户端部分路径被转换/重试，但直接的 TimeoutError、其他 I/O 异常或 SendRequest XML ParseError 不都经过这一转换。合成探针确认：trades 默认期抛 TimeoutError 时直接退出，不再请求 p=5；cash 也直接向外抛，不返回 `_fetch_chunk` 的错误字符串。补这类用例及多个查询条目中的中断行为，避免 Rust 将所有错误统一放进“继续回退/继续下一条”的分支。原 A2 的 cash 空成功不回退、最多两次、无 p=5 已关闭。

### R2-B4 · 调整执行顺序与验收预算，避免框架未上锁就上线或冷启动先超时

**设计：** §六，DESIGN.md:493–501；§七，DESIGN.md:521–538；§九，DESIGN.md:567–570。

**代码：** 插件 `k8s/cicd/pipeline-build.yaml:37–64`；`platform/api/internal/agentd/setup.go:34–35,112–114`、`api/internal/agentrt/store/repos.go:203–205`、`api/internal/agentd/businesskeys.go:19–22,75–91`。

`coreRevision` 与构建钉子修复被排在切片 3，录制器 0.14.0 却在切片 2 上线。应把 Python 构建的插件 SHA/core SHA 分离与校验提前到切片 1–2；否则仍需额外解释这次基准发布怎样避开旧的同 revision 克隆问题。

冷启动不能只量 Verify 的 900 秒：现有 **Setup 总限时 600 秒**，现在还要装 Python 并完整 `cargo build --workspace --all-targets`，可能在进入 Verify 之前就失败。给 Setup 和 Verify 分别记录耗时/退出原因，再决定只预取、只编依赖或调整受控限时。`CARGO_*` 要加 AllowedEnv 和 homePins；当前 stageKeyless 的业务键 deny 规则并不匹配它们，无须为此放宽业务键边界。A8 的主机二进制更新、路径钉住、manifest-path 和缺库必败方向已闭合。

## A1–A9 关闭表

| 上轮 A | 状态 | 修订设计与固定代码核对 | 本轮剩余 |
|---|---|---|---|
| A1 配置写鉴权 | **closed** | §1.6，DESIGN.md:153–167；`fq/api/deps.py:13–57`、`config_summary.py:134–167`；普通写/配置写的空令牌分歧、网关头、header 优先级一致。28 组合成探针通过。 | 路由级 HTTP/库不可用顺序尚未集成实测；不能把单函数探针算成全部 HTTP 验收。 |
| A2 现金回退 | **closed** | §1.3，DESIGN.md:83–102；`fq/orchestration/trades.py:64–110`、`transactions.py:191–202,267–297`；现金无 p=5、空成功不回退、多段禁止回退成立。 | R2-B3 补清异常类型。 |
| A3 私有错误泄露 | **closed with a new hole** | §2.3/§2.6，DESIGN.md:249–259,297–310；原 `core/portfolio/reader/accounts.py:934–940,1255–1264` 和 `fq/orchestration/transactions.py:256–258` 的日志/异常出口已有具体隔离与金丝雀方案。 | R2-A7：网络入站与可能的 health/PG 读取出口。生产 Python 旧日志仍是明确接受到退役的遗留范围，未误报成已修。 |
| A4 录制边界 | **not closed** | §2.2/§2.4/§2.5，DESIGN.md:222–239,265–289；接缝可达性已由 `core/monitor/reader/write_support.py:62–76`、`accounts.py:686,1159` 核实。 | R2-A1、R2-A2：录制故障会污染事务；重放初态/时间规则和失败案例验收仍有缺口。 |
| A5 主键、created_at、重复行 | **closed**（原则） | §1.4/§2.4，DESIGN.md:110,265–267；已有行不再豁免主键/created_at，保留多重集合；`core/portfolio/reader/accounts.py:269–302,859–918`、`brokerage_ddl.py:100,308,383` 证明这些约束必要。 | R2-A2 要落实 SQL 时钟、新行计数和序列权限不足的处理；不得把 §10.2 的降级当默认通过。 |
| A6 交易日与完整性 | **not closed** | §4.2–4.3，DESIGN.md:411–430；NYSE 日历、周一不重复计天已纠正，`research/src/bifrost_research/orchestration/schedules.py:108–125` 支持周六收周五的解释。 | R2-A3 独立分母仍缺；R2-A4 候选身份漏生产输入。 |
| A7 切换与回滚 | **not closed** | §5，DESIGN.md:445–484；完整 digest/args revert、API RollingUpdate、数据修复分离均正确，对上两个 Deployment 和 `core/persistence/postgres/commissions.py:108–113`。 | R2-A5 未真正 drain；R2-A6 提前删证据、手动写覆盖及修复并发边界。R2-B2 提醒最终镜像变换器。 |
| A8 Agent 接线 | **closed** | §七，DESIGN.md:518–536；`platform/api/internal/agentd/testdb.go:190–204,243–248`、`confine.go:148–165`、`setup.go:170–178`、`executors.go:37–58` 均已被设计覆盖：同版本 agentd、Cargo pins、manifest-path、缺库红、全新尝试反例。 | R2-B4 的 Setup 600 秒须纳入冷启动验收；06 实机、工具链组件、socket 数据库连接尚未验证。 |
| A9 CI 合入闸门 | **closed** | §六，DESIGN.md:499–505；`infra/scripts/release/ci_gate.py:63–77`、`push-main.sh:113–117`、`trigger-trade-ci.yaml:220–245`。一条全检查流水线、仓库→应有流水线映射、两个列表和精确 SHA 反例覆盖原洞。`scripts/k3s/install-ci-webhooks.sh:22–26` 已含插件，无需另发明一条 webhook。 | 尚未执行真实 CI；假结果检查只能证明预期判定，不证明待写流水线已经接上或全部步骤未被 skip。 |

## 最小可行顺序与交 Owner 的选项

建议保留四个验收段：① 固定 Python/core 血缘、最小 CI 与合成契约；② 小范围事务内录制、故障隔离和 Python 真实案例自复现；③ Rust 全服务及 Agent 接线，同一组对照通过；④ 完整对账的 10 个交易日、drain/revert 演练、切换与观察。第②段先证明 R2-A1/R2-A2 可做，再投入 Rust 主体。R2-B1 的工具产品化和源码清理移后，业务验收不移后。

最后一轮仍未闭合的事项，交 Owner 选择如下；不是请求再开第三轮设计复核：

| 决定 | 推荐 | 其他可行选项及代价 |
|---|---|---|
| D-R10 录制接缝（R2-A1/A2） | 保留代理接缝，但先交可运行的隔离/重放小样和上述正反例，未过不发录制器。 | 改 core 正式钩子；多一个仓库及接口发布，但仍要证明相同事务语义。事务外快照不能作为回退选项。 |
| 验收证据（R2-A3/A4） | 增加独立最小作业快照，先用完整生产构建身份，减少身份白名单维护。 | 实现完整的分层构建证明与不可变 attempt 清单；更复杂，第一块没有必要。只有 cases 的方案不能签 10 天。 |
| 切换（R2-A5） | 窄范围暂停新写入口，保留读服务，可靠排空后切换。 | 增加完整在线 drain 协议，工程量更大；两种都要包含 API 同步写入。 |
| D-R11 恢复与退役（R2-A6） | 保留证据和离线 Python，先用 Owner 审批的逐案修复，自动 repair CLI 后置。 | 本块完成通用 repair 工具及其并发/跨表测试。两种都不得提前销毁案例。 |
| 隐私模板（R2-A7） | 补齐入站隔离、PG 回环/socket、禁止生产 health/API，再做负例验收。 | 不能仅以日志金丝雀或断出站替代这条边界。 |

## 已做与未做的检查

已做：读取四份材料，按指定提交交叉核对接缝、核心写事务、其他写入者、队列/补跑/freshness、鉴权、回退、消费者、Deployment/NetworkPolicy、构建/CI 和 agentd 接线。仅用 Python 标准库从固定源码抽取函数，执行 28 组鉴权组合、6 个 trades 回退案例、6 个 cash 案例、6 个 fallback 值、6 个分类案例，均通过。复现了现行 ci_gate 接受其他已知流水线成功的反例；在隔离的预期流水线模型中验证了同 SHA 成功/缺失/失败/别的 SHA/别的流水线五种结果，**这不是待实现 ci_gate 的测试通过声明**。另构造了“额外作业完全漏录而可见案例不变”的纯数据反例。

只用本地 `kubectl kustomize` 对临时的合成清单做了一次渲染，确认旧 newTag 覆盖短名 digest；没有连接集群，临时目录已清理。未运行仓库命令中的部署、同步、安装脚本。

按 BRIEF 限制，未做：任何网络、MCP、SSH、数据库或集群访问；真实 Flex 报表/账户行/Secrets/.env 读取；真实 A/B 业务重放、数据库事务/锁/序列/故障注入实测；线上 schema、权限、时区、PVC/NFS、准入、网络隔离实效、镜像保留或资源基线核验；06 冷启动；真实 CI、镜像构建、10 个交易日并跑、切换和回滚演练。本机 PATH 未发现 cargo/rustc，未跑 Rust/clippy/sqlx。上述未做事项均不计为通过；数据库及隔离问题是代码和设计交叉推导，未冒充现场复现。

未修改被审仓库、未提交、未写本目录及共享缓存以外的位置。报告不含真实账户内容。

先修：R2-A1 录制故障污染事务、R2-A2 重放起点和判等规则、R2-A3 独立尝试分母、R2-A4 完整候选身份、R2-A5 真正排空写入、R2-A6 修复证据与覆盖、R2-A7 入站隐私隔离。
END OF REPORT
