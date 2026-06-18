# Phase B — bifrost-stg v2 全功能实施计划

> **目标**：K3s `bifrost-stg` 成为与 Compose 等价的**全功能 STG**（Tier A + B）：Live TWS + Massive + daemon + Celery + socket 四服务 + 9 API + frontend。  
> **非目标**：P5a gpu-server、prod cutover（D1）、Legacy 关停（见 §7）。  
> **权威入口**：`http://192.168.10.73:30880/` · namespace `bifrost-stg` · `make k3s-install-phase-b-stg-v2`

---

## 1. 现状（v1）

| 已有 | 缺失 |
|------|------|
| PG / Redis in-cluster | daemon · account-sync · celery-worker |
| nginx :30880 + 9 API + frontend | ib-ingestor · ib-account-agent · ib-operator · massive-ws |
| Tekton `bifrost-deliver-stg` | worker/socket K8s manifests + Kaniko 镜像 |
| `skip_monitor_ib: true` | Live IB + Massive 配置 |
| release gate：stg-monitor + frontend | 9 API 全量 smoke · worker/socket 健康 |

---

## 2. 验收定义（Tier A + B）

### Tier A — 网关与 API 面

- [ ] `bifrost-stg` 全部 Deployment Ready（含 v2 worker/socket）
- [ ] `:30880` 下 9 域 `GET /api/{domain}/status` → HTTP 200
- [ ] SPA 含 `Bifrost Trade`（非 smoke HTML）
- [ ] `db-init-stg` Job 完成
- [ ] Ops Console release gate：**9× stg-api-* + stg-frontend** 可配置为 required

### Tier B — 运行时全功能

- [ ] **Live TWS**：`ib.host` / `ib.secondary` LAN 可达；**STG 独立 client_id**（210 段，与 prod/dev 隔离，R-DV3）
- [ ] **Massive**：`massive-ws` 运行；`MASSIVE_API_KEY` 经 Secret 注入
- [ ] **daemon** 写入 in-cluster PG；Monitor Daemon 页可读状态
- [ ] **Celery worker** 连 in-cluster Redis；Ops Celery 页可见队列
- [ ] **Socket 四服务** Redis 健康键刷新；Market Live / Socket 页可联调
- [ ] `skip_monitor_ib: false`

### Tier B — Ops 控制（分阶段）

| 阶段 | 能力 | 实现 |
|------|------|------|
| **B1（本计划）** | Pod 重启 / scale | Ops Console → Cluster（platform-api L1） |
| **B2（后续）** | Celery/Socket 启停与 Compose 等价 | `bifrost-trade-api` `executor_mode: kubernetes` |

---

## 3. 里程碑（单变量顺序）

| ID | 名称 | Repo | 交付物 | 验证 |
|----|------|------|--------|------|
| **S10** | v1.5 清单与配置基线 | infra | 本计划 + `config.stg.yaml` 全结构 + `sync_stg_config.sh` | `config` 含 ib/massive/ops |
| **S11** | worker/socket K8s + 镜像 | infra | `k8s/base/worker/*` `socket/*` Dockerfiles Kaniko task | `kubectl get deploy -n bifrost-stg` |
| **S12** | deliver-stg v2 管线 | infra | `pipeline-deliver-stg` 构建 rollout worker+socket | PipelineRun Succeeded |
| **S13** | STG Secret + 联调 | infra | `bifrost-stg-secrets` · `make sync-stg-config` · IB/Massive 联调 | TWS + Polygon 连接 |
| **S14** | 全量 smoke + gate | platform + infra | `clusters.yaml` 9 API probes · `verify-phase-b-stg-v2.sh` | release gate stg 全绿 |
| **S15** | 文档与 spine 对齐 | platform | `ops-context` compose-k3s note · uiProgressSnapshot | Briefing 反映 v2 |

---

## 4. 技术要点

### 4.1 STG IB client_id 分配（勿与 prod/dev 冲突）

