# LANE-W33R — W-33 返工：patrol 共享状态跨进程读写 + PROD api 的 patrol 配置

登记：`agent-config/WORK.md` 的 W-33（匹配 LANE-W33R）。来源：Claude 10-09 验收 LANE-W33 时发现，PROD 发布前必须修。

仓库与分支（都从最新 origin/main 开独立 worktree）：

- bifrost-platform · `cursor/w33r-platform`（main 已含 LANE-W33，`9a0d1ed`）
- bifrost-trade-infra · `cursor/w33r-infra`

先读：`LANE-W33.md` 第二节、`reports/LANE-W33.md`、本文件。

## 事实（10-09 实测与读码）

- W-33 起，PROD api 自己提供 `/patrol/*`，patrol 循环只在 workers 里跑。两个进程经 `statefile` 共享 patrol 状态：在集群里，`PLATFORM_DATA_DIR` 下的路径由 `statefile/k8sstate` 存成 ConfigMap（TD-196）。
- **问题 1：只在启动时读一次。** `api/internal/patrol/store.go`：`NewStore` 时 `load()` 一次。之后 `ListRuns` / `LastRun` / `Enabled` 只读内存；`AppendRun` / `UpdateRun` / `SetEnabled` 改完内存，再把**整份**写回。所以：
  - api 列出的 runs 停在 api 启动那一刻；
  - api 上 `PUT /patrol/skills/{id}/enable` 改的开关，workers 的循环看不到；
  - 两个进程都整份写回，会互相覆盖，丢掉对方的 runs 或开关。
- **问题 2：写入是盲写。** `k8sstate.Backend.Write` 冲突时会重新 Get，但写回的还是调用方给的同一份数据，没有在最新内容上重做修改，最后写的一方赢。
- **问题 3：PROD api 没有 patrol 配置。** PROD overlay 只给 **workers** 挂了 `bifrost-platform-patrol-skills`，也只给 workers 设了 `PATROL_SKILLS_DIR=/app/patrol-skills`、`PATROL_DISPATCH=local`、`PATROL_MODE=report`（`k8s/overlays/platform-prod/platform-workers-patrol.patch.yaml`）。api 读不到技能定义，`/patrol/skills` 会是空的。另外 api 没设 `PATROL_DISPATCH`，默认走 hybrid：L1 技能会去调 Cursor Cloud，和 workers 不一致，而 `POST /patrol/trigger/{id}` 现在就在 api 里执行。
- STG 的 patrol 本来是关的，这些问题在 STG 上看不出来。

## 要做

1. **statefile 加读改写接口**：
   - 新增 `statefile.Update(path, mutate func(old []byte) ([]byte, error)) error`；
   - k8s 后端：`Get` → `mutate(当前内容)` → 带 resourceVersion `Update`。冲突时**重新 Get、在最新内容上重做 mutate**，有限次重试。不存在时 Create，`AlreadyExists` 同样重试；
   - 文件后端：用文件锁或同目录临时文件加 rename 保证读改写原子，单进程测试够用即可；
   - `Backend` 接口要扩的话，现有实现和测试一起改。`Write` 的语义不变（其他 store 还在用）。
2. **patrol Store**：
   - 读（`ListRuns`、`LastRun`、`Enabled`）每次都从 statefile 重读。可以加不超过 2 秒的缓存，但必须有测试证明另一个进程的写入在缓存过期后可见；
   - 写（`AppendRun`、`UpdateRun`、`SetEnabled`）一律走 `statefile.Update`，在最新内容上做修改，不整份写回内存副本；
   - runs 的上限截断照旧，在 mutate 里做。
3. **测试**：用假后端起两个 `Store` 实例（模拟 api 和 workers）：
   - A 追加的 run，B 能列出来；
   - A 改的开关，B 的 `Enabled` 能看到；
   - 交错执行 `SetEnabled` 和 `AppendRun`，没有丢失的更新；
   - 后端第一次返回冲突时，`Update` 在新内容上重做 mutate。
4. **infra · PROD overlay**：给 platform-api 加一个 patch，挂上 `bifrost-platform-patrol-skills`，env 设 `PATROL_SKILLS_DIR=/app/patrol-skills`、`PATROL_DISPATCH=local`、`PATROL_MODE=report`，和 workers 一致。**不要**给 api 打开 patrol 循环。再加一个检查：渲染 PROD overlay 后，api 和 workers 的这三个 env 相同、都挂了技能目录。放进现有检查脚本（如 `check_ops_context_parity.py`），或者新的小脚本加 make 目标。
5. **审计，只报告不改**：列出其他经 statefile 跨进程共享的 store（`checklist`、`approvals`、`cluster/data_clone`、`promote`、`actuation/audit`、`agentdeploy`），逐个说明：谁写、谁读、读时是否重读、写是否盲写整份、有没有会丢更新的场景。每条写 `文件:行`。Claude 据此决定是否立技术债。

## 防线

- 上面第 3 条的测试（patrol 双实例、`statefile.Update` 冲突重做）；
- 第 4 条的 overlay 检查；
- RATCHETS.md 登记这两条。

## 门禁

- platform `api/`：`go build ./... && go vet ./... && go test ./...`
- platform `console/`（如果改到）：`npm run lint && npm test && npm run build`
- infra：`kubectl kustomize k8s/overlays/platform-prod`、`kubectl kustomize k8s/overlays/platform-stg`、新加的检查、`make check-maintainers`

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33R.md`，格式按 README（改动 · 防线 · 门禁 · 验收 · 要 Owner 批 · 后续），审计结果单独一节。报告从 origin/main 另开 worktree 提交，推 main：`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`。

注意：infra 的 W-33 PROD overlay（`cursor/w33-infra` 里 `k8s/overlays/platform-prod/` 那部分）还没进 main，PROD 发布时由 Claude 合。你这条道的 api patch 基于当前 main 的 PROD overlay 写，Claude 合并时两份一起处理。

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- 发布队列；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义。
- 不修第 5 条审计出来的其他 store（只报告）。
- 不发版、不部署、不 apply、不写数据库、代码不推 main；不碰 `scripts/agent-guard/`。
