---
name: code-health
description: >-
  代码健康度棘轮（duplication / oversized files / contract coverage / image spread）。
  Use when a code-health check fails, when lowering a baseline in baselines.env,
  when adding a metric to scan.sh, when reading Ops Console → Code Health, or when
  deciding whether a conclusion rests on verified code or on stale memory.
parity-id: code-health-v1
---

# 代码健康度棘轮

运行时健康（Control Room / Observability）回答**「它在跑吗」**；
这套机制回答**「跑着的东西还维护得动吗」**。集群全绿和代码腐烂可以同时成立。

- 采集：`agent-config/scripts/code-health/scan.sh`（工作区根 `scripts/code-health/`）
- 基线：同目录 `baselines.env`
- 可视：Ops Console → Mission Control → **Code Health**；Observability 内每域一条汇总 signal
- Agent 读取：MCP `get_code_health`

---

## ⛔ 核心契约：没测量 ≠ 健康

链路每一层都必须把「无数据」和「测过且干净」区分开：

| 层 | 无数据时的表现 |
|----|---------------|
| `scan.sh` | repo 缺失 → `NOT MEASURED`；`--repo` 名字不认识 → 退出 2；一个指标都没产出 → 退出 2 |
| `GET /api/v1/code-health` | `reported: false` + note，**不返回空的健康对象** |
| Observability signal | `optionalContract: true` → `NOT OBSERVED` |
| Code Health 页 | 琥珀 `NOT OBSERVED` + 产出读数的命令 |

改这条链上任何一环时，先问：**没数据会不会被显示成绿的？** 会，就是 bug。

---

## 棘轮规则

```
value > baseline  → 退出 1，拒绝合并
value = baseline  → 放行
value < baseline  → 放行，但要求调低 baseline
```

第三条不是客气话：**基线不调低，让出来的地会被悄悄吃回去**。
先例：`check-legacy-css.sh` 的 `RAW_PNL_PALETTE_BASELINE` 靠这条规则从 64 降到 37。

**基线只能填 `scan.sh` 亲口打印过的数**。手填的数没有意义 ——
人工统计不可靠正是这套机制存在的理由。

---

## 常用命令

```bash
make check-code-health                      # bifrost-trade-infra，全量
npm run check:code-health                   # bifrost-trade-frontend，只查 satellite
bash scripts/code-health/scan.sh --json -    # 机器可读（摘要走 stderr）
bash scripts/code-health/scan.sh --report    # 上报 platform-api（需 PLATFORM_OPERATOR_TOKEN）
```

`--root <path>` 用于 CI：工作区里只有部分 repo，向上查找找不到工作区根。

---

## 指标口径（改之前先读）

| 指标 | 口径 | 为什么这么定 |
|------|------|-------------|
| duplicated function names | 有 >3 处定义的**不同函数名个数**；排除 tests 与 dunder | 数的是「重复的概念」。加第 52 个 `_run` 不触发（框架接口不算腐化），出现一个**新的**重复名才触发 |
| files over 800 lines | git 跟踪的源文件行数 | 大到没人能通读的文件，就是下一个重复函数被写出来的地方 |
| API modules without schema | `src/api/*.ts` 里没接 `withValidation` / `lib/schemas` 的 | 两个 payload 独立发布后，没契约的端点漂移了没人知道 |
| research image tiers | `bifrost-research/k8s` 里不同的镜像 tag 数 | 每多一档，就多一个组件在跑没人追踪的代码 |

**只扫 `git ls-files`**：gitignore 排除的（node_modules / `.venv*` / dist）自动不算。
早期版本用 find + 排除列表，把 `.venv-docs` 里 37 个 pygments 文件算成了项目代码 ——
排除列表维护不完，git 的口径才是唯一不会漂的那个。

## 新增指标

1. 先在命令行把数量出来，确认口径不含第三方 / 生成代码 / 测试替身
2. `baselines.env` 加常量，值 = 脚本打印的数
3. `scan.sh` 里 `add_metric`（传**基线变量名**，不是值）
4. 超基线时必须能打印**完整违规清单** —— 只报数字不报位置的检查，人会直接静音它
5. 两个方向都要实测：造一处回归看是否退出 1；调高基线看是否提示下调

---

## 当前强制点（2026-08-31 实况）

| 位置 | 状态 |
|------|------|
| `bifrost-trade-frontend/.husky/pre-commit` | ✅ 生效（`check:legacy-css` + `check:code-health`） |
| `bifrost-ci-{frontend,platform,python}` Tekton | ✅ 已部署；Triggers + Gitea push webhook 已接通（Owner 批准，2026-08-31） |
| `bifrost-platform` / `bifrost-research` | ❌ 无 pre-commit hook |

CI 链：Gitea push → `el-bifrost-ci` → CEL 路由 → PipelineRun → `bifrost-code-health` Task。
安装：`make k3s-install-ci-triggers` + `make k3s-install-ci-webhooks`；校验 `make k3s-verify-ci-triggers`。

**`bifrost-research` 仍不在任何 CI 触发过滤器内**（python-ci 只覆盖 core/api/worker/socket），
所以第二 payload 有交付链但没有 CI 闸门 —— 对 research 不要说「CI 会拦住」。

---

## 认知新鲜度

`bash scripts/check-agent-config-parity.sh` 第 6 节比对各 repo 与 `origin/main`。
会话开始、长时间中断恢复后必跑。

**结论必须标注来源**：是「基于刚核实的代码」还是「基于可能过时的记忆」。
本项目 Cursor 与 Claude Code 并行维护，两天内改动可达代码库的 11%；
凭记忆给出的镜像版本、replicas、目录结构，很可能已经失效而你不会察觉。
