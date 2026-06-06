# Phase 2A 跨 Repo 联调检查清单

> **目标**：在 Dev 栈上验证 worker ↔ api ↔ socket 循环依赖与 Celery/Beat 契约一致，作为 M6 切域前的机械门禁补充。

## 前置条件

```bash
cd bifrost-trade-infra
make dev-build         # 自动从 .env.example 创建 .env（若缺失）
make dev               # 后台启动全栈（首次各 API 容器 pip install ~1–2 分钟）
make db-init-dev       # 首次初始化 schema
# 等待 API 就绪后再探活：
sleep 90 && make dev-health
```

**常见失败**：
- `(000)` / `(000000)`：栈未启动 → 先 `make dev`；查看 `docker compose -f docker-compose.dev.yml ps -a`
- 容器 `Exited` + `egg-info` 错误：已修复（dev 卷改为 rw 挂载）
- `Attribute "app" not found`：已修复（`run_server.py` 调用各域 `run_*_server`）

| Repo | `make install-dev` 链 |
|------|----------------------|
| core | `pip install -e ".[dev]"` |
| socket | core → socket |
| worker | core → socket → worker → api[dev] |
| api | core → worker → socket → api[dev] |

## 自动化门禁（无需 Dev 栈）

在各 repo 根目录执行：

```bash
# core
pytest -m 'not ib and not db' -q          # 期望 146 passed

# socket
pytest -m 'not ib' -q                     # 期望 ≥20 passed（当前 23）

# worker
pytest -m 'not ib and not db' -q          # 期望 189 passed

# api（含契约 + 跨 repo）
pytest tests/ -m 'not ib and not db' -q   # 期望 195+ passed
pytest tests/contract -q                    # 期望 24 passed（9 域 parity + cross-repo）
```

### 跨 repo 单测覆盖点

| 检查项 | 测试位置 |
|--------|----------|
| `bifrost_api.research.*` 可被 worker 侧懒加载 | `tests/contract/test_cross_repo_integration.py::test_worker_research_lazy_import_chain` |
| Massive Beat API ≡ worker `beat_schedule_public` | `test_massive_beat_schedule_api_matches_worker_source` |
| Ops capabilities `beat_tasks` 长度 7 | `test_ops_and_massive_beat_tasks_aligned` |
| Ops 注册任务名 `src.*` 前缀 | `tests/contract/test_ops_parity.py` |
| 9 域 health + OpenAPI 壳 | `tests/contract/test_{domain}_parity.py` |

## Dev 栈手动冒烟（Owner 可选）

前端 **仍指向 Legacy API**；仅临时改单域 `VITE_API_*` 到 8765–8773 做对照（不提交 env）。

| 步骤 | 命令 / URL | 通过标准 |
|------|------------|----------|
| 1. 全栈 health | `make dev-health` | 9/9 API `ok`；PG `pg_isready`；Redis `PONG` |
| 2. Ops Celery | `GET http://localhost:8768/ops/celery/capabilities` | `ok: true`；`beat_tasks` 7 条；含 `src.bars.tasks.backfill_bars` |
| 3. Massive Beat | `GET http://localhost:8766/research/massive/celery-beat-schedule` | `ok: true`；`entries` 7 条；与步骤 2 `beat_tasks` 任务路径一致 |
| 4. Monitor daemon | `GET http://localhost:8765/status` | JSON 含 daemon 状态字段（PG sink 可读） |
| 5. Celery enqueue | Flower `:5555` 或 Redis CLI | `run_massive_job` 入队不 ImportError（需 worker 容器运行） |
| 6. Socket 健康键 | Redis `HGETALL bifrost:health:ws_ib_operator` | 有 hash 或 daemon 黄灯说明（无 TWS 时可跳过） |

### 前端 Batch 对照（单域切换时）

见 [`PHASE1_SIGNOFF_MASTER.md`](../bifrost-trade-frontend/docs/PHASE1_SIGNOFF_MASTER.md)：

| API 域 | 冒烟路由 |
|--------|----------|
| docs | `/settings/api` |
| monitor | global strip + `/operations/daemon` |
| market | `/market/live` |
| trading | `/portfolio/ledger` |
| portfolio | accounts / positions / performance |
| strategy | 六路由 |
| ops | `/operations/celery` |
| massive | coverage / feed |
| research | 八路由 |

## 出口签字

- [x] 四 repo 单测绿（`not ib and not db` / socket `not ib`）
- [x] `tests/contract` 24 passed
- [x] `make dev-health` 9/9（Dev 栈已起时）
- [x] `MIGRATION_TRACKING.md` §4 九域 **VERIFIED** → Phase 2B **CUTOVER**
- [x] Phase 2B：[`PHASE2_API_CUTOVER.md`](./PHASE2_API_CUTOVER.md) + `PHASE2B_SIGNOFF_MASTER.md`；`make check-cutover-env`
