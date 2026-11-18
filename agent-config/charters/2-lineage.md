# 领域 2「干活登记与血缘」章程（占位席位，2026-11-14）

标记：【量】= 读 `bifrost-platform` origin/main 得到，带 `文件:行`；【推】= 推断。眼下没有活，下面是接手时的起点。

## 1. 管哪块代码和表
- **external-work 登记**【量】：`api/internal/agentrt/store/externalwork.go`（724 行，`RegisterExternalWork` :349、`ReadOwnExternalWork` :659、`ReadExternalWork` :714）。**没有自己的表**：每条登记是 `agentrt.event` 里 stream 为 `external-work:<id>` 的事件（:314、:597），读的是 `body_json->'external_work'`。
- **线程心跳与在线**【量】：`api/internal/agentthreads/`（handler 331 行、store 104 行）。状态存在**一个文件**里（`store.go:21` `NewStore(path)`，`Update` 带读改写，:83），不进 Postgres。`store/presence*.go`（共约 700 行）名字叫 presence，其实读的是 host/job/control（`presence.go:66-86`，`agentrt.host`），是机房 Agent 主机的在线，不是线程在线——【推】归属要重划，别和线程心跳混。
- **提交血缘**【量】：`api/internal/lineage/`（14 个非测试文件，约 2,200 行：`service.go` 450、`branches.go` 292、`planhistory.go` 230 等）。数据来自 Gitea 镜像扫描（`service.go:26`），读 `Claude-Session` / `Change-Id` 尾注（`trailers.go`），不入库，靠内存缓存。
- 相关：`controller/external_records.go`（把审批、问题等逐条记成事件）。

## 2. 对外露哪些口子
- **路由**【量】：`POST /api/v1/agentrt/external-work`、`POST …/external-work/{id}/events`、`GET …/external-work/{id}`、`POST /api/v1/agent/threads/heartbeat`、`GET /api/v1/agent/threads`（`server/collector_routes.go:20-28`）；`PUT /api/v1/lineage/thread-title`、`PUT …/transcript-title`（`actions/coverage.go:118-119`）；`GET /api/v1/lineage`。
- **MCP 工具**【量】：`get_commit_lineage`（`mcp/catalog.go:210`）；`register_external_work`、`record_external_work_event`（在工具清单里，目录行号未逐一核）。
- **包间函数**【量，来自 domains-review】：store 的 external-work 和在线组 2,490 行，被 store 外用 20 个、被别的组用 24 个。

## 3. 谁用它，它用谁
- 用户【量/推】：Agent 会话（登记、心跳、读血缘判断「这个改动落地没」，见根 `CLAUDE.md` 提交血缘）；Console 的 Work、Commit Lineage 页；统筹/工坊的「看得见」（domains-review 第 57 行）；Stop hook 上报线程标题。
- 它用谁【量】：事件日志和写入者（底座）；Gitea 镜像；计划树（`lineage/planhistory.go`）；**旧派活起名的文件里的 21 个东西**（domains-review 第 35 行：它用别的组 40 个，其中 21 个在那里）。

## 4. 现状与缺口
- 有数据没牌子：领域 2 没有自己的包，登记那组在 store 里和旧派活文件缠在一起；旧流程残留（约 5,000 行）要等它不再用才能删【量，引 domains-review】。
- 没人维护的地方【推】：线程状态是单文件存储，多副本/重启下的一致性没见到保证；`presence*.go` 命名误导，归属不清。
- 已知缺口：external-work 无专属表，查询靠扫事件（`externalwork.go:693` DISTINCT ON），量大后会慢【推】；线程在线只认 Claude 席位（domains-review 第 85 行「信箱只认 Claude」）。
- 建议第一步（等有活）：先把 21 个旧派活依赖列清单，再决定搬进领域 2 还是重写。

## 5. 对外合约的变动记录（底座代记，领域 2 席位是占位）

- **2026-11-17（底座，platform `a6862d84`，迁移 0032）登记事件换了类型**：external-work 的每条记录（登记、心跳、事件）从 `note`（body 带 `external_work` 字段）改成血缘自己的事件类型 `external_work_noted {text, external_work}`，登记在 `bus/registry/ledger/types.yaml` 的 lineage 名下。body 字段没变。
  - 代码现在在 `api/internal/agentrt/externalwork/`：`AppendExternal` 写，`vocab.go` 声明，用 `ExternalNote.Validate` 校验。原来经计划的 note 校验和端口间接校验。
  - 改过的读取方，新旧两种类型都读，旧行不回填：
    - planstore 三处：计划视图的覆盖数、证据、采纳判断；
    - workregistration 三处：identities、spans、snapshot；
    - externalwork 两处：最近一条记录、`NamingOfCommit`。
  - Console 按 body 字段读，不看类型，不用改。
  - 同日搬进 externalwork 的还有：写入（`writes.go`）、记录员导入的落地（`recorder.go`）、`PrepareRecorderImport`、`NamingOfCommit`（交付读「哪个工作点名了这个提交」用）。上面第 1 节里 `store/externalwork.go` 的行号已经过时。