| 角色 | STG (K3s) | Prod | Dev |
|------|-----------|------|-----|
| daemon | 210 | 10 | 110 |
| listener | 201 | 1 | 101 |
| operator | 220 | 20 | 120 |
| ingestor | 250 | 50 | 150 |
| account_agent | 260 | 60 | 160 |

Host: `192.168.10.30` / Secondary: `192.168.10.33` · `port_type: tws_live`（Owner 拍板）

### 4.2 镜像

- `192.168.10.73:30500/bifrost-worker:stg` — daemon / account-sync / celery-worker（command 覆盖）
- `192.168.10.73:30500/bifrost-socket:stg` — 四个 socket 进程（command 覆盖）

### 4.3 密钥

- `MASSIVE_API_KEY` / `POLYGON_API_KEY` → Secret `bifrost-stg-secrets`
- `OPS_OPERATOR_TOKEN` / `OPS_ADMIN_TOKEN` → Secret 或 `sync_stg_config.sh` 写入 overlay config（勿提交 git）

### 4.4 部署命令

```bash
# 1. 配置（从 .env 同步 STG overlay）
make sync-stg-config
# 2. 创建 Secret（一次性，见 k8s/base/secrets/bifrost-stg-secrets.example.yaml）
kubectl apply -f k8s/base/secrets/bifrost-stg-secrets.yaml -n bifrost-stg
# 3. 全量安装 / 升级
make k3s-install-phase-b-stg-v2
# 4. 验证
make k3s-verify-phase-b-stg-v2
```

---

## 5. 文件清单（S10–S12 已落地）

```
bifrost-trade-infra/
  docs/PHASE_B_STG_V2_PLAN.md          ← 本文
  config/config.stg.yaml               ← 全功能结构（密钥走 env/secret）
  scripts/sync_stg_config.sh
  scripts/k3s/verify-phase-b-stg-v2.sh
  scripts/k3s/install-phase-b-stg-v2.sh
  k8s/base/worker/manifest.yaml
  k8s/base/socket/manifest.yaml
  k8s/base/secrets/bifrost-stg-secrets.example.yaml
  k8s/cicd/docker/Dockerfile.worker-stg
  k8s/cicd/docker/Dockerfile.socket-stg
  k8s/cicd/tekton/task-kaniko-worker-socket-stg.yaml
  k8s/cicd/tekton/pipeline-deliver-stg.yaml   (updated)
  k8s/cicd/tekton/task-deliver-stg.yaml       (rollout list)

bifrost-platform/
  config/clusters.yaml                 (stg_smoke.api_domains)
  api/internal/config/clusters.go
  api/internal/delivery/service.go
```

---

## 6. 风险与依赖

| 风险 | 缓解 |
|------|------|
| TWS client_id 冲突 | STG 专用 210 段；切换前核对 TWS 已连接会话 |
| K3s 节点拉镜像失败 | `configure-insecure-registry.sh` + overlay `192.168.10.73:30500` |
| Tekton 构建超时 | `DELIVER_TIMEOUT=7200`；worker/socket 增量 Kaniko |
| Ops API 无法控制 K8s Pod | B1 用 Console Cluster actuation；B2 再迁 executor |
| prod matrix 仍 fail | 预期内；stg gate 与 prod cutover 解耦 |

---

## 7. 与 Legacy Retirement 的关系

STG v2 全绿后：

1. **可并行启动** `legacy-retirement` → `ui-experience-alignment`（Legacy 仍运行）
2. **不可跳过** Owner 签字与 **prod 替代路径**（D1）才能 `stop-legacy-runtime`
3. STG 全功能可作为 **K3s 能力证明**，不等同于 prod compose 退役

---

## 8. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-06-18 | 初版：Owner 拍板 Tier A+B · Live TWS + Massive · P5a 暂缓 |
| 2026-06-18 | G2–G3 placement：Tekton `taskRunTemplate` amd64 · stg overlay `kubernetes.io/arch=amd64` · `make k3s-verify-placement` |
