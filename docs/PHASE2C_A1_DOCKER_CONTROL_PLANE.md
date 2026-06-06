# Phase 2C-A.1 — Docker 控制面（Daemon / Socket / Ops）

**状态**：**进行中**（阻塞 2C-A Session 1–9 Owner 签字）

| WP | 状态 | 备注 |
|----|------|------|
| WP1 | **已落地** | `executor_docker.py` · `docker_compose_map.py` · api 0.1.1 |
| WP2 | 部分 | `runtime_kind` / `compose_service` 已在 GET services |
| WP3 | 部分 | `api-ops` docker.sock + `/infra` 挂载 · `config.prod.yaml` |
| WP4–WP6 | 未开始 | |

**前置**：2C-A Session 0 已签（栈门禁 + nginx `/api/*`）。

**目标拓扑（与 2C-B 未来集群一致）**：

```
┌─────────────────────────────────────────────────────────────┐
│  Docker Compose（应用栈 only）                               │
│  nginx · frontend · api-* · daemon · ib-* · massive-ws ·   │
│  celery-worker · flower                                      │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
         PostgreSQL (LAN)              Redis (LAN, 独立实例)
         非 compose 服务                 非 compose 服务
```

**问题陈述**：Daemon / Socket 页与 Ops `market-ingest` API 面向 **单机 systemd / Mac subprocess**；在 compose 多容器下 `process_active=unknown`、启停无效、Redis lease 与 Legacy（192.168.10.70）冲突。Session 8 与 Daemon Ops 表无法按未来 prod 验收。

---

## 里程碑与仓库分工

| WP | Repo | 交付物 | 优先级 |
|----|------|--------|--------|
| **WP1** | bifrost-trade-api | `executor_mode: docker` + compose 启停 | P0 |
| **WP2** | bifrost-trade-api | `GET /ops/market-ingest/services` 语义（容器 + Redis health） | P0 |
| **WP3** | bifrost-trade-infra | `config.prod.yaml` / `.env` / compose 挂载与文档 | P0 |
| **WP4** | bifrost-trade-frontend | Daemon/Socket 表字段与 lamp 逻辑 | P1 |
| **WP5** | bifrost-trade-infra | `verify_2c_a1_control_plane.sh` + Makefile | P1 |
| **WP6** | bifrost-trade-infra | 签字文档解冻 + Session 重验矩阵 | P2 |

---

## WP1 — Ops Docker Executor（bifrost-trade-api）

### 1.1 配置契约

在 `ops` YAML 段新增（`config.yaml.example` + `config.prod.yaml`）：

```yaml
ops:
  executor_mode: docker          # local | agent | docker
  docker:
    compose_project: bifrost-trade-infra   # 可选，默认从 COMPOSE_PROJECT_NAME
    compose_files:               # 相对 infra 根或绝对路径
      - docker-compose.yml
      - docker-compose.local.yml  # 本地 monorepo build 时
    socket_path: /var/run/docker.sock  # api-ops 容器挂载
    workdir: /infra                # compose 文件所在目录（容器内挂载点）
```

`GET /ops/health` 响应扩展：

- `executor_mode: docker`
- `docker_reachable: true|false`
- `compose_project: string`

### 1.2 服务 ID → Compose service 映射

| `market_ingest` id | Legacy systemd unit | **Compose service** | 控制动作 |
|--------------------|---------------------|---------------------|----------|
| `trading_engine` | bifrost-engine.service | `daemon` | start/stop/restart |
| `massive_ws` | bifrost-massive-ws.service | `massive-ws` | start/stop/restart |
| `ib_ingestor` | bifrost-ib-ingestor.service | `ib-ingestor` | start/stop/restart |
| `ib_account_agent` | bifrost-ib-account-agent.service | `ib-account-agent` | start/stop/restart |
| `ib_operator` | bifrost-ib-operator.service | `ib-operator` | start/stop/restart |
| `account_sync_daemon` | bifrost-account-sync-daemon.service | *(待定)* | WP3 决策 |

实现位置建议：

- `src/bifrost_api/ops/services/executor_docker.py` — `DockerComposeExecutor`
- `src/bifrost_api/ops/app.py` — 三分支：`agent` | `docker` | `local`
- `market_ingest_config.py` — 可选 `compose_service` 列；默认由上表推导

