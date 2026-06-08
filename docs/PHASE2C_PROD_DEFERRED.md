# Phase 2C / Phase 3 — 里程碑追踪

> **2026-06-04**：Phase 2B CLOSED → **Phase 2C 已启动**。签字与 Runbook 见 **[PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md)**。

## Phase 2C — Linux 生产

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 2C-A | compose + config.prod + 前端 prod build；Session 0–9 | **Owner 已验**（2026-06-08） |
| **2C-A.1** | Ops `executor_mode: docker`；Daemon/Socket 页；`make verify-2c-a1` | **Owner 已验** — [PHASE2C_A1_DOCKER_CONTROL_PLANE.md](./PHASE2C_A1_DOCKER_CONTROL_PLANE.md) |
| **Local Prod Final** | local 闸门 | **CLOSED**（2026-06-04）— [LOCAL_PROD_FINAL_SIGNOFF.md](./LOCAL_PROD_FINAL_SIGNOFF.md) |
| 2C-B | Compose Prod 稳定测试 / 生产切换 | **稳定测试已签**；生产切换待 K3s 后迁移决策 |
| **K3s 阶段 1** | 集群搭建与试验 | **进行中** — [K3S_PLATFORM_ARCHITECTURE.md](./K3S_PLATFORM_ARCHITECTURE.md) §9 |

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
