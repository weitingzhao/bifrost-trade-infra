# Phase 2C / Phase 3 — 里程碑追踪

> **2026-06-04**：Phase 2B CLOSED → **Phase 2C 已启动**。签字与 Runbook 见 **[PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md)**。

## Phase 2C — Linux 生产

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 2C-A | `docker-compose.yml` 对齐 socket/worker/daemon；`config.prod.yaml`；前端 `.env.production`；`make prod-preflight` | **实施完成，待冒烟签字** |
| 2C-B | 192.168.10.70 切换、停 Legacy、Owner 生产签字 | 排期 |

**前置（已满足）**：

- Phase 2B Final sign-off 完成
- Mac Dev New Frontend + New API 9/9 Owner 签字

---

## Phase 3 — Legacy 退役（未开始）

**前置**：Phase 2C-B 生产全栈验证通过。

**动作**：

1. 停止 `bifrost-trader-engine` daemon、Legacy 多端口 API、Legacy frontend
2. [`MIGRATION_TRACKING.md`](./MIGRATION_TRACKING.md) 全局标 **engine 已退役**
3. `bifrost-trader-engine/` 保持只读归档（禁止写操作）

---

## 历史备注

Wave B（monitor / market / ops）已在 Phase 2B Session 7–9 签字完成，不再阻塞 2C。
