# 已退役的 Agent 规则（归档，不再加载）

本目录**在 `.cursor/rules/` 之外**，Cursor 不会加载这里的 `.mdc`。
保留原文仅为可追溯性。

| 文件 | 退役原因 | 替代权威源 |
|------|---------|-----------|
| `migration-protocol.mdc` | 整篇围绕 `bifrost-trader-engine` → `bifrost-trade-*` 的迁移；engine 已按 spine **D8**（2026-06-29）NAS 归档并移出工作区，迁移已完成 | 跨 repo 协同 → `bifrost-trade-core/.cursor/rules/versioning.mdc`；进度 → `bifrost-trade-infra/docs/MIGRATION_TRACKING.md` |
| `project-workflow.mdc` | "核心文档三角"（REQUIREMENTS / ARCHITECTURE / CAPABILITY_TRACKING）全部位于已归档的 `bifrost-trader-engine/docs/` | spine `bifrost-platform/config/ops-context.yaml` + Console Governance catalogs |
| `run-environment.mdc` | 全文指向 `bifrost-trader-engine/docs/ARCHITECTURE.md §2` 与 `REQUIREMENTS.md`，两者均已随 engine 归档 | `AGENT_FACTS.md` §6 + `bifrost-platform/config/{topology,clusters}.yaml` + Console Runtime Map |

退役日期：2026-08-27 · 依据：spine D8
