# LANE-W33R 报告

W-33 上 PROD 之前的返工：patrol 状态跨进程读写，以及 PROD platform-api 的 patrol 配置。代码在两条功能分支，未推 main、未合并、未部署、未 apply、未 helm、未写数据库。`api/internal/approvals/` 的审批语义未改。`scripts/agent-guard/` 未改。D10 仍是 BLOCKED。

本道的 api 补丁基于当前 origin/main 的 PROD overlay。`cursor/w33-infra` 上的 PROD overlay（去掉 runner 令牌、待重启 DaemonSet、Grafana）还没进 main。Claude 合并时把两边合在一起。`platform-runner-token.patch.yaml` 仍在 main 上，本道没动它。

STG 不挂技能、不开 patrol 循环。这些缺陷在 STG 上看不见。

没有给 api 加 `CHECKLIST_PROBER`，也没有设 `PLATFORM_PATROL_LOOP`。循环仍只在 `role.RunsWorkers()` 为真时启动。

pre-commit 的 code-health 看到 platform 超长文件 12，基线 13，exit 0。基线没有在本道降到 12：infra 若先于 platform 合并，主检出上的旧文件数会顶破新基线。

## 1. patrol 状态跨进程

### 改动

- bifrost-platform · `cursor/w33r-platform` · `0bf528551b42de7b216e0f5eb0c0284effc16908`
  - `api/internal/statefile/statefile.go`：`Backend` 增加 `Update`。`statefile.Update` 把 mutate 作用在当前内容上再写回。文件后端用同目录 `.lock` 的 flock 包住读-改-写，临时文件再 rename。`Write` / `WriteFile` 语义不变。
  - `api/internal/statefile/k8sstate/k8sstate.go`：`Update` 先 Get，再 mutate，再带这次读到的 resourceVersion 去 Update。冲突或 AlreadyExists 就重新 Get，对最新字节再跑一次 mutate，最多 5 次。`Write` 仍是拿调用方原来的字节重试（last-writer-wins）。
  - `api/internal/patrol/store.go`：`ListRuns`、`LastRun`、`Enabled` 每次 `ReadFile`。`AppendRun`、`UpdateRun`、`SetEnabled` 只走 `statefile.Update`，在 mutate 里改最新内容，并在里面把运行记录截到 `MaxRuns`（200）。没有加缓存。

### 防线

- `api/internal/patrol/store_share_test.go`：`TestOtherStoreSeesAppendedRun`、`TestOtherStoreSeesEnableFlag`、`TestInterleavedWritesLoseNothing`。两个 Store 共用一个假后端。
- `api/internal/statefile/statefile_test.go`：`TestFileUpdateKeepsBothEdits`、`TestUpdateDoesNotWriteWhenMutateFails`。
- `api/internal/statefile/k8sstate/k8sstate_test.go`：`TestUpdateReappliesMutateAfterConflict`。第一次 Update 冲突，期间内容从 `{"n":1}` 变成 `{"n":10}`，第二次 mutate 必须落成 `{"n":11}`。
- 登记在本分支的 `agent-config/RATCHETS.md`（随 infra 分支，不在本报告提交里）。

### 门禁

- `cd api && go build ./... && go vet ./... && go test ./...` → exit 0

### 验收

```bash
git -C /tmp/cursor-w33r/w33r-platform show 0bf528551b42de7b216e0f5eb0c0284effc16908:api/internal/patrol/store.go | grep -n 'statefile.Update\|ReadFile'
```

预期：`read` 里有 `ReadFile`，`edit` 里有 `Update`。`saveLocked` 不再出现。

### 要 Owner 批

无。本道不部署。

### 后续

无。

## 2. PROD api 的 patrol 配置

### 改动

- bifrost-trade-infra · `cursor/w33r-infra` · `c46113e78c2c6fc12b2e4cc543e07395598b3aa9`
  - 新增 `k8s/overlays/platform-prod/platform-api-patrol.patch.yaml`。platform-api 挂 `bifrost-platform-patrol-skills`，设置 `PATROL_SKILLS_DIR=/app/patrol-skills`、`PATROL_MODE=report`、`PATROL_DISPATCH=local`。没有 `CHECKLIST_PROBER`，没有 `PLATFORM_PATROL_LOOP`。
  - `kustomization.yaml` 挂上这个补丁。技能 ConfigMap 仍是带 hash 的名字，api 和 workers 渲染后是同一个名字（`bifrost-platform-patrol-skills-5cf4542gm7`）。
  - `scripts/check_platform_maintenance.py`：PROD api 与 workers 都必须挂技能，三个环境变量必须相等；`CHECKLIST_PROBER` 仍只在 workers；api 不得把 `PLATFORM_PATROL_LOOP` 设成开；STG 仍不挂技能，两个循环开关仍是 off。

### 防线

- `make check-platform-maintenance`（`scripts/check_platform_maintenance.py`）。
- `agent-config/RATCHETS.md` 里原「只有 workers 能挂技能」那一行改成 api 与 workers 共用三值、探测器只在 workers。

### 门禁

- `kubectl kustomize k8s/overlays/platform-prod` → exit 0
- `kubectl kustomize k8s/overlays/platform-stg` → exit 0
- `PATH="/usr/bin:/usr/local/bin:$PATH" python3 scripts/check_platform_maintenance.py` → exit 0，输出以 `ok: PROD platform-api and platform-workers share PATROL_SKILLS_DIR/PATROL_MODE/PATROL_DISPATCH` 开头
- `python3 scripts/check_maintainers.py` → `ok 42 maintainers; static; no-alert 12`

