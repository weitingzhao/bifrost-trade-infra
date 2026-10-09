# LANE-W33C — 发版链去掉管理员 kubeconfig（W-33 第 2 步的第二道）

登记：`agent-config/WORK.md` 的 W-33（匹配 LANE-W33C）。依据：`LANE-W33B.md`「〇」第 4 条（Owner 2026-10-09 定）。本道是第 3 步（Mac 上的 Agent 换只读 kubeconfig）的前提：今天的发版链有好几处用管理员 kubeconfig 直接写集群，换只读以后都会断。

> **派给 Cursor 之前，先由 Owner 定下面「〇」节的四件。** 定了以后把「待定」改成「已定」，删掉没选的选项。

仓库与分支（都从最新 origin/main 开独立 worktree）：

- bifrost-platform · `cursor/w33c-platform`
- bifrost-trade-infra · `cursor/w33c-infra`

先读：

- `LANE-W33B.md` 和 `reports/LANE-W33BR.md`（含「Claude 验收」）；
- `bifrost-trade-infra/docs/RELEASE.md`；
- `scripts/release/release.sh` 的头注释；
- `agent-config/claude/skills/research-release/SKILL.md`。

## 〇、要 Owner 定的四件（待定）

### 1. PROD 的 pinned run 改成什么形式

**问题**：现在 PROD 的 pinned run，是把 `pipeline/bifrost-deliver-prod` 整份内联成 `pipelineSpec`，再把 6 个 clone 任务的 revision 改成 STG 跑过的 SHA，由 release.sh 用 kubectl 直接建。这条路有两个毛病：

- 第 3 步之后，Agent 没有在 cicd 建 PipelineRun 的权限；
- TD-271 的准入策略禁止平台身份建内联 spec 的 run。所以这条路也不能简单地搬到平台上。

**选项**：

- **A（推荐）Pipeline 加逐仓参数**：`bifrost-deliver-prod` 增加 6 个参数 `coreRevision`、`workerRevision`、`apiRevision`、`frontendRevision`、`uiRevision`、`infraRevision`，6 个 clone 任务各用自己那个。pinned run 变成「`pipelineRef` 加参数」，经平台 `start_pipeline_run` 起。PROD 是 C 级，要审批，正好对应「PROD 发版要 Owner 点头」。准入策略不用放宽。
- B 平台新增专用动作「从 STG run 生成 pinned run」，由平台去内联，准入策略给这个动作开例外。这会削弱 TD-271 刚堵上的那条路。
- C 第 3 步之后，PROD 的 Trade 发版由 Owner 亲手跑 release.sh。

### 2. 发布窗口由谁持有

**现状**：

- 窗口的权威是本机文件 `~/.bifrost-release/window.json`；
- `release.sh hold` 再用 kubectl 把它写成 ConfigMap `cicd/bifrost-release-window`；
- 平台的 `start_pipeline_run`，以及插件构建、Dagster、deliver-research 流水线的第一个任务，都读这个 ConfigMap。

**选项**：

- **A（推荐）窗口归平台**：平台新增 `GET`、`PUT`、`DELETE /api/v1/delivery/release-window`，B 级，用 operator 令牌。平台本来就有 cicd ConfigMap 的写权限。`release.sh hold / window / --clear` 改调这几个接口，本机文件退役。这样多台机器、多个会话看到的是同一份窗口。
- B 本机文件仍是权威，平台接口只负责写 ConfigMap 这一份镜像。

### 3. Gitea 镜像同步交给平台（顺带修 TD-273）

**现状**：

- `release.sh` 经 `scripts/k3s/bootstrap-gitea-mirrors.sh` 同步镜像。它要读 `gitea-bootstrap` Secret 里的 Gitea 管理令牌，第 3 步之后读不到；
- `plan_manifest` 也会因为镜像还没同步，拿不到刚推的提交（TD-273）。

**选项**：

