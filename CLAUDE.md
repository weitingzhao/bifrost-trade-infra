# CLAUDE.md — bifrost-trade-infra

> 本 repo 是 Bifrost 的部署中心。Legacy `bifrost-trader-engine` 已按 spine **D8**（2026-06-29）归档移出工作区。
> 迁移进度见 `docs/MIGRATION_TRACKING.md`；工作区事实基线见 `../AGENT_FACTS.md`。

与本项目用户对话一律使用中文回复（无论用户用何种语言提问）；UI 字符串与代码标识符使用 English。

## 工作区定位（2026-09-06）

| 项 | 值 |
|---|---|
| 域 / 载荷 | Trade + Ops 的**部署中心**，同时承载治理层 `agent-config/`（工作区根 `.claude` / `.cursor` / `CLAUDE.md` / `AGENT_FACTS.md` 的实体） |
| 运行位置 | K3s `bifrost-bootstrap`（apiserver `192.168.10.73:6443`，kubeconfig `~/.kube/bifrost-k3s.yaml`）；overlays → Argo CD @ `cicd` |
| 发布链 | **推 main 即改运行时**：Argo `bifrost-platform-{stg,prod}` 自动同步（prune + selfHeal）；`bifrost-{stg,prod}` 手动同步；PROD overlay 改动走 git + `gitops_sync_app`，不用 `kubectl apply` |
| D10 guard | `k8s/overlays/stg/daemon-scale-zero.patch.yaml` · `k8s/overlays/prod/daemon-observe-safe.patch.yaml` —— 未解锁不得改 |
| 仓库可见性 | GitHub **PUBLIC**（12 个 repo 全部公开）—— `.env`、Secret YAML、dump、kubeconfig、账户内容永不入库 |
| 硬边界 | D10 交易执行冻结（BLOCKED）· D13 三域边界 · 平台/业务解耦（Flywheel A/B） |
| 事实基线 | `../AGENT_FACTS.md`（§8c 运行时与安全事实）· 规则 `../CLAUDE.md`（§8 Claude Code 运行配置） |

会话请在工作区根 `/stocks` 启动（加载治理层 hooks / auto mode / 共享记忆）；运行时与安全事实以 `../AGENT_FACTS.md` §8c 为准。

## 职责范围

本 repo 是整个 Bifrost Trade 系统的**部署和基础设施**中心：

- `k8s/` — 生产与各环境的部署（K3s：overlays `dev` / `stg` / `prod`，Argo + Tekton 发布链）；compose「生产」栈 2026-10-02 已退役（TD-33）
- `docker-compose.dev.yml` — 本地开发环境（源码挂载 + 热重载）
- `config/` — 共享 YAML 配置文件（挂载到各容器）
- `Makefile` — 常用操作快捷命令
- `docs/DOCKER_BUILD.md` — 何时 rebuild、local 镜像分层、BuildKit 缓存
- `Goal/` — **开发目标索引**（战略文档已迁入 Ops Console Architecture — Blueprint § AI Native Platform）
- `../bifrost-platform` — **环境治理控制面**（Go API `:8780` + Console `:5180`）
- Ops Console → Architecture → **Blueprint** · **Platform Roadmap** · **K3s Architecture** · **K3s Bootstrap**（`bifrost-platform/console/src/lib/architecture/`）
- Ops Console → Program → **Deploy Mainline**（`deployMainlineCatalog.ts`）— 部署决策主线
- `mkdocs.yml` + `scripts/start_docs.sh` — 本地文档站（`make docs` → http://127.0.0.1:8050）；platform 文档 → http://127.0.0.1:8060

## 快速启动

```bash
# 1. 复制并填写环境变量
cp .env.example .env

# 3. 本地开发（源码挂载）
make dev

# 4. 初始化数据库 schema（首次或重置）
make db-init
```

## 配置管理

