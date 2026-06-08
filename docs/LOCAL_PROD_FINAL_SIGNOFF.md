# Local Prod Final Signoff → 部署主线

> **制定**：2026-06-08 · **关账**：**2026-06-04** — **Local Prod Final CLOSED**
>
> **Owner 修订路线**（L3 签字）：Local Prod Final → **K3s 阶段 1 搭建与测试**（优先）→ **迁移方案待集群就绪后确定**（含 2C-B Compose 与 K3s 取舍）→ Legacy 退役

---

## 主线一览

| 序 | 阶段 | 文档 | 状态 |
|----|------|------|------|
| 0 | Phase 2B + 2C-A Session 0–9 | [PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md) | **CLOSED**（2026-06-08） |
| **1** | **Local Prod Final**（本文） | 本文 | **CLOSED**（2026-06-04 Owner L4） |
| 2 | 2C-B Linux Docker Prod（稳定测试） | [PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md) §2C-B | **稳定测试已签**（D5）；生产切换待迁移方案 |
| 3 | **K3s 阶段 1 试验** | [K3S_PLATFORM_ARCHITECTURE.md](./K3S_PLATFORM_ARCHITECTURE.md) §9 | **进行中**（Owner 2026-06-04 解锁） |
| 4 | Compose → K3s 搬迁 | [PLATFORM_ROADMAP.md](./PLATFORM_ROADMAP.md) §5–6 | 待 K3s 集群就绪 + D1 迁移决策 |
| 5 | Phase 3 Legacy 退役 | [PHASE2C_PROD_DEFERRED.md](./PHASE2C_PROD_DEFERRED.md) | 待 Prod 全栈验证 |

