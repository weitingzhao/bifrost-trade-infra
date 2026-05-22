# CLAUDE.md — bifrost-trade-infra

与本项目用户的所有对话一律使用中文。

## 职责范围

本 repo 是整个 Bifrost Trade 系统的**部署和基础设施**中心：

- `docker-compose.yml` — 生产环境全栈编排
- `docker-compose.dev.yml` — 本地开发环境（源码挂载 + 热重载）
- `nginx/` — 反向代理配置（统一入口、路径路由、SSE 支持）
- `config/` — 共享 YAML 配置文件（挂载到各容器）
- `Makefile` — 常用操作快捷命令

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
- 配置通过 Docker volume 挂载到各服务的 `/app/config/`

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