- `.env` — 敏感信息（密码、API Key），**不提交 git**
- `config/config.yaml` — 从 `bifrost-trade-core/config/config.yaml.example` 复制并修改
- `config/config.dev.yaml` — Dev 叠加层（postgres/redis/ib 由 `make sync-dev-config` 同步；**密码 / Ops token 用 `.env` 的 `PGPASSWORD` / `OPS_*`，YAML 字段保持空**）
- 配置通过 Docker volume 挂载到各服务的 `/app/config/`
- K8s：密钥在 `bifrost-{dev,stg,prod}-secrets`（见 [docs/SECRETS.md](docs/SECRETS.md)）

### Ops UI Authenticate token（Dev）

定义在 **`.env`**（或 K8s Secret）→ `OPS_OPERATOR_TOKEN` / `OPS_ADMIN_TOKEN`（YAML `ops.auth.tokens` 已清空）：

- `OPS_OPERATOR_TOKEN` → operator（关停 API、Socket 控制）
- `OPS_ADMIN_TOKEN` → admin

验证（Dev 栈启动后）：

```bash
curl -s -H "Authorization: Bearer <operator-token>" http://localhost:8768/ops/auth/capabilities
```

应返回 `"authenticated": true` 且 `"can_operate": true`。修改 Secret / `.env` 后需重启 API（`bdev restart` 或 `kubectl rollout restart`）。

## 服务端口一览

| 服务 | 对外端口 | 说明 |
|------|---------|------|
| Nginx | 80 / 443 | 统一入口，路由到各 API |
| Frontend | 80 (via Nginx) | React SPA |
| Monitor API | 8765 | Daemon 状态与控制 + Ops 认证/审计/market-ingest |
| ~~Docs API~~ | ~~8767~~ | **merged** into api-monitor |
| ~~Ops API~~ | ~~8768~~ | **merged** into api-monitor (`/api/ops/*` alias) |
| Trading API | 8769 | 订单与持仓 |
| Strategy API | 8770 | 策略与 Gate |
| Portfolio API | 8771 | 多账户 Greeks |
| Market API | 8772 | 实时行情 SSE |
| Research API | 8773 | 回测分析 |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 消息队列/缓存 |

> **P7:** Massive REST API (`api-massive` / port 8766) retired — Polygon public market data is served by **Market Data Plugin** (`market-data-api:8790` via Trade `/api/plugin/market-data` or platform-api). Celery Massive workers removed from base (ingest is Plugin Cron/PG-broker). Trade `massive-ws` Deployment retired; its Plugin successor `polygon-ws-ingestor` and the `redis-massive` bus were retired too (Owner 2026-09-27 — Options Starter has no real-time WS). There is no Polygon WS ingest anywhere. Config key `massive_port` / `massive:` YAML blocks may remain as **legacy** schema fields (API key for Plugin consumers); they do not mean a Trade `api-massive` or `massive-ws` Deployment.

## bifrost-core 版本管理（TD-37，Owner 2026-10-03 选 B）

- **STG/PROD**：`bifrost-deliver-{stg,prod}` 把 core 与 api、worker 一起从 Gitea 克隆（STG 按分支头，PROD 钉版本 run 按逐仓 SHA），
  `k8s/cicd/docker/Dockerfile.{api,worker}-stg` 直接安装那份克隆。**core 的发布身份是这个 SHA**：clone-core 的 `commit`
  结果作为 build-arg 写进镜像（env `BIFROST_CORE_SHA`、label `io.bifrost.core.sha` / `io.bifrost.core.version`），
  api 各域 `GET /health` 返回 `core_sha` 与 `core_version`。`pyproject.toml` 的版本号只是下游的兼容下限，同一版本号可能对应多个提交。
- **PROD tag**：PROD 发布成功后跑 `scripts/release/tag_core_release.sh <core_sha>`（默认 dry-run，`--push` 才打 `v<version>` 并推送）；
  `v<version>` 已指向别的提交时脚本拒绝——给新内容 bump 版本，不要挪 tag。
- **`BIFROST_CORE_REF`**（`.env`）只给各 repo 自带的 `Dockerfile` 与本地 docker-compose 用：`main` 或某个已有 tag，改后 `make build`。
  它不影响 STG/PROD。

规则全文：`bifrost-trade-core/.cursor/rules/versioning.mdc`。
