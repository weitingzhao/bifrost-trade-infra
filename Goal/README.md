# Bifrost Trade — 开发目标（Goal）

本目录存放 **infra 层面的战略性开发目标**，与 `docs/` 下的操作手册、签字 Runbook、迁移追踪互补：

| 目录 | 用途 |
|------|------|
| **`Goal/`**（本目录） | 接下来要构建什么、为什么、成功标准、与业务的关系 |
| **`docs/`** | 怎么做、当前进度、验收清单、平台路线图 |

## 当前目标

| 文档 / Repo | 状态 | 摘要 |
|-------------|------|------|
| **[AI_NATIVE_OPS_PLATFORM.md](AI_NATIVE_OPS_PLATFORM.md)** | **重点构建** | AI 原生自发现 / 自维护 / 自修复的发布运维平台；承载页面持续重构与交易复盘 AI |
| **[bifrost-platform](../../bifrost-platform)** | **Phase 0 脚手架** | Go API `:8780` + Console `:5180`；Dev/Prod 连通性矩阵（L0） |

## 阅读顺序

1. [AI_NATIVE_OPS_PLATFORM.md](AI_NATIVE_OPS_PLATFORM.md) — 合并后的主目标（原「快速发布 + AI 重构」与「全网 AI 运维」）
2. [../docs/LOCAL_PROD_FINAL_SIGNOFF.md](../docs/LOCAL_PROD_FINAL_SIGNOFF.md) — **进行中**：Local Final → 2C-B → K3s → Legacy
3. [bifrost-platform/README.md](../../bifrost-platform/README.md) — 控制面 repo 快速启动
4. [../docs/PLATFORM_ROADMAP.md](../docs/PLATFORM_ROADMAP.md) — Compose → K3s 分阶段执行
4. [../docs/K3S_PLATFORM_ARCHITECTURE.md](../docs/K3S_PLATFORM_ARCHITECTURE.md) — 目标集群拓扑

## MkDocs

`make docs` 会通过 `docs/Goal` 符号链接包含本目录，导航在 **Goals** 分组下。