### 1.3 Executor 接口（与 RestrictedExecutor 对齐）

```python
async def systemctl_is_active(self, unit: str) -> str:
    # docker: map unit → compose service → docker compose ps --format json
    # 返回 active | inactive | unknown

async def _systemctl(self, action: str, unit: str, ...) -> dict:
    # docker: docker compose start|stop|restart <service>
    # 禁止在 api-ops 容器内 subprocess 再起一份 ingest
```

### 1.4 Redis lease（R-DV3 简化）

- `control_profile` 仍写 `bifrost_ops_control_env` 到 health hash
- **2C-A.1 本地验收必须使用独立 Redis**（见 WP3），避免与 192.168.10.70 Legacy 抢 lease
- 409 guard：同 profile 已被 **本 compose project** 外实例占用时拒绝；文档说明多集群隔离靠 **独立 Redis**

### 1.5 测试

- `tests/test_ops_executor_docker.py` — mock `docker compose` CLI 或 testcontainers
- 不依赖 live docker.sock 的单元测试为 CI 门禁

---

## WP2 — market-ingest API 语义（bifrost-trade-api）

### 2.1 `GET /ops/market-ingest/services` 响应字段

在现有字段上扩展（向后兼容）：

| 字段 | docker 模式含义 |
|------|-----------------|
| `process_active` | `active` / `inactive` / `unknown` ← **compose 容器状态** |
| `runtime_kind` | `docker` \| `systemd` \| `subprocess` |
| `compose_service` | e.g. `ib-ingestor` |
| `container_id` | 短 id（可选） |
| `health_live` | 来自 `ingest_redis_health_looks_live(meta_key)` |
| `logical_summary_source` | `monitor_status` \| `redis_meta`（供前端 tooltip） |

`trading_engine` 行：`process_active` 优先 compose `daemon` 容器；logical 列仍可读 Monitor PG 心跳。

### 2.2 `POST /ops/market-ingest/control`

- docker 模式：`action` → `docker compose <action> <compose_service>`
- 成功后刷新 Redis lease（现有逻辑保留）
- IB 四件套 group stop：保持现有 `ib_operator_disconnect_all` 行为

### 2.3 弃用路径（docker 模式下）

- 不在 `api-ops` 容器内 `pgrep run_ib_ingestor.py`
- 不调用 `systemctl`（容器内通常不存在）

---

## WP3 — Infra 配置与 compose（bifrost-trade-infra）

### 3.1 api-ops 容器能力

`docker-compose.yml` → `api-ops`：

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
  - .:/infra:ro   # compose 文件与 project 名
environment:
  BIFROST_OPS_EXECUTOR: docker
```

`config.prod.yaml`：

```yaml
ops:
  executor_mode: docker
  docker:
    workdir: /infra