- **A（推荐）平台新增同步接口**：`POST /api/v1/delivery/mirrors/sync`，B 级，参数是仓库名列表（只接受白名单里的仓库，白名单在配置里）。平台调 Gitea 的 `mirror-sync` 接口，再轮询到目标提交出现为止。平台本来就能读 `gitea-bootstrap`。release.sh 和 `plan_manifest` 都用它：`Plan` 起 run 之前先同步。
- B 只修 `plan_manifest`（TD-273），release.sh 的镜像同步留给 Owner。

### 4. `start_pipeline_run` 带任意参数

**现状**：

- 平台只认 `revision` 和 `tag`，而且按流水线名写死了对应关系（`delivery/service.go` 的 `pipelineRunParams`，里面直接写着 market-data 的镜像仓库名）。这本身违反「平台不认识具体应用」；
- 1-A 要求能传 6 个 revision。

**选项**：

- **A（推荐）通用参数**：`start_pipeline_run` 增加可选的 `params`（名字到字符串的映射）。平台从集群读这条 Pipeline 声明的参数，名字没声明过的拒绝。值只允许 `^[A-Za-z0-9._/:@-]{1,200}$`。`revision`、`tag` 和现有的写死对应关系保留一版，兼容现有调用方。MCP 工具同步加 `params`。
- B 只为 `bifrost-deliver-prod` 再写死 6 个参数，平台继续认识具体流水线。

## 事实（2026-10-09 实测；platform main `e2d5137`，infra main `9def22c`）

- **release.sh 里的管理员写操作**：
  - `window_publish` / `window_unpublish`：`kubectl create configmap … | kubectl apply`、`kubectl delete configmap`（:92、:105）；
  - STG：`kubectl create -f pipelinerun-deliver-stg.json`（:439）；
  - PROD：`kubectl create -f <pinned spec>`（:450、:452），spec 由 `prod-pinned-from-stg.sh` 内联生成；
  - 镜像同步：`bootstrap-gitea-mirrors.sh`（:207），读 `gitea-bootstrap` Secret，并做端口转发。
- **只读、不受影响的部分**：CI 检查（`kubectl get pipelineruns`）、`deliver_free`、`release_tool.py`（只有 `kubectl get` 和 HTTP GET）、`tag_core_release.sh`（git）。
- **`release-check.sh`** 跑 role-matrix 对账用的是 `--via kubectl`（`kubectl exec` 进主库）。`check_role_matrix.py` 本来就支持 `--via psql`，可以改用 `agent_reader`（10-09 起可用，见 AGENT_FACTS）。
- **DB 步骤**：`db_steps_gate` 只打印待执行的步骤，由 Owner 在自己的终端执行，脚本本身不执行。
- **插件**：
  - 构建流水线 `bifrost-build-{market-data,flex-query,ib-gateway}` 已在平台 `pipelineTakesRevision` 里；
  - 部署（`kubectl apply -k k8s/base`、ib-gateway overlay）可以改用 `apply_manifest`：插件仓库的 `k8s` 在白名单里，级别 C；
  - ib-gateway 现在从镜像仓库拉（digest 钉死），不再需要 SSH 到节点导镜像。
- **research**：
  - deliver-research 和 Dagster 构建已经走平台的 `start_pipeline_run`；
  - `k8s/orchestration/dagster.yaml` 改用 `apply_manifest`（在白名单里，级别 C）；
  - ddl-apply（`k8s/jobs/ddl-apply.yaml`，Argo 跳过）是 PROD DDL，走 `owner_run_command`。
- **其他**：
  - TD-262 的修复（MCP 带 `who`）已在 platform main（`634e305`），台账还写着「未合」。不在本道范围，Claude 另报；
  - 平台的 `start_pipeline_run` 对 kaniko 流水线会自己加 `taskRunSpecs`（`tekton-deliver`），准入策略放行。

## 要做

按〇节的推荐写。Owner 选了别的选项时，Claude 先改这一节再派道。

