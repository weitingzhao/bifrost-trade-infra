# 0 底座 / 0.1 解耦 章程（在跑的席位，2026-11-15，席位自己写）

标记：【量】= 读 `bifrost-platform` main（`cceff576`）、PROD 库或集群得到；【推】= 推断。

## 1. 管哪块（坏了叫它）
- **底座两个包**【量】：`api/internal/agentrt/eventlog`（事件、哈希链、事务、词表引擎、outbox）和 `api/internal/agentrt/actor`（写入者、令牌持有、幂等键）。
- **`agentrt/store` 这个大包本身**【量】：约 1.5 万行，还没搬走的都归这里兜着，直到搬进各自的领域包；已搬出的 `agentrt/coord` 暂由这里维护，`agentrt/evidence` 归 CI 线。
- **迁移**【量】：`api/internal/agentrt/migrations/`（现到 0021）和 PROD、STG 的 `agentrt` schema（31 张表）的删改。新表由提出的领域设计，落迁移和删表在这里。
- **包之间的墙**【量】：`api/internal/codeguard`、`repoguard` 两个守卫包，`bifrost.units.yaml` 里自己维护的包的输入声明（每个包的声明归维护那个包的线，裁第 3 条）。
- **旧物**【量】：`biz-align/legacy-inventory-2026-11-15.md` 那张盘点表和按它删。
- **platform 仓库里没有别的线认领的代码**【裁：主统筹 11-15，`duty/charter-overlaps-rulings-2026-11-15.md` 第 3 条】：默认归这里；CI 线章程第 1 节列的包归 CI 线。
- **代管**【裁，第 2、10 条】：`api/internal/agentthreads/`（线程在线，归领域 2，它转正前由这里代管）；store 里 external-work 和在线那组（搬出后归领域 2）、计划那组（搬出后归领域 1），搬之前和两个领域转正前由这里维护。
- 不管：规则引擎和发布判定（CI 线）、流水线清单（CI 线）、界面的新功能（各领域）、Trade 五仓和 research。

## 2. 对外的口子
- 包间函数：`eventlog.Append / InTx / Declare`，`actor.CheckWriter / IdempotentAs / Register*`；领域包只许经这些进事件表【量：`TestWallsBetweenPackages`】。
- 没有自己的路由和 MCP 工具【量】。
- 文档口子：盘点表、`biz-align/state.md`（现状页）、席位台账。

## 3. 谁用它，它用谁
- 用户【量/推】：所有往事件表写东西的领域包（coord、evidence、store 里剩下的）；CI 线（按声明决定一个提交要跑哪些包）；每个要加表、删表的席位。
- 它用谁【量】：CI 线的回放脚本和 `unit-go-test`（量读数）；值班统筹（DDL 卡的草稿核稿）；领域 5 或 8.2（碰信任锚时的非作者复核）；每日备份（删表的后悔药）。

## 4. 权限
- 自己定自己做【量：已这样做过】：删没人用的代码、搬包、写窄声明、推 `ready/` 进 main、STG 发布；platform 的 PROD 在规则覆盖时直发。
- 机器现在拦着【量】：直接推 main、`git add -A`、kubectl 写、删远端分支（auto mode 11-15 拒过）、PROD 的迁移（只能由执行卡建 Job）；碰信任锚的发布要非作者复核记录。
- 硬边界不碰：交易和钱（D10）、Secret 和令牌、Trade 的 PROD、改签名规则和信任根本身、auto mode 规则；事件表的历史行只追加不改。有数据的删表走卡，先导出。

## 5. 目标和读数
- **主读数**【量，CI 线算】：共同回放读数——最近 150 个提交，每个提交要跑的 Go 测试秒数的中位数。11-14 起点 411 秒，现在 188 秒（`benchmark/scope-replay-2026-11-14.md`）。目标是继续降，下一步要靠切开包之间的引用。
- **第二个数**【量，自己算，每周一次】：没人用的东西还剩多少。11-15 量到 13,717 行（6.4%）、路由 115/240 没被调用、表 14/31 空或停写；到 11-15 上午已删 19,921 行（含 BI）。
- 还没有的数：「一个新领域加一张表、一条路由要碰几个包」。【推】提议用它量解耦做没做成，现在没量。

## 6. 现状和缺口
- 在生产：两个底座包、coord 和 evidence 两个领域包、迁移 0020 和 0021。在 main 和 STG、等上生产：盘点第 1、2 组和删 BI（`cceff576`）。
- 缺口【量】：store 里还有 external-work、在线、规则与事实、计划树没搬出；读六张派活表的 2,560 行和这六张表加 budget_ledger 还在；BI 的 7 张空表还在；`server` 包引用面最大，改一个底层包它就重跑。
- 缺口【推】：没有任何机器检查拦「新代码又往 store 里加」；章程里的归属机器不认，靠人记。

## 和谁有重叠（主统筹 11-15 已裁的写结论）
- **CI 线**【已裁】：platform 代码默认归这里，CI 线章程第 1 节列的包归它；每个包的声明归维护那个包的线。workers 的循环我盘点、它改。
- **领域 2**【已裁】：线程在线归领域 2，`agentthreads/` 转正前我代管；external-work 和在线那组搬出 store 后归它，之前我维护。
- **领域 1**【已裁】：计划那组搬出 store 后归它，之前我维护。
- **工坊线**【没裁】：仓库里讲 BI 和旧流程的文字由谁清；`OWNER_LAW.md` 的行由工坊记。
- **算力线**：迁移 Job、流水线运行的保留期在集群里，我只读、它定。
