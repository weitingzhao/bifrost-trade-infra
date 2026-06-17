# Bifrost Trade — 开发目标（Goal）

> **2026-06-15 更新**：战略目标文档已迁入 Ops Console Architecture。本目录保留为 MkDocs 导航兼容。

## 权威源

| 内容 | 位置 |
|------|------|
| **AI 原生运维平台目标** | Ops Console → Architecture → **Blueprint § AI Native Platform**（`blueprintCatalog.ts`） |
| **平台路线图（Compose → K3s）** | Ops Console → Architecture → **Platform Roadmap**（`roadmapCatalog.ts`） |
| **K3s 目标拓扑** | Ops Console → Architecture → **K3s Architecture**（`k3sArchitectureCatalog.ts`） |
| **K3s 首节点部署** | Ops Console → Architecture → **K3s Bootstrap**（`k3sBootstrapCatalog.ts`） |
| **部署决策主线** | Ops Console → Program → **Deploy Mainline**（`deployMainlineCatalog.ts`） |
| **脊柱（milestones / decisions）** | [bifrost-platform/config/ops-context.yaml](../../bifrost-platform/config/ops-context.yaml) |
| **Ops Platform 快速启动** | [bifrost-platform/README.md](../../bifrost-platform/README.md) |

## 文档权责分割

| Repo | 管辖范围 |
|------|----------|
| **bifrost-platform**（控制面） | 环境治理、集群架构、发布闸门、平台路线图、AI Ops 目标 → Console Architecture catalogs 为权威 |
| **bifrost-trade-infra**（数据面） | Docker build 手册、迁移签字清单、2C Session runbook、业务 API 切换流程 → MkDocs :8050 为权威 |

## MkDocs

`make docs` 会通过 `docs/Goal` 符号链接包含本目录，导航在 **Goals** 分组下。
