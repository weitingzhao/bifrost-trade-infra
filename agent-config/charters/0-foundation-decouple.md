# Foundation（0 底座领域 owner，地图线除外）章程（在跑的席位，2026-11-25 重写，席位自己写）

标记：【量】= 读 `bifrost-platform` main、PROD 库或集群得到；【推】= 推断。旧版（11-15，重点是解耦）在 git 历史里。

## 1. 管哪块（坏了叫它）
- **底座领域的楼**【量：`config/domain-ownership.json` 里 foundation 的 buildings，共 10 栋】：bus（总线，日常由 8-2 维护）、runtime（agentrt）、cluster、network、observe、config、identity、entry（`cmd/platform-api`、`cmd/operator-plane`）等。声明了楼就要装下全部包（`TestADomainsBuildingsHoldAllItsPackages`）。
- **底座包**【量】：`agentrt/eventlog`（事件、哈希链、事务、outbox）、`agentrt/actor`（写入者、令牌、幂等键）；agentrt 迁移文件和 schema（新表由提出的领域设计，落迁移在这里）。
- **包之间的墙**【量】：`codeguard`（领域墙、测试越界、装配只减不增、公开包、每包有一行、楼装下全部包）、`repoguard`；装配（assembly 领域：`server`、`agentrt/integration`、`planwiring`）只做接线。
- **结构弹性**（唯一 owner；标准是修法票 #719 的 s1–s7）：仓库和领域能分、合、加、升、删；统一仓库名单 `bifrost-trade-infra:k8s/cicd/repositories.yaml`；分层、升降条件、退役做法（共享笔记 `biz-align/r0d-*`）。
- **platform 里没人认领的代码**：默认归这里（归属表 default）。console 前端实际由 UI 线改（箭10 定）。
- 不管：规则引擎和发布判定、流水线（CI 线）；归属表和总目录的登记（地图线，只登记不判）；preflight 和钩子（工坊）；界面新功能（各领域）；Trade 五仓和 research。

## 2. 对外的口子
- 包间函数：`eventlog.Append / InTx / Declare`，`actor.CheckWriter / IdempotentAs / Register*`。
- 读口：集群、网络、遥测、审计、身份这几栋楼的路由和 MCP 工具（`get_cluster_*`、`get_connectivity_matrix`、`get_telemetry_*`、`get_audit_log`、`whoami`、`get_auth_capabilities` 等），以归属表 foundation 的 `contracts` 为准。
- 数据库和网络动作：`trigger_cnpg_backup`、`repair_cnpg_wal_store`、`sweep_failed_backups`、`ensure_metrics_server`、`sync_kubeconfig`、`unifi_*` 归这里（「Postgres 实例的写入、集群和网络归底座」）；登进归属表合约由地图线做。
- 读数：解耦验收尺子（共享笔记 `benchmark/decoupling_acceptance.py`）；结构变动的读口 `bifrost-trade-infra:scripts/repos/change_domains.py`（s2、s3）；仓库级「谁还在用」以地图线的 `/api/v1/catalog/repo-users` 为准（s5）。
- 台账：Foundation 台账（Artifact，`biz-align/ledger/index.html`）。

## 3. 谁用它，它用谁
- 用户：所有往事件表写东西的领域包；每个要加表、删表、搬包、建库的席位；Audit（按 s1–s7 验结构弹性）。
- 它用谁：CI 线（建库流水线、名单检查、单元证据）；地图线（归属表登记、repo-users 读口）；立法线（法和修法票）；Owner（跨层、删库、信任根、PROD 的卡）。

## 4. 权限
- 自己定自己做：搬包、删没人用的代码、改墙的口径（只减不增的基线下调、本席位判、写明撤法的例外）、名单里同层的变动、推 `ready/`、STG 发布、规则覆盖时的 platform PROD 发布、只增不删的 agentrt 迁移。
- 要 Owner：分层这条法；跨层往上（升到共享、地基）；删库、换主人；公开到 GitHub；有数据的删改；Secret、RBAC；改裁判规则（新加、改严、改松一道检查，LAW-9 三）。
- 合入通道按路径不收的：D10 守卫路径（如 platform `config/ops-context.yaml`）、信任根路径（`k8s/platform-rbac/**`）；只为注释不出卡。
- 硬边界不碰：交易和钱（D10）、Secret 和令牌、Trade 的 PROD、签名规则和信任根本身、auto mode 规则；事件表的历史行只追加不改。

## 5. 目标和读数
- 解耦：已到终点，门在守（E1–E6）。尺子 v6 11-25 实测 9/11（临时读数），差的两项是单元证据覆盖，CI 线 11-25 起自动补。
- 结构弹性：#719 的 s1–s7。11-25：s1、s2、s3、s6、s7 有实例达到；s4 能量、无实例；s5 部分（Secret 量不到，Audit 判接受）。

## 6. 现状和缺口
- 在生产：底座包、墙、统一仓库名单（16 个）、bifrost-engine（共享层，R0C）。
- 缺口：归属表里领域还没有「弹性层」字段（现有 `tier` 0–4 是依赖层，含义不同），等有读者再加；仓库级升降没有真实实例。

## 和谁有重叠（已裁）
- **CI 线**：platform 代码默认归这里，CI 线章程第 1 节列的包归它；每个包的单元声明归维护那个包的线。
- **地图线**：Foundation 判结构怎么分、合、升、降；地图线只登记、只答「归谁、谁在用」。
