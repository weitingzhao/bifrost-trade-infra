---
name: code-health
description: >-
  代码健康度棘轮（duplication / oversized files / contract coverage / image spread）。
  Use when a code-health check fails, when lowering a baseline in baselines.env,
  when adding a metric to scan.sh, when reading Ops Console → Code Health, or when
  deciding whether a conclusion rests on verified code or on stale memory.
parity-id: code-health-v10
---

# 代码健康度棘轮

运行时健康（Control Room / Observability）回答**「它在跑吗」**；
这套机制回答**「跑着的东西还维护得动吗」**。集群全绿和代码腐烂可以同时成立。

- 采集：`agent-config/scripts/code-health/scan.sh`（工作区根 `scripts/code-health/`）
- 基线：同目录 `baselines.env`
- 可视：Ops Console → Mission Control → **Code Health**；Observability 内每域一条汇总 signal（仅 OVER 降级，贴顶不翻舰队）
- **覆盖（v10）**：11 git repos in multi-root workspace · 4 domain 展示块（无静默死角）

| Domain | Repos | Metrics |
|--------|-------|---------|
| Rocket | `bifrost-platform` · `bifrost-ui` · **`bifrost-trade-infra`** | oversized · infra shell/py dup |
| Satellite | `bifrost-trade-frontend` · `bifrost-trade-api` · `bifrost-trade-core` · `bifrost-trade-worker` | dup · oversized · FE contract |
| Research | `bifrost-research` | dup · oversized · image tiers |
| Subcontractors | `bifrost-platform-plugin{,-market-data,-flex-query}` | dup · oversized |

**Out of scope（须在 Console Coverage 列出）**：`Research-workspace`（无 `.git`）· `bifrost-trade-socket`（已 Archive/移出）· `bifrost-analytics`（并入 research dbt，不在 multi-root）
- 规划 lens：`bifrost-platform/console/src/lib/code-health/codeHealthLens.ts`（slack / at ceiling / paydown / **Posture Summary**）
- Agent 读取：MCP `get_code_health`；Console **Generate Agent Pack** / 侧栏 Sparkles（先 Live Re-scan，再生成可粘贴的 Code Refactor Agent Task Content）
- **Live Re-scan**：`POST /api/v1/code-health/rescan`（operator）跑本机 `scan.sh`；`GET` 带回 `freshness.stale_vs_head`。**Refresh 只重拉快照**。
- **不在 UI 生成 Suggested Cuts** — playbook 已退役。切点由 IDE Agent 读 offender 后提出；Console 只提供机械量尺 + Agent Task Content pack。

---

## 两套语言（不要合成一个分）

| 语言 | 问题 | 表现 |
|------|------|------|
| **闸门** | 能不能合？ | `value > baseline` → CI / pre-commit 退出 1 |
| **规划** | 债有多重？下一刀砍哪？ | `slack = baseline − value`；贴顶（slack 0）= 黄灯；paydown 队列 |

**禁止**加权综合健康分 / A–E / 技术债美元。维度（size / duplication / contract / image_spread）只做分组标签。

**Posture Summary**（页顶 + 侧栏 title + Ask pack）：一句 `Gate CLEAR|BLOCKED · Planning AT CEILING|HELD|NOT OBSERVED · headroom`，再加 Dimensions chips / Next / Trend — **仍不是分数**。

**Lower baseline 工作流**（IMPROVED）：页上 **BASELINE LOWERING OWED** / 行内 Lower… → 对话框只允许把 `baselines.env` 常量改成 **scan 打印的 value**（Copy patch / Copy for Agent）。Console **不写** 文件；在 `bifrost-trade-infra` 改并 `scan.sh --report`。禁止抬高基线。

规划灯（页 + 侧栏，**不是** Observability 舰队）：

```
未上报            → unknown / NOT OBSERVED
任一 OVER         → fail
无 OVER 且 minSlack=0 → degraded（AT CEILING）
有余量            → ok（HELD）
```

Observability `code-health.*` 仍为 `role: evidence`：只有 OVER → degraded；贴顶保持 healthy（不误伤舰队）。

---

## ⛔ 核心契约：没测量 ≠ 健康

链路每一层都必须把「无数据」和「测过且干净」区分开：

| 层 | 无数据时的表现 |
|----|---------------|
| `scan.sh` | repo 缺失 → `NOT MEASURED`；`--repo` 名字不认识 → 退出 2；一个指标都没产出 → 退出 2 |
| `GET /api/v1/code-health` | `reported: false` + note，**不返回空的健康对象**；附带 `freshness`（`stale_vs_head` / `rescan_available`） |
| `POST /api/v1/code-health/rescan` | operator；本机跑 `scan.sh`，`source=live-rescan`；集群内常无 workspace → `rescan_available: false` |
| Observability signal | `optionalContract: true` → `NOT OBSERVED` |
| Code Health 页 / 侧栏 | 琥珀 `NOT OBSERVED` + 产出读数的命令；贴顶用黄灯，不用绿 HELD 假装健康；**STALE VS HEAD** 时先 Live Re-scan / Generate Agent Pack |

改这条链上任何一环时，先问：**没数据会不会被显示成绿的？贴顶会不会被当成「很健康」？** 会，就是 bug。

---

## 棘轮规则

```
value > baseline  → 退出 1，拒绝合并
value = baseline  → 放行（规划：AT CEILING）
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
# Console Live Re-scan ≡ POST /api/v1/code-health/rescan（DEV platform-api + workspace）
```

`--root <path>` 用于 CI：工作区里只有部分 repo，向上查找找不到工作区根。

Live Re-scan 环境（可选）：`BIFROST_WORKSPACE_ROOT`（stocks 根）、`PLATFORM_CODE_HEALTH_SCAN_SH`（测试替身）。默认：`PLATFORM_PROJECT_ROOT` 的父目录若含 `scan.sh` 即工作区。

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
6. 若指标不是「越低越好」，必须在 `codeHealthLens` 显式声明方向 — 默认全部 lower-is-better

---

## 当前强制点（2026-08-31 Wave 5）

| 位置 | 状态 |
|------|------|
| `bifrost-trade-frontend/.husky/pre-commit` | ✅ `check:legacy-css` + `check:code-health` |
| `bifrost-platform/.husky/pre-commit` | ✅ `check:code-health`（console `npm install` → husky） |
| `bifrost-research/.githooks/pre-commit` | ✅ `make install-hooks` / `make install-dev` |
| `bifrost-ci-{frontend,platform,python}` Tekton | ✅ Triggers + Gitea push webhook；**python-ci 含 research + trade-api/core/worker** |

CI 链：Gitea push → `el-bifrost-ci` → CEL 路由 → PipelineRun → `bifrost-code-health` Task。
安装：`make k3s-install-ci-triggers` + `make k3s-install-ci-webhooks`；校验 `make k3s-verify-ci-triggers`。

**闸门语言**：只有 OVER 拦合入；贴顶（AT CEILING）放行但规划灯黄。
**规划语言**：见 Posture Summary / paydown（Console Code Health）。

---

## 认知新鲜度

`bash scripts/check-agent-config-parity.sh` 第 6 节比对各 repo 与 `origin/main`。
会话开始、长时间中断恢复后必跑。

**结论必须标注来源**：是「基于刚核实的代码」还是「基于可能过时的记忆」。
本项目 Cursor 与 Claude Code 并行维护，两天内改动可达代码库的 11%；
凭记忆给出的镜像版本、replicas、目录结构，很可能已经失效而你不会察觉。