### 一、platform

1. **`start_pipeline_run` 带参数（〇第 4 条）**：
   - 请求体加 `params`；
   - 校验：名字必须是该 Pipeline 的 `spec.params` 声明过的（从集群读），值匹配上面的字符集；
   - `pipelineRunParams` 的旧逻辑保留：调用方没传 `params` 时照旧，两者同时给了同一个名字时以 `params` 为准；
   - MCP 工具加 `params`；
   - 审批单里显示全部参数，`params_hash` 也覆盖它们。
2. **发布窗口接口（〇第 2 条）**：
   - `GET /api/v1/delivery/release-window`（A 级）；
   - `PUT`（B 级，体内是 `what`、`who`、`reason`、`ttl_minutes`）：已有别人持有时拒绝，同一个 `who` 重复 PUT 视为续期；
   - `DELETE`（B 级，只有持有者的 `who` 能删）；
   - Owner 的 `--clear` 用 `DELETE ?force=1`，C 级，走审批；
   - 写的就是现在的 ConfigMap，格式不变，流水线不用改；
   - 窗口过期后视为空。
3. **镜像同步接口（〇第 3 条）**：
   - `POST /api/v1/delivery/mirrors/sync`（B 级），体内是 `repos` 列表加可选的 `commits`（仓库到 SHA）；
   - 仓库必须在配置的白名单里，复用 `actuation-policy.yaml`，加一个 `mirrors.repos`；
   - 先调 Gitea `mirror-sync`，再轮询 `git/commits/<sha>`，最多 90 秒，返回每个仓库是否到位；
   - `workactions.Plan` 起 run 之前，先对这个仓库和提交调一次同步（TD-273）。
4. **防线**：
   - `params` 校验：未声明的名字、非法字符、超长都拒绝；
   - 窗口：并发 PUT 只有一个成功，非持有者 DELETE 被拒，过期后视为空；
   - 镜像同步：用一个假的 Gitea 测，不在白名单的仓库被拒；`Plan` 一定先同步再起 run。

### 二、infra

1. **`bifrost-deliver-prod` 加逐仓参数（〇第 1 条）**：
   - 增加 6 个 `*Revision` 参数，6 个 clone 任务各用自己的；
   - `revision` 参数保留，只用于展示和标签；
   - `prod-pinned-from-stg.sh` 改为输出 6 个 SHA 的 JSON，不再生成内联 spec；
   - `pipelinerun-deliver-stg.json` 里平台不会自己加的设置（超时、工作区等），核对清楚，改由平台起 run 时一并带上，或者写进 Pipeline 的默认值。逐项写进报告。
2. **release.sh**：
   - `hold`、`window`、`--clear` 改调平台的窗口接口；本机 `window.json` 退役（保留读取一次，用来迁移）；
   - `hold` 和 `release.sh stg|prod` 运行期间，每分钟续期一次（`ttl_minutes` 设 5），退出时 DELETE。进程被杀的话，窗口 5 分钟后自然过期。现在要 Owner 手动 `--clear` 的残留锁，以后基本不会再出现；
   - 镜像同步改调平台的同步接口；
   - STG 改调 `start_pipeline_run bifrost-deliver-stg`，B 级，直接返回 run 名；
   - PROD 改调 `start_pipeline_run bifrost-deliver-prod`，带 6 个 SHA 和 `who`。拿到 `appr_…` 后打印「等 Owner 批准」，轮询 `GET /api/v1/approvals/<id>`（viewer），执行后从结果里取 run 名，再照旧跟踪；
   - 令牌：平台的 operator 令牌和 viewer 令牌从 `.env` 读，经权限 600 的 curl 配置文件传，不出现在命令行，也不打印；
   - `--dry-run` 打印的是要调的接口和参数，不再打印 kubectl 命令。