**平台 Console**：[bifrost-platform](https://github.com/weitingzhao/bifrost-platform) — Topology / Matrix（L2.8 已签）。

---

## Phase L — Local Prod Final（2C-B 前置闸门）

### 与 2C-A 的关系

- **2C-A**（2026-06-08）：Session 0–9 已全部 Owner 签字，**已 CLOSED**。
- **Local Prod Final**：在不动 Legacy Prod、不切换 Linux 生产的前提下，做 **最终机械复验 + Owner 短清单确认**，证明 local `http://localhost/` 栈可作为 **后续 K3s / 生产迁移的参照基准**。

**不等于** 生产切换。

---

## L1 — Agent 机械门禁

| Check | Pass | Agent date | Remarks |
|-------|------|------------|---------|
| `make prod-health`（PG + Redis + nginx + 9 API） | [x] | 2026-06-08 | postgres `.80`、redis `.70`、12/12 OK |
| `make verify-2c-a1` | [x] | 2026-06-08 | docker executor；destructive SKIP 可接受 |
| SPA `http://localhost/` HTTP 200 | [x] | 2026-06-08 | `local_prod_final_gate.sh` |
| `bifrost-platform` API `/health`（可选） | [x] | 2026-06-08 | `:8780` |
| `GET /api/v1/topology?env=prod`（可选） | [x] | 2026-06-08 | 拓扑 API OK |

---

## L2 — Owner 浏览器短清单（按 Session 复验）

| Session | L2 项 | Route | Pass | Owner date | Remarks |
|---------|-------|-------|------|------------|---------|
| **0** | L2.7 | `/settings/api` + `/` | [x] | 2026-06-04 | Dev/Prod 双列全红不阻塞；Swagger Open 空白已知 |
| **1** | L2.1 | `/` Global strip、侧栏灯 | [x] | 2026-06-04 | |
| **1** | L2.2 | `/operations/daemon` 概览 | [x] | 2026-06-04 | |
| **2** | L2.5 | `/market/live` SSE | [x] | 2026-06-04 | |
| **3** | L2.6 | `/portfolio/positions` | [x] | 2026-06-04 | |
| **8** | L2.2–L2.4 | daemon + celery + socket | [x] | 2026-06-04 | `config.prod` 无 token；匿名 operator 启停 OK |
| opt | L2.8 | `:5180` Topology/Matrix | [x] | 2026-06-04 | Platform Console |

**已知不阻塞项**（继承 2C-A）：

- `/settings/api` Dev/Prod 端口双列探针全红
- Socket 单 slot 黄灯
- Swagger/ReDoc Open 与 nginx 前缀未对齐

---

## L3 — Owner 决策确认（2026-06-04）

| # | 原草案 | **Owner 决定** | Pass | Owner date |
|---|--------|----------------|------|------------|
| D1 | 2C-B Prod 主机 = mini-pc-a（`.70`） | **先搭建 K3s 集群**；Compose→K3s **迁移路径待集群就绪后再定**（不预先锁定 `.70` 为唯一 Prod 落点） | [x] | 2026-06-04 |
| D2 | PG 保持 mini-pc-b（`.80`） | **确认**：`.80` 裸机 PG **保持不变**（至 CNPG 迁移） | [x] | 2026-06-04 |
| D3 | TWS = Win11 Host | **确认**：TWS **Host + Secondary 均在 Win11**；`IB_HOST` 按账户分别配置 | [x] | 2026-06-04 |
| D4 | R-DV3：仅 New daemon 自动下单 | **暂缓**：当前**无自动下单需求**（风险过高）；不要求维护窗口内切换自动下单 | [x] | 2026-06-04 |
| D5 | 2C-B 后再 K3s | **修订**：**2C-B 稳定测试已签**；**可立即开始 K3s 环境搭建与测试**（与 Compose 稳定态并行） | [x] | 2026-06-04 |

---

## L4 — Local Prod Final 签字

| 项 | Pass | Owner date | 签名 |
|----|------|------------|------|
| L1 机械门禁全绿（或仅 SKIP 可接受项） | [x] | 2026-06-04 | Agent 2026-06-08 |
| L2 浏览器短清单 L2.1–L2.8 | [x] | 2026-06-04 | Owner |
| L3 决策 D1–D5 已确认 | [x] | 2026-06-04 | Owner |
| **Local Prod Final CLOSED** | [x] | 2026-06-04 | **Owner** |

**签字后解锁**：**K3s 阶段 1**（[K3S_PLATFORM_ARCHITECTURE.md](./K3S_PLATFORM_ARCHITECTURE.md) §9）；2C-B 生产 Runbook 保留作 Compose 参照，**生产切换待 D1 迁移决策**。

---

## 下一阶段速查

### K3s 阶段 1（当前优先）

见 [K3S_PLATFORM_ARCHITECTURE.md](./K3S_PLATFORM_ARCHITECTURE.md) §9：

1. mini-pc-a：Ubuntu 24.04 + K3s Server（单节点先跑通）
2. mini-pc-b：加入 Server / 验证 CNPG Operator
3. gpu-server（4090）：K3s Agent + `workload=gpu`
4. Mac Mini ×2：OrbStack Agent（可选，开发/CI）
5. bifrost-platform Console 更新 `deployment_phase: k3s` 后对照拓扑

### 2C-B Compose（稳定测试参照，非立即生产切换）

```bash
# 参照栈（迁移方案确定后再选主机）
cd bifrost-trade-infra
make sync-prod-config
make prod-preflight
make prod-health
```

### 搬迁与 Legacy

- 搬迁顺序：`data` → `socket/worker` → `api` → `frontend`（[PLATFORM_ROADMAP.md](./PLATFORM_ROADMAP.md)）
- Legacy 退役：**Phase 3**，前置 K3s 或 Compose Prod 全栈验证
- **自动下单 / R-DV3**：Owner 暂缓，不在当前里程碑范围

---

## 变更日志

| 日期 | 内容 |
|------|------|
| 2026-06-08 | 立项；Agent `prod-health` + `verify-2c-a1` 复验通过 |
| 2026-06-04 | Owner L2 Session 0–3/8 + L2.8；L3 D1–D5 修订；**L4 CLOSED**；解锁 K3s 阶段 1 |
