# Wave 14G-F — Trade Socket 退役设计

> **Status:** Phase 0–2 **DONE**（2026-08-31）· Phase 3 archive marker 已落；workspace 移出待 ≥90 天  
> **Date:** 2026-08-24（design）· Phase 0–2 executed 2026-08-31  
> **Owner gate:** D-14GF.1–6 **同意推荐 R1**；Owner 授权「继续」执行 Phase 1+（结论 C）  
> **D10:** 本 Wave **不触达** live trading unlock；Operator 退役只清进程/镜像/文档，不解锁发单

---

## 0. 一句话结论

**Prod K3s 上 IB 实时总线已由 Platform IB Gateway Plugin → `redis-ib` 承接（IBGP3/4 done）；`bifrost-trade-socket` 是最大半退役技术债块。**  
运行时仍「默认能起」的路径主要在 **本地 `docker-compose.dev.yml`（无 profile，三进程默认启动）** 与 **Tekton/Kaniko 仍 build `bifrost-socket` 镜像**；K3s base 清单几乎已空，但镜像 rename、retire 脚本、Console catalog、API/FE「Socket」命名面仍大量残留。

**本文件是设计 + Owner 决策清单，不是实施授权。**

---

## 1. 事实核查摘要（只读扫描 · 2026-08-24）

### 1.1 仓库体量

| 项 | 值 |
|----|-----|
| `bifrost-trade-socket` | **52** 个 `.py` · **~10.4k** LOC |
| 包职责（CLAUDE.md） | IB ingestor / account_agent / operator 参考实现；Massive WS **已 RETIRED (P7)** |
| 生产权威路径 | Plugin `data/ib-gateway` → `redis-ib.data.svc.cluster.local`（契约兼容 legacy Redis key） |

### 1.2 触点数量级（文件级 grep，排除 node_modules / .git）

| 区域 | 约文件数 | 性质 |
|------|----------|------|
| `bifrost-trade-infra` | **~49** | compose、Dockerfile.socket、Tekton、retire 脚本、docs、Makefile、image rename |
| `bifrost-platform` | **~25** | environments-catalog SOCKET 标签、deliveryTargets、criticalProcesses 兼容名、git-bridge mirror、历史 migrate waves |
| `bifrost-trade-api` | **~30** | `/status` socket 块、ops workload map、ib-ingestor logs 路由、market_ingest 文案 |
| `bifrost-trade-frontend` | **~36** | Settings → Socket 页、`IbBrokerConnection`、topology `kind: 'socket'`（**UI 面，非进程**） |
| `bifrost-trade-core` | **~8** | `ib_operator` Redis client、`ib_socket_status` / `platform_ib_gateway` 集成 |
| `bifrost-trade-worker` | **极少** | 运行读 `redis-ib`；CLAUDE 仍写「ib-edge Operator」属文档漂移 |
| `bdev` / `sessions.yaml.example` | **0** | **不**启动 socket 进程 |

### 1.3 现状拓扑