3. **`release-check.sh`**：role-matrix 改为 `--via psql`，用 `agent_reader`（读 `~/.pgpass`）。读不到时明确报错，不退回 `kubectl exec`。
4. **DB 步骤**：仍由 Owner 执行。`db_steps_gate` 对 PROD 的待执行步骤顺带提一张 `owner_run_command`（命令写原样，原因写步骤 id），打印单号。Owner 批准后用 `owner-run.sh <id>` 执行，执行后 `release.sh db-done` 照旧。
5. **文档**（两侧同步，bump parity-id）：
   - `docs/RELEASE.md`；
   - `agent-config/{claude,cursor}/skills/research-release/SKILL.md`：窗口、镜像同步、`dagster.yaml` 改用 `apply_manifest`、ddl-apply 改用 `owner_run_command`；
   - 插件发布步骤写在哪里就改哪里（先 `grep -rn "pipelinerun-build-\|apply -k k8s/base" agent-config docs`）：构建用 `start_pipeline_run`，部署用 `apply_manifest`。
6. **防线**：
   - release.sh 的测试（照 `test_window_decision.py` 的写法）：脚本里没有 `kubectl create`、`kubectl apply`、`kubectl delete`、`kubectl exec`，也没有 `bootstrap-gitea-mirrors.sh`；
   - `prod-pinned-from-stg.sh` 的输出没有 `pipelineSpec`；
   - 一个静态检查：发布类 skill 和 RELEASE.md 里不再出现 `kubectl create -f … pipelinerun`、`kubectl apply -k k8s/base`；
   - RATCHETS.md 登记。

## 门禁

- platform `api/`：`go build ./... && go vet ./... && go test ./...`；`mcp/platform`：`npm test`；
- infra：
  - `python3 -m unittest discover scripts/release`；
  - `bash scripts/release/release.sh stg --dry-run`、`bash scripts/release/release.sh prod --dry-run --from-stg <最近一次成功的 STG run>`：只读，打印的是平台调用；
  - `kubectl kustomize` 两个 platform overlay；
  - `python3 scripts/check_admission_guards.py`；
  - `bash agent-config/scripts/check-agent-config-parity.sh`；
- **这一道必须真跑一次**（LANE-W33B 的教训：流水线只做静态检查，上线后 3 个 bug 全是真跑才暴露）。报告里写「上线后由 Claude 执行的真跑清单」，Cursor 不执行：
  - STG Trade 发一次；
  - 用新的 pinned 形式发一次 PROD（等 Owner 批）；
  - 插件构建并部署一次（挑一个有改动的插件，或者重发当前版本）。

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33C.md`，格式照 README：

- 每节写：改动（仓库 · 分支 · 完整 SHA）、防线、门禁、验收、要 Owner 批的、后续；
- 附「`pipelinerun-deliver-stg.json` 与平台起的 run 的逐项对照」；
- 附「上线顺序」。参考：
  1. 合 platform；
  2. STG 发版；
  3. PROD 发版（审批）；
  4. 合 infra 的 Pipeline 改动（deliver-prod 加参数；不归 Argo 管，要 apply：Owner 批）；
  5. 合 release.sh 和文档；
  6. 真跑清单。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

注意：本道改的就是 `release.sh window`。新版合进去之前，照旧用旧版检查。

## 不在本道

- 第 3 步：Mac 上的 Agent 换只读 kubeconfig；管理员凭证搬到 Owner 专用目录；preflight 按路径拦。
- W-31 的发布队列（排队、规则集自动批准）。本道只做到「发版不用管理员凭证、每个 run 都经平台、进审计」，审计覆盖率的验收归 W-31。
- TD-272（tekton-trigger）。

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义（删除已退场功能的调用方除外；新增接口只走现有的审批流程）。
- 不发版、不 apply、不写数据库、代码不推 main。
- 不碰 `scripts/agent-guard/`（preflight 闸门）。
- 暂缓、不在瘦身范围：TWS 自动重启、交易区迁移、网络分区。
