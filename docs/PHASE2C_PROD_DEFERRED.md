# Phase 2C / Phase 3 — 里程碑追踪

> **2026-06-04**：Phase 2B CLOSED → **Phase 2C 已启动**。签字与 Runbook 见 **[PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md)**。

## Phase 2C — Linux 生产

| 子阶段 | 内容 | 状态 |
|--------|------|------|
| 2C-A | compose + config.prod + 前端 prod build；Session 0–9 | **Owner 已验**（2026-06-08） |
| **2C-A.1** | Ops `executor_mode: docker`；Daemon/Socket 页；`make verify-2c-a1` | **Owner 已验** — [PHASE2C_A1_DOCKER_CONTROL_PLANE.md](./PHASE2C_A1_DOCKER_CONTROL_PLANE.md) |
| **Local Prod Final** | local 闸门 | **CLOSED**（2026-06-04）— Ops Console → Program → Deploy Mainline (`deployMainlineCatalog.ts`) |
| 2C-B | Compose Prod 稳定测试 / 生产切换 | **稳定测试已签**；生产切换待 K3s 后迁移决策 |
| **K3s 阶段 1** | 集群搭建与试验 | **进行中** — Ops Console → Architecture → K3s Architecture §10 |

**前置（已满足）**：

- Phase 2B Final sign-off 完成
- Mac Dev New Frontend + New API 9/9 Owner 签字

---

## Phase 3 — Legacy 退役（未开始）

**前置**（全部满足后方可执行关停）：

1. Phase 2C-B 生产全栈验证通过
2. **UI 体验对齐 Owner Sign-off** — 在统一 Design System（`@bifrost/ui` + Dense UI）治理下，以 Legacy 为并排参照完成视觉密度与调性打磨；Owner 签字确认后方可关闭 Legacy（关闭后将永久失去并排对比能力）

**动作**（按顺序）：

1. **UI 体验对齐**（Legacy 运行期间完成）：全局 token 密度调优 → 逐页打磨 → 通用组件上提 `@bifrost/ui` → Owner 并排验收签字
2. 停止 `bifrost-trader-engine` daemon、Legacy 多端口 API、Legacy frontend
3. [`MIGRATION_TRACKING.md`](./MIGRATION_TRACKING.md) 全局标 **engine 已退役**
4. `bifrost-trader-engine/` 保持只读归档（禁止写操作）

---

## 历史备注

Wave B（monitor / market / ops）已在 Phase 2B Session 7–9 签字完成，不再阻塞 2C。