```
┌──────────────────────────── Prod / STG / DEV (K3s) ────────────────────────────┐
│  Win11 TWS (.30 / .32)                                                         │
│       ↑                                                                        │
│  data/ib-gateway (Platform Plugin) ──write──► redis-ib (data NS)               │
│       ↑ ExternalName redis-ib                                                  │
│  bifrost-{dev,stg,prod}: api-market / daemon / account-sync ──read──► redis-ib │
│  legacy STS ib-market-gateway / ib-account-agent / ib-operator — 退役脚本已有  │
│  k8s/base/socket/ — 仅 README + ib-socket-rbac.yaml（无 Deployment 清单）      │
└────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────── docker-compose.yml (prod compose) ─────────────────┐
│  ib-ingestor / ib-account-agent / ib-operator                                  │
│  → 已挂 profiles: [legacy-ib]   ← 默认 make prod 不会起                        │
│  docker-compose.local.yml 仍定义 bifrost-socket:local 构建与三服务 override      │
└────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────── docker-compose.dev.yml (make dev) ─────────────────┐
│  挂载 ../bifrost-trade-socket                                                  │
│  ib-ingestor / ib-account-agent / ib-operator — **无 profile，默认启动**        │
│  ← 与 TRADE_DEV_INNER_LOOP（假定 redis-ib）冲突的最大本地债                     │
└────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────── 本机 bdev / Vite Inner Loop ───────────────────────┐
│  trade-ui :5173 → K3s DEV API :30882 → redis-ib（Plugin）                      │
│  sessions.yaml.example — 无 socket session                                     │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 依赖矩阵：谁还「需要」socket **进程**？

| 消费者 / 表面 | 需要 trade-socket 进程？ | 实际依赖 |
|---------------|--------------------------|----------|
| K3s Trade API / daemon / account-sync | **否** | `redis-ib` + Plugin Gateway（Redis 协议） |
| Trade FE Settings → Socket | **否** | Monitor `GET /status` 的 `socket.*` JSON（命名遗留；transport=`platform_gateway`） |
| Platform Console Critical Processes | **否** | 已 fallback 到 `data/ib-gateway`；仍保留 legacy 名匹配 |
| `make dev` compose | **仅当 Owner 要本地直连 TWS 调试** | 当前默认起三进程 → **应视为可选债** |
| `docker-compose.yml` + `legacy-ib` profile | **可选遗留** | 已 profile 化 |
| Tekton deliver STG/PROD | **否（运行时）** | 仍 **build** `bifrost-socket:stg`（浪费 CI + 镜像） |
| Operator RPC（`ib:operator:cmd`） | **否 → Plugin** | `bifrost_core.ib_operator` 只认 Redis；谁写结果谁就是 Operator。**无代码级「fallback 到 trade-socket 进程」**；风险是双写（compose 与 Plugin 同时监听） |
| Massive / Polygon WS | **否** | 已 Plugin `polygon-ws-ingestor` → `redis-massive` |
| bdev | **否** | 零引用 |

### 1.5 Plugin 是否已完全替代三进程？

| Socket 进程 | Plugin 替代 | Redis 契约 |
|-------------|-------------|------------|
| ib-ingestor / ib-market-gateway | `data/ib-gateway` MD 路径 | `ib:ingester:tick:*` 等（`redis_keys.py` 标明 must match trade-socket） |
| ib-account-agent | 同 Pod 账户路径 | `ib:account:*` |
| ib-operator | 同 Pod Operator RPC | `ib:operator:cmd` / `result:*`（`protocol.py`: compatible with bifrost-trade-socket） |

**结论：** 契约层已替代；**残留的是编排 / 镜像 / 文档 / UI 命名 / 本地 compose，不是功能缺口。**

### 1.6 CI / Tekton / Kaniko（仍 build socket）

- `k8s/cicd/docker/Dockerfile.socket-stg`
- `k8s/cicd/tekton/task-kaniko-worker-socket-stg.yaml` → destination `bifrost-socket:${TAG}`
- `pipeline-deliver-stg.yaml` / `pipeline-deliver-prod.yaml` 调用该 task
- Gitea mirror 列表含 `bifrost-trade-socket`
- overlays `{dev,stg,prod}/kustomization.yaml` 仍有 `bifrost-socket` image rename（无对应 workload 时为死映射）

### 1.7 已有退役工具（实施时可复用，本 Wave 不执行）

- `scripts/k3s/retire-legacy-ib-socket.sh`
- `scripts/k3s/cleanup-legacy-ib-deployments.sh`
- `make k3s-cleanup-legacy-ib-deployments`
- verify 脚本中对 legacy STS 的 **absent** 断言（如 `verify-phase-b-stg-v2.sh`、`verify-w11-trade-k8s-native.sh`）

---

## 2. 目标（Owner 确认后的技术债清理）

1. **运行时唯一 IB 边缘：** Plugin Gateway + `redis-ib`（所有环境 + 本地 Inner Loop）。
2. **默认路径零 socket 进程：** `make dev` / prod compose / K3s 均不起 trade-socket。
3. **停止 build/publish `bifrost-socket` 镜像**；从 deliver pipeline 与 mirror 列表移除（或显式标记 archived）。
4. **`bifrost-trade-socket` repo：** 按 Owner 决策归档 / 移出工作区 / 保留参考期。
5. **命名债可分期：** FE/API `socket.*` 字段与 Settings「Socket」页可后续 rename（非本 Wave 阻断）；本 Wave 聚焦 **进程与构建面**。
6. **D10 不变：** 不因退役而启用 live place_order。

---

## 3. 推荐方案与备选

### 推荐（R1）— 「默认全连 Plugin；短过渡期保留可选 profile」

| 决策点 | 推荐答案 |
|--------|----------|
| 本地 compose / `make dev` | **一律假定连 Plugin `redis-ib`**（与 `TRADE_DEV_INNER_LOOP.md` / D-IL3 对齐）。dev compose **移除默认启动** 的三进程；若过渡需要，仅通过显式 profile 启用。 |
| `bifrost-trade-socket` repo | **归档只读**（GitHub archive 或 `ARCHIVED.md` + 工作区移出可选）；保留 **≥1 个 tag** 作契约考古；**不**作为日常开发依赖。建议参考保留期 **90 天** 后移出多仓 workspace。 |
| 过渡期 profile | **允许** 短期 `legacy-ib` / `legacy-socket` profile（prod compose **已有** `legacy-ib`）。dev 对齐同一命名；过渡结束后删除 profile + Dockerfiles。 |
| Operator RPC | **确认仅 Plugin Gateway**；禁止任何「compose operator 作为 fallback」文档或默认路径。Verify：集群内无 trade-socket operator Pod；本机默认 compose 无 operator 容器。 |

**理由：** Inner Loop 与 Prod 已同构在 `redis-ib`；继续默认起 socket 会制造 **双写 TWS / 双写 Redis** 风险，并拖累 `make dev` 安装面。Profile 给排障留后门，但不进默认路径。

### 备选（A1）— 「立即硬切，无 profile」

- 一次删掉 compose 三服务 + 全部 Dockerfile.socket + Tekton socket task。  
- **优点：** 债清得最快。  
- **缺点：** 无本地「对照 legacy 实现」逃生舱；排障只能读归档 repo。  
- **适用：** Owner 确认 90 天内无人再跑 socket 源码调试。

### 备选（A2）— 「长期保留 repo 作参考，compose 永久 profile」

- repo 永不归档；`legacy-socket` profile 永久存在。  
- **不推荐：** 半退役状态会继续诱导 Agent/`make` 文档把 socket 当 live。

---

## 4. Owner 必须确认的决策题

请逐项批注 **同意推荐 / 改选备选 / 自定义**：

| ID | 问题 | 推荐 |
|----|------|------|
| **D-14GF.1** | 本地 compose / `make dev` 是否仍需要默认起 socket 三进程，还是一律假定连 Plugin `redis-ib`？ | **一律 `redis-ib`；dev 默认不起 socket** |
| **D-14GF.2** | `bifrost-trade-socket` repo：归档只读 / 移出工作区 / 保留参考实现多久？ | **归档只读 + 参考保留 90 天，再移出 workspace** |
| **D-14GF.3** | 是否允许过渡期 compose profile（`legacy-ib` / `legacy-socket`）可选启用？ | **允许短过渡（建议 ≤1 个 release cycle），到期删除** |
| **D-14GF.4** | Operator RPC：是否确认 **仅** Plugin Gateway，**无任何** fallback 到 trade-socket operator？ | **确认仅 Plugin；双写视为事故** |
| **D-14GF.5**（附加） | Tekton deliver 是否在下一轮 STG/PROD pipeline 中 **停止** build `bifrost-socket`？ | **是**（与 Phase 2 绑定） |
| **D-14GF.6**（附加） | FE Settings「Socket」页与 API `socket.*` JSON 是否本 Wave rename，还是仅文档标注「命名遗留」？ | **本 Wave 不 rename**（避免 FE/API 大 diff）；另开命名债 ticket |

**未获上述确认前：禁止删除 socket 代码、禁止改默认 compose、禁止从 pipeline 移除 Kaniko socket task。**

---

## 5. 分阶段实施清单（确认后另开执行；本文件不授权）

### Phase 0 — 文档 / 门禁 / catalog 对齐（低风险）

- [ ] 本设计 Owner 签批；PROGRESS / Migration Tracking 记「14G-F design signed」
- [ ] 更新 `environments-catalog.ts` SOCKET 条目为 **RETIRED / reference-only**（实施时）
- [ ] `TRADE_DEV_INNER_LOOP.md` / socket `CLAUDE.md` / worker `CLAUDE.md`：明确「勿启动 trade-socket」
- [ ] grep 门禁草案（CI 可选）：`docker-compose.dev.yml` 中无未 profile 的 `run_ib_*.py`
- [ ] **回滚点：** 仅文档/catalog → revert commit

### Phase 1 — compose 下线默认路径

- [ ] `docker-compose.dev.yml`：三进程加 `profiles: [legacy-ib]`（或删除）+ 去掉默认 volume 安装对 socket 的硬依赖（若 entrypoint 允许）
- [ ] 对齐 `docker-compose.yml` 已有 `legacy-ib`；文档写清启用方式
- [ ] `docker-compose.local.yml`：socket build 随 profile 或移除
- [ ] 验证：`make dev` 不起 `ib-*`；Live 仍走 K3s/`redis-ib`
- [ ] **回滚点：** 恢复 profile 前 compose；本地可 `--profile legacy-ib up`

### Phase 2 — infra / CI 清理

- [ ] 从 Tekton pipeline 移除或 skip `kaniko-worker-socket` 的 socket 半段；删 `Dockerfile.socket-stg` ConfigMap 刷新
- [ ] overlays image rename 去掉 `bifrost-socket`
- [ ] 清理 `k8s/base/socket/` RBAC / network-policy `ib-socket-egress`（若 verify 已 WARN）
- [ ] mirror 列表可选保留 repo（归档后仍可 mirror）或移除
- [ ] 跑既有 `retire-legacy-ib-socket` / verify-w11 / verify-phase-b 确认 STS absent
- [ ] **回滚点：** 恢复 Dockerfile CM + pipeline task；镜像可重建但 **不应** 再 scale STS

### Phase 3 — repo 归档

- [ ] GitHub archive / 根目录 `ARCHIVED.md`（指向 Plugin + 本设计）
- [ ] 工作区 `.code-workspace` 移除 socket 文件夹（Owner 确认后）
- [ ] Migration Tracking §3 标 **RETIRED**
- [ ] **回滚点：** unarchive + 加回 workspace（代码仍在 git 历史）

---

## 6. 风险与验收标准

### 风险

| 风险 | 缓解 |
|------|------|
| 本地开发者仍习惯 `make dev` 起 TWS 直连 | Phase 1 文档 + profile；Inner Loop 标准路径写清 |
| 双写：compose operator + Plugin 同时听 `ib:operator:cmd` | D-14GF.4；默认不起；verify 脚本检测非法 Pod/容器 |
| 误删仍被引用的 Redis 契约测试 | Plugin `tests/test_redis_contract.py` 为权威；socket 仅参考 |
| FE「Socket」页被误以为进程依赖 | D-14GF.6；页内文案已偏 Platform Gateway |
| D10 / 发单路径被连带「整理」 | **明确禁止**；本 Wave 不改 daemon execution 策略 |

### 验收（实施阶段）

```bash
# 1) 默认 compose 无 socket 容器（示例）
docker compose -f docker-compose.dev.yml config --services | grep -E 'ib-ingestor|ib-operator|ib-account' \
  && echo FAIL || echo PASS