本机默认 `python3` 是 Homebrew 3.14，没有 PyYAML。门禁用的是 `/usr/bin/python3`（3.9，有 PyYAML），`kubectl` 在 `/usr/local/bin`。

### 验收

```bash
git -C /tmp/cursor-w33r/w33r-infra show c46113e78c2c6fc12b2e4cc543e07395598b3aa9:k8s/overlays/platform-prod/platform-api-patrol.patch.yaml
```

预期：有 `PATROL_SKILLS_DIR`、`PATROL_MODE`、`PATROL_DISPATCH` 和 `patrol-skills` 挂载。没有 `CHECKLIST_PROBER`，没有 `PLATFORM_PATROL_LOOP`。

### 要 Owner 批

无。合进 PROD overlay 之后的发版不在本道。

### 后续

- Claude 合 `cursor/w33-infra` 时，把本道的 `platform-api-patrol.patch.yaml` 留在 PROD overlay 里。那条分支的 kustomization 还没有这个补丁。

## 3. Console 文案

### 改动

- 同上 platform SHA。
  - `console/src/lib/environments-catalog.ts` 的 mac-mini-1 / mac-mini-2：职责改成带外 operator-plane、互看、.50 告警中继。
  - `roadmapCatalog.ts` 没有运行时 import，已删除。`k3sBootstrapCatalog.ts`、`k3sArchitectureCatalog.ts`、`environments-catalog.ts` 里指向该文件的三处字符串改成 environments catalog 的座位说明。

### 防线

无新测试。既有 console 测试 683 通过，没有断言旧的 Remediation Runner 句子。

### 门禁

- `cd console && npm run lint && npm test && npm run build` → lint 0 error（3 条既有 warning）、683 passed、build exit 0

### 验收

```bash
git -C /tmp/cursor-w33r/w33r-platform grep -n 'Remediation Runner PRIMARY' 0bf528551b42de7b216e0f5eb0c0284effc16908 -- console/src/lib/environments-catalog.ts console/src/lib/architecture/roadmapCatalog.ts
```

预期：无匹配（文件已删或句子已换）。

### 要 Owner 批

无。

### 后续

- 别的目录（`cicdBootstrapCatalog.ts`、`dualFlywheelVisionCatalog.ts`、`dailyOpsChecklistCatalog.ts`）仍写着 Remediation Runner。本道只改任务书点名的两处座位和零引用的 roadmap 文件。

## 审计（只报告，未改）

`k8sstate.Write`（`k8sstate.go:78`）冲突时用调用方原来的整份字节重试，不重跑编辑。下面这些 store 的写都走 `WriteFile`，不走 `Update`。本道没有改它们。

### checklist

- 写：`prober.go:109` 的 `Merge` → `store.go:113`。`loadLocked`（`store.go:33`）读整份，`saveLocked`（`store.go:64`）整份 `WriteFile`。`SetDispatch`（`store.go:206`）同样，生产代码没有调用方。
- 读：`Get`（`store.go:70`）和 `KPIs`（`store.go:80`）每次重读。HTTP 只有 `GET /checklist/signals`（`server.go:419`）。
- 会丢吗：现在只有 workers 开 `CHECKLIST_PROBER`，api 只读，读得到 workers 刚写的。两个进程同时 `Merge` 时，后写的整份盖掉先写的，冲突重试也不会把两边的信号并进去。

### approvals

- 写：`service.go` 在创建（109–113）、批准（161–194）、拒绝（213–231）、过期（257）时先 `load` 再 `save`。`store.go:72` 把整份列表 `WriteFile`。
- 读：list（127）、get（142）每次 `load`。
- 会丢吗：同一进程内有锁。两个进程（或同一角色的两个副本）同时改同一份时，后写的整份盖掉另一份申请。语义未改。

### cluster/data_clone

- 日程：`Get`（`data_clone.go:336`）每次 `load`（312）。`Put`（343）整份替换后 `WriteFile`（329），后一次 Put 覆盖前一次，这是整份替换。`RecordRun`（367）不先 `load`，改内存里的 `s.cfg` 再写。workers 记下一次运行时，会盖掉 api 在这次进程加载之后写入的日程。
- 上次克隆：`Get`（430）返回内存，不重读。`Record`（436）写内存再 `WriteFile`（427）。api 进程启动之后，workers 写的上次克隆时间它看不见。

### promote

- `LoadTier`（`promote/store.go:55`）每次重读。`SaveTier`（85）把调用方拿来的整份记录 `WriteFile`（98），不与文件里的现稿合并。`AppendHistory`（161）先读（166）再整份写（183）。两个进程各追加一条时，有一条会丢。
- `cycle_store.go` 的 `RecordDeploy`（89）同样：`loadLocked`（44）后整份 `saveLocked`（`WriteFile` 在 72）。

### actuation/audit

- `NewAuditLog`（`audit.go:58`）只在构造时 `load`（206）。`Record`（67）往内存追加再整份 `WriteFile`（230）。`HandleList`（169）列出自己的内存；`AlsoList` 在每次列出时重读另一份路径（180）。
- 路径按角色分开（`server.go:124` 的 `audit-<role>.json`），所以 api 和 workers 不写同一个键。同一角色两个副本写同一个键时，各自的内存加整份覆盖，会丢掉另一副本的记录。自己的文件在进程活着的时候不重读。

### agentdeploy

- `NewStore`（`agentdeploy/store.go:33`）只在构造时读 `last.json`（60）。`Last`（83）和 `Current`（74）都返回内存。这个包没有 `WriteFile`。`handler.go:61` 只读这两项，`current` 在这棵树上没有赋值。别的进程若写了 `last.json`，本进程启动之后看不见。
