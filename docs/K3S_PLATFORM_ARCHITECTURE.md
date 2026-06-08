# K3s 平台架构规划

> **文档目的**：记录 Bifrost Trade 从 Docker Compose 迁移至 K3s 集群的完整目标架构，供日后架构调整和现状对比使用。
>
> **制定日期**：2026-06-07 · **当前状态**：规划阶段，尚未实施
>
> **与 Compose 过渡**：执行顺序与硬件映射见 **[PLATFORM_ROADMAP.md](PLATFORM_ROADMAP.md)**（2C-B 先于 K3s 阶段 1）。**重点构建目标**见 **[Goal/AI_NATIVE_OPS_PLATFORM.md](../Goal/AI_NATIVE_OPS_PLATFORM.md)**。TWS 当前在 **Win11 ×2**（非 Mac Mini），保持集群外专用机。

---

## §1 背景与动机

### 现状（Docker Compose）

- Legacy 系统运行在独立 Linux 服务器上
- 新系统计划使用 `docker-compose.yml`（本 repo）部署
- **问题**：新旧系统共享同一物理服务器，端口冲突不可避免（Redis 6379、PostgreSQL 5432、API 端口 8765–8773 均存在冲突风险）

### 目标（K3s 集群）

- 所有节点组成统一 K3s 集群，服务通过 ClusterIP + Ingress 路由，彻底消除宿主机端口冲突
- 基础设施即代码（GitOps），ArgoCD 负责所有部署，不再手动操作
- **AI 原生**：AI Agent 可透明查看集群状态、执行例行运维、提出并提交变更

---

## §2 硬件节点清单

| # | 节点名称 | CPU | RAM | 系统 | 批次 | 主要角色 |
|---|---------|-----|-----|------|------|---------|
| 1 | `mini-pc-a` | Ryzen 7 7735HS | 24GB | Linux | 首批 | K3s Server ① · 通用服务 |
| 2 | `mini-pc-b` | Ryzen 7 7735HS | 32GB | Linux | 首批 | K3s Server ② · 数据库专用 |
| 3 | `gpu-server` | Ryzen 9 9500S | 128GB | Linux | 首批 | K3s Agent · GPU 工作节点 |
| 4 | `mac-mini-1` | Apple M4 | 16GB | macOS | 首批 | K3s Agent (OrbStack) · 开发/CI |
| 5 | `mac-mini-2` | Apple M4 | 16GB | macOS | 首批 | K3s Agent (OrbStack) · 监控/开发 |
| 6 | `mini-pc-c` | Ryzen 7 7735HS | 32GB | Linux | 第二批 | K3s Server ③ · 监控/CI Runner（Legacy 退役后加入）|

> **备注**：三台 Mini PC 组成奇数 Server 节点，满足 K3s 嵌入式 etcd HA 的 quorum 要求（2/3 节点存活即可维持集群）。Mac Mini 通过 OrbStack 运行 ARM Linux VM 加入集群。

---

## §3 集群拓扑

```
┌──────────────────────────── K3s HA Control Plane ──────────────────────────────┐
│                                                                                 │
│  mini-pc-a (24GB)        mini-pc-b (32GB)        mini-pc-c (32GB) [第二批]     │
│  K3s Server ①            K3s Server ②            K3s Server ③                 │
│  ────────────────         ────────────────         ────────────────             │
│  • bifrost-trade-api      • PostgreSQL (Primary)   • Prometheus                 │
│  • Redis                  • pgvector               • Loki                       │
│  • Gitea                  • MinIO (备份)            • Grafana                   │
│  • ArgoCD                 • PostgreSQL (Standby)    • AlertManager              │
│  • Traefik Ingress          [Streaming Replication  • AIOps Pipeline            │
│                              → mini-pc-a]           • Tekton CI Runners         │
│                                                                                 │
│  ←── 任意一台宕机，etcd 保持 2/3 quorum，集群管理面继续运行 ──────────────────→  │
└─────────────────────────────────────────────────────────────────────────────────┘

  gpu-server (RTX 4090 · 128GB)          mac-mini-1 / mac-mini-2 (M4 · 16GB × 2)
  K3s Agent · label: workload=gpu        K3s Agent (OrbStack ARM Linux VM)
  ─────────────────────────────          ────────────────────────────────────────
  • Ollama (Qwen2.5-32B / DeepSeek-R1)   • bifrost-trade-frontend (Nginx)
  • Open-WebUI                           • Tekton CI Runners (轻量构建)
  • bifrost-trade-socket                 • 开发调试环境
  • bifrost-trade-worker (Celery)        • kubectl 客户端（直连集群 API）
  • 未来：模型微调 / 回测加速
```