# 2) K3s legacy STS absent
for ns in bifrost-dev bifrost-stg bifrost-prod; do
  for sts in ib-market-gateway ib-account-agent ib-operator; do
    kubectl get sts "$sts" -n "$ns" 2>/dev/null && echo FAIL || true
  done
done

# 3) redis-ib 拓扑
cd bifrost-trade-infra && make assert-redis-ib-topology

# 4) 门禁 grep（实施后）
rg -n 'run_ib_ingestor|run_ib_operator|run_ib_account_agent' docker-compose.dev.yml \
  && echo 'must be under profiles or absent'

# 5) CI：pipeline 不再 destination bifrost-socket（实施后）
rg -n 'bifrost-socket:' k8s/cicd/tekton/ && echo FAIL_or_doc_exception
```

Monitor：`socket.platform_ib_gateway` / `transport=platform_gateway`；Critical Processes 解析到 `data/ib-gateway`。

---

## 7. 明确非目标 / 不授权

- **本文件不授权：** 删除 `bifrost-trade-socket` 源码、改默认 compose、改 Tekton、archive repo、移出 workspace。
- **不做：** D10 unlock、daemon live place_order、改 Operator 协议 v1。
- **不做（本 Wave）：** 强制 rename API `socket.*` / FE 路由 `/settings/socket`（见 D-14GF.6）。
- **只读参考：** `bifrost-trader-engine` 仍只读；退役设计不依赖修改 engine。

---

## 8. 与既有 Wave / Program 的关系

| 既有产物 | 关系 |
|----------|------|
| IB Gateway Plugin IBGP0–4 | **已完成**功能替代；本 Wave 清半退役编排债 |
| `retire-legacy-ib-socket.sh` | 实施 Phase 2 复用 |
| `TRADE_DEV_INNER_LOOP.md` | 权威本地路径；与推荐 R1 一致 |
| Trade IB Client Migration catalog | 收尾项「archive bifrost-trade-socket ib/ references」与本 Wave 对齐 |
| Wave 2–6 DB hygiene docs | 风格参考；本文件为 **14G-F 独立设计** |

---

## 9. 签批区（Owner）

| 字段 | 值 |
|------|-----|
| Owner 签批日期 | **2026-08-31** |
| D-14GF.1 … D-14GF.6 | **同意推荐 R1**（一律 redis-ib；归档+90 天；短过渡 profile；仅 Plugin Operator；停 Tekton build；本 Wave 不 rename FE/API） |
| 授权进入实施 Phase | **Phase 0 已授权并执行**（文档 / catalog / 事实基线）。Phase 1+ 须另开「执行 14G-F Phase N」 |
| 设计作者 | Bifrost Agent（14G-F design）；Phase 0 执行 2026-08-31 |

### Phase 0 完成记录（2026-08-31）

- [x] 本设计 Owner 签批（D-14GF.1–6 R1）
- [x] `MIGRATION_TRACKING.md` §1.1 · `AGENT_FACTS.md` §4 记 14G-F Phase 0
- [x] `environments-catalog.ts` SOCKET → RETIRED / reference-only；IB edge 路径改 Platform Gateway
- [x] `TRADE_DEV_INNER_LOOP.md` Non-goals：勿启动 trade-socket
- [x] socket / worker `CLAUDE.md`：勿启动 / 无 fallback

### Phase 1 完成记录（2026-08-31）— Owner 授权继续（结论 C）

- [x] `docker-compose.dev.yml`：三进程 `profiles: [legacy-ib]`；默认 `config --services` 无 `ib-*`
- [x] `docker-compose.local.yml`：ib-* + base-socket 对齐 `legacy-ib`
- [x] prod compose 本已 `legacy-ib`（未改行为）

### Phase 2 完成记录（2026-08-31）

- [x] Tekton `bifrost-kaniko-worker-socket-stg` 仅 build worker；无 `--destination …/bifrost-socket:`
- [x] deliver STG/PROD 去掉 `clone-socket`；API Dockerfile 不再 pip install socket
- [x] `bifrost-trade-api` 去掉 `bifrost-socket` 依赖（0.1.6）
- [x] overlays `{dev,stg,prod}` 去掉 `bifrost-socket` image rename
- [x] prepare/refresh Dockerfile CM 列表去掉 socket

### Phase 3 部分完成（2026-08-31）

- [x] `bifrost-trade-socket/ARCHIVED.md`
- [x] **CI/CD + Gitea 清除（Owner 2026-08-31）**
  - mirror / webhook / trigger CEL / deliver `MIRROR_REPOS` 去掉 `bifrost-trade-socket`
  - 删除 `k8s/cicd/docker/Dockerfile.socket-stg`；deliver 脚本不再创建 `bifrost-socket-stg-dockerfile` CM
  - 集群：Gitea `bifrost/bifrost-trade-socket` 仓库与 webhook 已 DELETE（404）
  - Console `payloadConstellationCatalog` Trade `mirrorRepos` 去掉 socket
- [x] 移出 Cursor workspace — Owner 提前授权（2026-08-31）；`bifrost-trade.code-workspace` 去 folder；compose 默认路径不再挂载 socket
- [x] GitHub Archive — Owner 已 Archive `weitingzhao/bifrost-trade-socket`
- [x] 考古锚点 — GitHub `22bd9d6`；本地 `b0a59f5` + tag `archived-14gf`（archived remote 只读）；物理目录由 Owner 压缩备份后移出 `Desktop/stocks/`

*End of design — Wave 14G-F Trade Socket retirement.*
