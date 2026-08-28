---
name: research-release
description: >-
  发布 bifrost-research 到 K3s（Research OLAP payload）。Use when releasing
  research-api / research-mcp, bumping the research image version, running
  bifrost-deliver-research, or debugging ImagePullBackOff / mirror-sync /
  kaniko failures in the research namespace.
parity-id: research-release-v1
---

# Research 发布流程

Research 是**第二 payload**（决策载荷），与 Satellite（执行载荷）平级 —— 不是 subcontractor。
它走 payload 级完整交付链，不是 plugin 级的 clone+kaniko。

**本机不需要 Docker。** 构建由集群内 Kaniko 完成。

---

## ⛔ 顺序铁律

```
构建镜像 → 确认 registry 中 tag 存在 → 再 bump manifest → 才推 GitHub
```

`bifrost-research` 的 **ArgoCD Application 直连 GitHub 且开着 automated sync**
（`bifrost-trade-infra/k8s/cicd/applications/bifrost-research.yaml`）。
**推 manifest 等同于直接改运行时。** 顺序反了就是 ImagePullBackOff。

这条规则不是风格偏好 —— 2026-08-28 曾因先 bump 后构建把 DEV 的 research-api
拉挂 73 分钟。

---

## 前置检查（每次必做）

```bash
# 1. 该 repo 是否被 ArgoCD 自动纳管？（research = 是）
kubectl get application bifrost-research -n cicd \
  -o jsonpath='{.spec.syncPolicy}{"\n"}{.spec.source.repoURL}{"\n"}'

# 2. registry 里已有哪些 tag？
curl -s http://192.168.10.73:30500/v2/bifrost-research/tags/list

# 3. Gitea 镜像是否已同步到最新 commit？（Kaniko 从 Gitea clone，不是 GitHub）
git -C bifrost-research rev-parse origin/main
```

---

## 发布步骤

### 1. 代码就绪

```bash
cd bifrost-research && make lint && make test
```

bump `pyproject.toml` + `src/bifrost_research/__init__.py` + `tests/test_package.py`
的版本断言（三处必须一致，否则 `make test` 失败）。**先不要动 `k8s/` 下的 image tag。**
提交并推 GitHub。

### 2. 构建镜像（集群内）

**推荐 —— 经 Ops Console：** Launch Desk → Research → 填 image tag → Launch Research

**或经 platform-api：**

```bash
curl -s -X POST -H "Authorization: Bearer $PLATFORM_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" -d '{"revision":"main","tag":"0.30.0"}' \
  http://127.0.0.1:8780/api/v1/delivery/pipelines/bifrost-deliver-research/runs
```

链条：`mirror-sync → clone → kaniko → rollout → verify → gitops-sync`

> 首次构建某个新版本时 `verify-research` **会失败**，这是**正确的** ——
> 它断言 Deployment 实际跑的 tag == 本次构建的 tag，而此时 manifest 还没 bump。
> 前四步成功 + registry 出现新 tag 即表示构建成功，继续第 3 步。

### 3. 确认 tag 已入库

```bash
curl -s http://192.168.10.73:30500/v2/bifrost-research/tags/list | grep -o '"0.30.0"'
```

**这一步不能跳过。**

### 4. bump manifest 并推送

`k8s/` 下有 **26 处独立钉版本**，按组件选择要改哪些：

| 组件 | 文件 | 何时需要升 |
|------|------|-----------|
| `research-api` | `k8s/api/deployment.yaml` | API / SEPA / Copilot 端点变更 |
| `research-mcp` | `k8s/mcp/deployment.yaml` | **MCP 工具变更**（`mcp/tools/*`） |
| CronJob engines | `k8s/engines/*.yaml` 等 | engines / scheduler 变更 |
| dagster | `k8s/orchestration/dagster.yaml` | 当前 replicas:0，通常不动 |

> **易错点**：新增 MCP 工具只升 `research-api` 是**无效的** —— 工具跑在
> `research-mcp` 里。2026-08-28 就踩过：api 升到 0.30.0 后工具仍未上线，
> 因为 mcp 还停在 0.28.1。

推 GitHub 后 ArgoCD 自动收敛，或手动催：

```bash
# MCP: mcp__bifrost-platform__gitops_sync_app { name: "bifrost-research" }
```

### 5. 验收

```bash
kubectl get deploy research-api research-mcp -n research \
  -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,READY:.status.availableReplicas
curl -s http://192.168.10.73:30882/api/plugin/research/health
```

`version` 字段应等于新 tag，`startup_ok: true`。

---

## 排障

| 症状 | 原因 | 处理 |
|------|------|------|
| `ImagePullBackOff` | manifest 指向 registry 中不存在的 tag（顺序反了） | 回退 manifest 到已存在的 tag 并推送，ArgoCD 自动恢复；再按正确顺序重来 |
| `clone-research` 失败 | Gitea 镜像里没有该 repo 或未同步 | `make k3s-bootstrap-gitea-mirrors`（`MIRROR_REPOS` 含 `bifrost-research`） |
| kaniko `exec format error` | 调度到了 ARM 节点 | PipelineRun 必须带 `nodeSelector: kubernetes.io/arch=amd64`（platform-api 自动注入） |
| `rollout-research` 403 | SA 权限 | `rollout-research` / `verify-research` / `gitops-sync` 须用 `tekton-deliver` SA |
| `verify-research` 报 tag 不匹配 | manifest 未 bump | 正常 —— 走第 3、4 步 |
| 工具/行为没变化 | 升错了 Deployment | 见第 4 步的组件对照表 |

## 相关文件

- 流水线：`bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-research.yaml`
- Task / RBAC：同目录 `task-deliver-research.yaml` · `rbac-deliver-research.yaml`
- ArgoCD：`bifrost-trade-infra/k8s/cicd/applications/bifrost-research.yaml`
- Console 页：`bifrost-platform/console/src/pages/ResearchReleasePage.tsx`
- 域归属：`AGENT_FACTS.md` §1 · `systemDomainCatalog.ts`

## D10

全链路 observe-only，只触及 `research` namespace，不涉任何交易执行路径。