---

## §4 PostgreSQL 部署方案

### 架构原则

| 层级 | 内容 | 说明 |
|------|------|------|
| 存储 | `local-path` PVC | 直接使用 mini-pc-b 本地 NVMe，最高 IO 性能 |
| 调度 | `nodeAffinity` 绑定 mini-pc-b | Primary 永远在专用节点上 |
| 高可用 | Streaming Replication | Standby 在 mini-pc-a，Primary 宕机自动 failover |
| 备份 | WAL 归档 → MinIO | 支持任意时间点恢复（PITR） |
| 管理 | CloudNativePG Operator | 声明式 YAML，Operator 处理 failover/备份/扩缩 |

### 数据文件物理路径

```
mini-pc-b（宿主机）
└── /var/lib/rancher/k3s/storage/pvc-[uuid]/   ← local-path PVC 实体
    └── PGDATA/
        ├── base/          ← 表数据
        ├── pg_wal/        ← 预写日志
        └── postgresql.conf

PostgreSQL Pod（容器内视角）
└── /var/lib/postgresql/data                   ← 挂载自上方 PVC（内容相同）
```

### 关键配置摘要

```yaml
# CloudNativePG Cluster（目标配置，尚未实施）
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: bifrost-postgres
  namespace: data
spec:
  instances: 2                        # Primary (mini-pc-b) + Standby (mini-pc-a)
  storage:
    size: 500Gi
    storageClass: local-path
  affinity:
    nodeAffinity:
      requiredDuringScheduling:
        nodeSelectorTerms:
          - matchExpressions:
              - key: node-role
                values: ["postgres"]  # mini-pc-b 打此 label
  postgresql:
    parameters:
      shared_buffers: "8GB"           # mini-pc-b 32GB 的 25%
      effective_cache_size: "24GB"
      max_connections: "200"
  backup:
    barmanObjectStore:
      destinationPath: s3://postgres-backup
      endpointURL: http://minio.data.svc:9000
```

---

## §5 CI/CD 平台

### 自建 vs GitHub 的决策依据

| 维度 | 自建（Gitea + ArgoCD）| GitHub Actions |
|------|----------------------|----------------|
| 交易策略代码安全 | 永不离开内网 | 上传至第三方服务器 |
| API Key 等凭证 | K3s Secret 内部管理 | 第三方托管 |
| CI 执行速度 | RTX 4090 直接运行，无排队 | 共享 Runner，高峰期排队 |
| 集成测试 | 直连内网 PostgreSQL/Redis | 需 tunnel 或 mock |
| 费用 | 零（使用自有硬件）| 按分钟计费 |
| GPU 测试 | RTX 4090 直接跑 | GPU Runner 极贵 |
| 断网可用性 | 可离线操作 | 完全依赖公网 |

**结论**：交易系统核心资产不经过任何第三方，选自建。

### GitOps 工作流

```
开发者 / AI Agent
      │ git push
      ▼
   Gitea（代码托管）
      │ webhook
      ├──► Tekton Pipeline（构建 + 测试 → 推送镜像到内网 Registry）
      └──► ArgoCD（检测 Git 变更 → 自动 apply 到 K3s 集群）
                │
                ▼
          K3s 集群（对应 namespace 的 Deployment 滚动更新）
```

### 部署位置

