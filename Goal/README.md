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
| **[bifrost-platform](../../bifrost-platform)** | **Phase 0 live** | **Bifrost Ops Platform** — Go API `:8780` + Ops Console `:5180`；脊柱 `config/ops-context.yaml` |

## 阅读顺序

1. [AI_NATIVE_OPS_PLATFORM.md](AI_NATIVE_OPS_PLATFORM.md) — 合并后的主目标（原「快速发布 + AI 重构」与「全网 AI 运维」）
2. [bifrost-platform/config/ops-context.yaml](../../bifrost-platform/config/ops-context.yaml) — **脊柱**（milestones、D1–D5、focus）
3. [../docs/LOCAL_PROD_FINAL_SIGNOFF.md](../docs/LOCAL_PROD_FINAL_SIGNOFF.md) — Local Final → K3s → Legacy
4. [bifrost-platform/README.md](../../bifrost-platform/README.md) — Bifrost Ops 控制面快速启动
5. [../docs/PLATFORM_ROADMAP.md](../docs/PLATFORM_ROADMAP.md) — Compose → K3s 分阶段执行
6. [../docs/K3S_PLATFORM_ARCHITECTURE.md](../docs/K3S_PLATFORM_ARCHITECTURE.md) — 目标集群拓扑

## MkDocs

`make docs` 会通过 `docs/Goal` 符号链接包含本目录，导航在 **Goals** 分组下。
