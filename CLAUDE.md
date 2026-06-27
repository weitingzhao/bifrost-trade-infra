# CLAUDE.md — bifrost-trade-infra

> 本项目是 bifrost-trader-engine 重构的部署中心。迁移进度见 `docs/MIGRATION_TRACKING.md`。

与本项目用户对话一律使用中文回复（无论用户用何种语言提问）；UI 字符串与代码标识符使用 English。

## 职责范围

本 repo 是整个 Bifrost Trade 系统的**部署和基础设施**中心：

- `docker-compose.yml` — 生产环境全栈编排
- `docker-compose.dev.yml` — 本地开发环境（源码挂载 + 热重载）
- `nginx/` — 反向代理配置（统一入口、路径路由、SSE 支持）
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

# 2. 生产环境启动
make up

# 3. 本地开发（源码挂载）
make dev

# 4. 初始化数据库 schema（首次或重置）
make db-init
```

## 配置管理

- `.env` — 敏感信息（密码、API Key），**不提交 git**
- `config/config.yaml` — 从 `bifrost-trade-core/config/config.yaml.example` 复制并修改
- `config/config.dev.yaml` — Dev 叠加层（postgres/redis/ib 由 `make sync-dev-config` 同步；**Ops Authenticate token** 在 `ops.auth.tokens`）
- 配置通过 Docker volume 挂载到各服务的 `/app/config/`

### Ops UI Authenticate token（Dev）

与 Legacy 相同，定义在 **`config/config.dev.yaml`** → `ops.auth.tokens`：

- `role: operator` → 名称 `trader`（关停 API、Celery/Socket 控制）
- `role: admin` → 名称 `admin`

可选环境变量覆盖：`OPS_OPERATOR_TOKEN` / `OPS_ADMIN_TOKEN`（写入 `.env`）。

验证（Dev 栈启动后）：

```bash
curl -s -H "Authorization: Bearer <operator-token>" http://localhost:8768/ops/auth/capabilities
```

应返回 `"authenticated": true` 且 `"can_operate": true`。修改 `config.dev.yaml` 后需重启 API 容器（`docker compose ... restart api-ops` 或 `make dev` 重拉）。

## 服务端口一览

| 服务 | 对外端口 | 说明 |
|------|---------|------|
| Nginx | 80 / 443 | 统一入口，路由到各 API |
| Frontend | 80 (via Nginx) | React SPA |
| Monitor API | 8765 | Daemon 状态与控制 |
| Massive API | 8766 | Polygon 数据 |
| Docs API | 8767 | OpenAPI |
| Ops API | 8768 | Celery 管理 |
| Trading API | 8769 | 订单与持仓 |
| Strategy API | 8770 | 策略与 Gate |
| Portfolio API | 8771 | 多账户 Greeks |
| Market API | 8772 | 实时行情 SSE |
| Research API | 8773 | 回测分析 |
| Flower | 5555 | Celery 监控 UI |
| PostgreSQL | 5432 | 数据库 |
| Redis | 6379 | 消息队列/缓存 |

## bifrost-core 版本管理

各服务 Docker 镜像通过 `BIFROST_CORE_REF` 变量控制安装的 bifrost-core 版本：
- `BIFROST_CORE_REF=main` — 最新主干（开发用）
- `BIFROST_CORE_REF=v0.2.0` — 指定 tag（生产用）

在 `.env` 中修改后 `make build` 重新构建镜像。