- **Gitea、ArgoCD、Tekton**：部署在 K3s 内部（`cicd` 命名空间），绑定 Mini PC 节点（稳定，非 GPU 节点）
- **紧急备用**：每台 Mini PC 本地保留 `scripts/emergency-deploy.sh`，集群 API 可达即可执行 `kubectl apply`，不依赖 ArgoCD

---

## §6 AI 原生运维平台

### 四层架构

```
Layer 4 · 自动化层（AI 本能反应）
─────────────────────────────────
AlertManager → Webhook → AI 分析 → 自动修复 or 推送诊断给人工

Layer 3 · 执行层（AI 的手）
────────────────────────────
K8s API · ArgoCD API · Gitea API · Bifrost 业务 API

Layer 2 · 推理层（AI 的大脑）
──────────────────────────────
Ollama (RTX 4090) · mcp-server-kubernetes · Open-WebUI

Layer 1 · 观测层（AI 的眼睛）
──────────────────────────────
Prometheus · Loki · Grafana · K8s Events Stream
```

### MCP Server for Kubernetes

Claude Code 通过 `mcp-server-kubernetes` 直接操作集群，无需手动 kubectl：

```
Mac Mini（开发机）
└── Claude Code
    └── mcp-server-kubernetes ─── 连接 K3s API Server
        ├── list_pods(namespace)
        ├── get_pod_logs(pod, namespace, tail_lines)
        ├── describe_node(node)
        ├── apply_manifest(yaml_content)
        ├── kubectl_exec(pod, command)
        └── get_events(namespace)
```

### 操作权限分级

| 级别 | 操作类型 | 执行方式 |
|------|---------|---------|
| 1 · 读 | get/describe/logs/metrics 查询 | AI 直接执行，无需确认 |
| 2 · 例行运维 | rollout restart · scale · pod delete · argocd sync | AI 直接执行，写审计日志 |
| 3 · 结构变更 | StatefulSet · PVC · RBAC · Ingress · Namespace 修改 | AI 提 Gitea PR → 人工 approve → ArgoCD 自动部署 |

### 自动化告警响应

```
触发条件                  AI 动作                         结果
─────────────────────────────────────────────────────────────────────
Pod CrashLoopBackOff     分析近 100 行日志                自动重启 + 推送诊断
磁盘用量 > 80%           分析数据增长来源                  建议清理策略 + 告警
API 延迟突增             关联最近部署记录                  定位变更点 + 可选回滚
trading daemon 停止      检查 IB 连接 / DB 连接            分步诊断 + 自动恢复
每日凌晨定时              汇总集群健康状态                  推送日报到手机
```

### 外部哨兵（K3s 之外）

部署在 Mac Mini 上（不依赖 K3s），解决"谁来监控监控者"问题：

```bash
# cron: */1 * * * *
# 若集群 API 或 Grafana 失联超过 3 分钟，发送推送通知
curl -sf https://k3s-api:6443/healthz || notify "K3s API 失联"
curl -sf https://grafana.internal/api/health || notify "Grafana 失联"
```

---

## §7 命名空间与服务分配

| 命名空间 | 服务 | 节点绑定 |
|---------|------|---------|
| `data` | PostgreSQL Primary · Standby · Redis · MinIO | mini-pc-b / mini-pc-a |
| `cicd` | Gitea · ArgoCD · Tekton · Container Registry | mini-pc-a |
| `monitoring` | Prometheus · Loki · Grafana · AlertManager | mini-pc-c（第二批）|
| `ai` | Ollama · Open-WebUI · AIOps Webhook Service | gpu-server / mini-pc-c |
| `bifrost` | bifrost-trade-api (×9) | mini-pc-a / mini-pc-b |
| `bifrost` | bifrost-trade-worker · bifrost-trade-socket | gpu-server |
| `bifrost` | bifrost-trade-frontend | mac-mini-1 |

---

## §8 从 Docker Compose 到 K3s 的映射关系

