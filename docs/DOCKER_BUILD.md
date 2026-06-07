# Docker 构建优化 — 重构期 local prod 冒烟

日常开发用 `make dev`（volume 挂载，**不 rebuild**）。2C 签验收用 `make prod-health`（**仅探针，不 rebuild**）。

## 何时需要 rebuild

| 变更类型 | 推荐命令 | 说明 |
|----------|----------|------|
| Python 业务代码（日常） | `make dev` | volume 挂载，改代码后重启容器即可 |
| 栈已在跑，只验门禁 | `make prod-health` | 秒级，无 build |
| 仅配置 / nginx | `make prod-up-local` | `up -d --no-build` |
| `pyproject.toml` / Dockerfile | `make prod-base-local` 然后 `make prod-build-local` | 重建共享 deps 层 |
| 仅 `bifrost-trade-api` 代码 | `make prod-rebuild-local-api` | 只 build API 镜像 + 重启 9 域 |
| 单服务 | `make prod-rebuild-local SERVICE=api-monitor` | 指定服务 build + up |
| 全栈冷启动 / 签验收 | `make prod-preflight-local` | build + up + health |

## 拆分 preflight 步骤

```bash
make prod-preflight-local-build    # sync + build only
make prod-preflight-local-up       # up --no-build + nginx restart
make prod-preflight-local-health   # make prod-health
```

## 镜像分层（local monorepo）

| 镜像 tag | 内容 |
|----------|------|
| `bifrost-base-worker:local` | python + apt + core + worker deps |
| `bifrost-base-socket:local` | python + apt + core + socket deps |
| `bifrost-base-api:local` | core + worker + socket（无 api） |
| `bifrost-worker:local` | base-worker + worker scripts |
| `bifrost-socket:local` | base-socket + socket scripts |
| `bifrost-api:local` | base-api + api（9 域共用） |
| `bifrost-api-ops:local` | base-api + Docker CLI + api |

BuildKit pip 缓存：所有 `RUN pip install` 使用 `--mount=type=cache,target=/root/.cache/pip`。确保 `DOCKER_BUILDKIT=1`（Docker Desktop 默认开启）。

## 冷启动预拉公版镜像

```bash
make prod-pull-base-images
# 或: docker pull python:3.11-slim node:20-slim nginx:alpine
```

## 避免清掉 builder cache

`make clean` 会执行 `docker system prune -f`，重构期频繁签验收时**不要习惯性 clean**，否则会失去 layer / pip 缓存。