```

### 3.2 本地 2C-A.1 验收用 `.env`（与 Legacy 隔离）

| 变量 | 2C-A Session 0（已签） | **2C-A.1 推荐** |
|------|------------------------|-----------------|
| `REDIS_HOST` | 192.168.10.70（与 Legacy 共用） | `redis`（embedded-infra）或独立 LAN Redis |
| `POSTGRES_HOST` | 192.168.10.80 | 可保持（只读验收）或 dev 库 |
| `BIFROST_PROD_INFRA` | `host` | `embedded-infra`（仅 Redis+PG 容器，应用栈不变） |

命令：

```bash
make prod-embedded-infra   # 或文档化「仅起 redis profile」变体
make prod-preflight-local
make verify-2c-a1
```

**不修改 192.168.10.70 Legacy** — 仅本地 `.env` 指向独立 Redis。

### 3.3 account_sync_daemon

**决策点（Owner）**：

- **A**：暂不纳入 compose；Daemon 页该行标 `not deployed`，隐藏 Start/Stop
- **B**：新增 `account-sync` 服务到 compose（后续 WP）

2C-A.1 默认 **A**，不阻塞 socket 四件套 + daemon。

### 3.4 sync_prod_config.sh

- 支持 `BIFROST_OPS_EXECUTOR` / `ops.executor_mode` 从 `.env` 写入 overlay

---

## WP4 — 前端（bifrost-trade-frontend）

### 4.1 类型扩展 `MarketIngestServiceRow`

`src/utils/socketIngestLamp.ts`：

```ts
runtime_kind?: 'docker' | 'systemd' | 'subprocess'
compose_service?: string
health_live?: boolean
```

### 4.2 Lamp 逻辑

| 场景 | 规则 |
|------|------|
| `runtime_kind=docker` | 进程灯 ← `process_active`；连接灯 ← Monitor `/status` socket 段（现有 logical 列） |
| `process_active=unknown` + docker | 显示 **yellow**，文案 `Container state unknown` |
| Host 列 | `redis_control_env` 为 **本栈 profile** 时显示 Prod，不再出现误报 DEV（独立 Redis 后） |
| Local Control Agent | `executor_mode=docker` 时隐藏或显示 N/A（非 Mac agent 场景） |

### 4.3 文案

- `ingestOpsShared.ts`：`socketServicesHostColumnDisplay` 增加 docker 分支
- Daemon / Socket 页 Process control 说明改为：「Docker Compose service control via Ops API」

### 4.4 测试

- `socketIngestLamp.test.ts` — docker 模式 lamp 用例
- 无需改业务 API `VITE_API_*` 路径

---

## WP5 — 验收脚本（bifrost-trade-infra）

`scripts/verify_2c_a1_control_plane.sh`：

1. `GET /api/ops/health` → `executor_mode=docker`，`docker_reachable=true`
2. `GET /api/ops/ops/market-ingest/services` → 5 行 socket + 1 行 trading_engine；`runtime_kind=docker`
3. 对每个 `compose_service`：`docker compose ps` 状态与 API `process_active` 一致
4. **可选 destructive**（`VERIFY_2C_A1_CONTROL=1`）：`restart ib-ingestor` via Ops POST → 容器 Recreate/Up
5. Redis lease：本栈 `control_profile` 写入后 Host 列非 `other stack`

Makefile：`make verify-2c-a1`

---

## WP6 — Sign-off 解冻矩阵

2C-A.1 **Agent 门禁全 Pass** 后：

| Session | 动作 |
|---------|------|
| 0 | 已签；**复验** Network `/api/*` + `prod-health` |
| 1 | **重签** — Global strip + Daemon **状态区**（Ops 表须可信） |
| 2 | 签 — 仍依赖 IB/TWS；与控制面正交 |
| 3–7 | **抽样** 或沿用 2B（API 契约未变） |
| 8 | **重签** — Socket 表 + Celery（Celery 仍 subprocess/systemd 在 worker 容器内，单独备注） |
| 9 | 2C-A Final |

---

## 实施顺序（建议）

```
WP3.2 独立 Redis .env  →  WP1 executor_docker  →  WP2 API 字段
        ↓
WP3.1 compose sock 挂载  →  WP5 脚本变绿  →  WP4 前端  →  WP6 解冻签字
```

**预估**：API+Infra 2–3 天；前端 0.5–1 天；联调 + 文档 0.5 天（视 docker.sock 权限与 IB 环境而定）。

---

## 非目标（2C-A.1 不做）

- 修改 192.168.10.70 Legacy 栈
- `executor_mode: agent` / Mac Local Control Agent 在 Linux prod 的退役（保留代码，prod 用 docker）
- Dev/Prod Health 双列（`/settings/api` 顶部）Legacy 端口探针 — 另开 backlog
- IB 全链路连通（TWS 网络/client_id）— 环境准备，不阻塞控制面 PR

---

## 参考代码（当前 Legacy 路径）

| 模块 | 路径 |
|------|------|
| market-ingest 路由 | `bifrost-trade-api/.../ops/routers/market_ingest.py` |
| Subprocess executor | `bifrost-trade-api/.../ops/services/executor_local.py` |
| 服务注册表 | `bifrost-trade-api/.../ops/market_ingest_config.py` |
| 前端 lamp | `bifrost-trade-frontend/src/utils/socketIngestLamp.ts` |
| Daemon 页 | `bifrost-trade-frontend/src/pages/settings/DaemonStatusPage.tsx` |
| Socket 页 | `bifrost-trade-frontend/src/pages/settings/SocketPage.tsx` |
