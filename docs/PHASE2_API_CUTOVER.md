# Phase 2B — API 逐域切换（M6）

**前置**：Phase 2A 完成 — 9 域 **VERIFIED**，`make dev-health` 9/9，`tests/contract/test_{domain}_parity.py` 全绿。

**验收清单**：[PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md)  
**Owner 走查**：[PHASE2B_OWNER_WALKTHROUGH.md](../../bifrost-trade-frontend/docs/PHASE2B_OWNER_WALKTHROUGH.md)  
**Agent 验证**：[PHASE2B_AGENT_VERIFICATION.md](../../bifrost-trade-frontend/docs/PHASE2B_AGENT_VERIFICATION.md)  
**进度表**：[MIGRATION_TRACKING.md](./MIGRATION_TRACKING.md) §10

---

## Mac Dev Runbook（日常标准环境）

默认 **不** Docker 化 PG/Redis；容器连 LAN 共享库（`.env` → `make sync-dev-config`）。

```bash
cd bifrost-trade-infra
make ensure-env              # 首次：cp .env.example .env，填 LAN 密码
make dev-preflight           # sync + dev + dev-health + celery 检查
make verify-domain-apis      # 9 域 New API smoke
```

| 命令 | 用途 |
|------|------|
| `make dev` | 启动应用容器（无 postgres/redis profile） |
| `make dev-health` | PG/Redis + 9 API（首次 pip 最多等 ~5 min） |
| `make dev-reinstall-deps` | pyproject 依赖变更后清 pip 标记卷 |
| `make dev-docker-infra` | 可选：隔离空 PG+Redis（CI 用） |
| `make switch-cutover-domain DOMAIN=docs MODE=legacy` | Phase 2B 单域 Legacy |
| `make switch-cutover-domain DOMAIN=all-new` | 恢复全 New 端口 |
| `make verify-wave-a-sessions` | Wave A 各会话关键 API smoke |

前端：`cd bifrost-trade-frontend && npm run dev`（5173）。

**生产 compose（Phase 2C）**：[`docker-compose.yml`](../docker-compose.yml) 已对齐 monorepo；`make prod-preflight` · 签字见 [PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md)。

---

## Dev 栈（切域目标环境）

```bash
cd bifrost-trade-infra
make dev-build    # 仅 Dockerfile.dev 变更时
make dev          # 后台启动全栈
make dev-health   # 等待 pip 完成后 9 API OK
make db-init-dev  # 仅空库首次 schema（LAN 库通常已有数据）
```

Celery 相关域（ops / massive / research）切域前确认 worker 在跑：

```bash
docker compose -f docker-compose.dev.yml ps celery-worker
```

---

## 切换步骤（每域一次）

1. `make dev-health` — 该域端口 OK
2. `make switch-cutover-domain DOMAIN=<域> MODE=legacy|new` — **仅改一个** `VITE_API_*`（见下表）
3. **重启** `npm run dev`（Vite 从 env 读端口）
4. 跑 [PHASE2B_SIGNOFF_MASTER.md](../../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md) 对应域 + Phase 1 Batch
5. Owner 签字 → 更新 MIGRATION_TRACKING §10 该行 **CUTOVER**
6. 机械门禁：`cd bifrost-trade-frontend && npm run lint && npm run build && npm run check:legacy-css`

### 端口对照

| 域 | env 变量 | Legacy | New |
|----|----------|--------|-----|
| docs | `VITE_API_DOCS` | 8719 | 8767 |
| monitor | `VITE_API_MONITOR` | 8711 | 8765 |
| market | `VITE_API_MARKET` | 8733 | 8772 |
| trading | `VITE_API_TRADING` | 8721 | 8769 |
| portfolio | `VITE_API_PORTFOLIO` | 8723 | 8771 |
| strategy | `VITE_API_STRATEGY` | 8735 | 8770 |
| ops | `VITE_API_OPS` | 8713 | 8768 |
| massive | `VITE_API_MASSIVE` | 8741 | 8766 |
| research | `VITE_API_RESEARCH` | 8731 | 8773 |

**禁止**：未验收前一次性改完全部 `VITE_API_*`（单变量隔离）。全部 9 域签字后，`.env.development` 应与 `.env.development.example` 一致。

验证 env：

```bash
chmod +x scripts/check_cutover_env.sh
./scripts/check_cutover_env.sh
```

---

## 推荐顺序

```
docs → monitor → market → trading → portfolio → strategy → ops → massive → research
```

| 域 | Phase 1 Batch | 关键路由 |
|----|---------------|----------|
| docs | 5 | `/settings/api` |
| monitor | 1 + 5 | global strip, `/operations/daemon`, logs |
| market | 1 | `/market/live` SSE |
| trading | 2 | `/portfolio/ledger` |
| portfolio | 1–2 | accounts, positions, performance |
| strategy | 4 | 六路由 + instances |
| ops | 5 | `/operations/celery` |
| massive | 6 | coverage/*, feed/* |
| research | 3 | 八路由 + Discovery |

---

## 跨域依赖

切换 **monitor** 时，以下前端模块同走 `VITE_API_MONITOR`：

- `src/api/monitor.ts`, `messages.ts`, `logs.ts`
- `src/api/market.ts` — `open-orders`（global strip）
- `src/api/strategy.ts` — `config/active-strategy`

切换 **market** 时重点验 `/quotes/stream` SSE。

---

## 回滚

将该域 `VITE_API_*` 改回 Legacy 端口，重启 Vite。已切域不受影响。

---

## 不在 Phase 2B 范围

- 生产 Nginx / `docker-compose.yml` 切域（Phase 2C）
- Legacy engine 退役（Phase 3）
- 修改 `bifrost-trader-engine`