| Docker Compose 概念 | K3s / K8s 等价物 |
|--------------------|----------------|
| `services:` 无状态服务 | `Deployment` + `ClusterIP Service` |
| `services:` 有状态服务（PostgreSQL/Redis）| `StatefulSet` (CloudNativePG/Bitnami Helm) |
| `ports:` 宿主机端口映射 | `Ingress` (Traefik) + `ClusterIP`（内部服务互不暴露）|
| `volumes:` 数据卷 | `PersistentVolumeClaim` |
| `depends_on:` | `readinessProbe` + `initContainer` |
| `.env` 文件 | `ConfigMap`（非敏感）+ `Secret`（敏感凭证）|
| `networks:` 内网别名 | Service DNS（`<service>.<namespace>.svc.cluster.local`）|
| `docker compose up` | `argocd app sync` or `kubectl apply -k` |

---

## §9 实施路线图

### 阶段 0（当前）：代码迁移继续推进

- Docker Compose 仍是当前生产部署方式（`docker-compose.yml`）
- K3s 实施不阻塞 bifrost-trade-worker / api / frontend 的代码迁移

### 阶段 1：K3s 基础集群搭建

- [ ] mini-pc-a 安装 Ubuntu 24.04 LTS，部署 K3s Server（单节点先跑通）
- [ ] gpu-server 安装 K3s Agent，打 `workload=gpu` label，验证 GPU 调度
- [ ] Mac Mini ×2 安装 OrbStack，加入集群作 Agent 节点
- [ ] mini-pc-b 安装 Ubuntu，部署 K3s Server（扩展为 HA etcd 3 节点待 mini-pc-c）
- [ ] 安装 CloudNativePG Operator，验证 PostgreSQL StatefulSet + PVC

### 阶段 2：CI/CD 平台上线

- [ ] 部署 Gitea（迁移代码仓库）
- [ ] 部署 ArgoCD（接管现有 docker-compose 服务的 GitOps 管理）
- [ ] 部署 Tekton + Container Registry（内网镜像构建）
- [ ] 配置 `mcp-server-kubernetes`（让 Claude Code 可直接操作集群）

### 阶段 3：观测与 AI 平台

- [ ] 部署 kube-prometheus-stack（Prometheus + Grafana + AlertManager）
- [ ] 部署 Loki（日志聚合）
- [ ] 部署 Ollama on gpu-server（Qwen2.5-32B 或 DeepSeek-R1-32B）
- [ ] 部署 Open-WebUI（接入 Prometheus/Loki API + K8s API）
- [ ] 实现 AIOps Webhook Service（AlertManager → AI 分析 → 自动处理）

### 阶段 4：mini-pc-c 加入（Legacy 退役后）

- [ ] Legacy 服务完成迁移，验证新系统稳定运行
- [ ] mini-pc-c 加入集群，形成完整 3-Server HA
- [ ] 监控栈迁移到 mini-pc-c 专用节点
- [ ] Legacy Linux Server 退役或转为备用节点

---

## §10 现状检查点（用于对比）

> 每次架构调整后，在下表更新实际状态。

| 目标 | 规划 | 实际完成 | 对比说明 |
|------|------|---------|---------|
| K3s Server 首节点 | mini-pc-a | — | 未开始 |
| K3s HA (3 Server) | mini-pc-a/b/c | — | 待 mini-pc-c 加入 |
| PostgreSQL on K3s | CloudNativePG + local-path | — | 未开始 |
| PostgreSQL Streaming Replication | Primary(b) + Standby(a) | — | 未开始 |
| Gitea 自建代码托管 | cicd namespace | — | 未开始 |
| ArgoCD GitOps | cicd namespace | — | 未开始 |
| Ollama on RTX 4090 | ai namespace | — | 未开始 |
| mcp-server-kubernetes | Mac Mini 本地 | — | 未开始 |
| Prometheus + Grafana | monitoring namespace | — | 未开始 |
| Loki 日志聚合 | monitoring namespace | — | 未开始 |
| AIOps Webhook | ai namespace | — | 未开始 |
| 外部哨兵 watchdog | Mac Mini cron | — | 未开始 |
| Docker Compose → K3s 全迁移 | bifrost namespace | — | 代码迁移完成后进行 |
