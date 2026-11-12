# agent-config — 工作区级 Agent 治理层

Bifrost 工作区（`/stocks`）的 Agent 治理资产。**实体在这里，工作区根是符号链接。**

放在 `bifrost-trade-infra` 是因为：治理层本属 Ops/infra 域，且这样才能纳入版本控制
并接入现有 CI 与 release gate —— 工作区根 `/stocks` 本身不是 git repo。

## 布局与链接

| 工作区根（符号链接） | 实体（本目录） | 内容 |
|---------------------|---------------|------|
| `/stocks/CLAUDE.md` | `CLAUDE.md` | 完整治理规则（只有这一份） |
| `/stocks/AGENT_FACTS.md` | `AGENT_FACTS.md` | 事实基线 |
| `/stocks/AGENTS.md` | `AGENTS.md` | 各家 Agent 的入口（Claude、Codex 等）：只放指针，不写规则正文 |
| `/stocks/DESIGN_CONTRACTS.md` | `DESIGN_CONTRACTS.md` | **三域设计契约** — Design 会话的唯一入站文件 |
| `/stocks/.mcp.json` | `.mcp.json` | Claude MCP：PROD VIP + `bifrost-local` + 仅 Claude 的 `bifrost-approve` |
| `/stocks/.mcp.json.README.md` | `.mcp.json.README.md` | MCP 说明（focus 桥、令牌分级） |
| `/stocks/.claude` | `claude/` | settings.json · skills · agents · commands · hooks |
| `/stocks/scripts` | `scripts/` | agent-guard、治理一致性检查（`check-governance-consistency.sh`）与提交血缘 git hook（`git-hooks/`） |
| （不链接） | `codex/` | Codex 的用户级配置说明（`~/.codex` 不进仓库）与检查脚本 `check-codex-guard.py` |
| `/stocks/PLAN-phase0-foundation-2026-10-05.md` | `work/PLAN-phase0-foundation-2026-10-05.md` | 阶段 0 计划 |
| `/stocks/REVIEW-architecture-discussion-round1-2026-10-05.md` | `work/` 下同名 | 架构讨论第一轮 |
| `/stocks/REVIEW-system-architecture-2026-10-05.md` | `work/` 下同名 | 系统架构评审 |
| `/stocks/REVIEW-trade-system-completeness-and-backtest-2026-10-04.md` | `work/` 下同名 | Trade 完整度与回测评审 |
| `/stocks/LEDGER-pine-tradingview-gaps.md` | `work/` 下同名 | Pine / TradingView 缺口账本 |
| `/stocks/REQUEST-symbol-paired-ddl-2026-10-06.md` | `work/` 下同名 | symbol 成对 DDL 申请 |
| `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md` | `work/` 下同名 | W3 删除前归档申请 |
| `/stocks/REQUEST-td96-preflight-d10-2026-10-06` | `work/REQUEST-td96-preflight-d10-2026-10-06/` | TD-96 preflight 草案（整个目录一条链接） |
| `/stocks/cursor-tasks/` 下已迁入的文件 | `work/cursor-tasks/` 同相对路径 | Cursor 还债任务与报告。目录本身留在工作区根 |

> 目录名故意用 `claude/` 而非 `.claude/`：避免把它误当成 infra repo 自己的配置目录而重复加载。
> 工作区级的 Cursor 一侧（`cursor/`：rules、skills、hooks 模板、安装脚本）已在清理第 2 波（2026-11-12）删除；
> 工作区根旧的 `.cursor` 链接指向已删目录，可以删掉（`rm /path/to/stocks/.cursor`）。

`cursor-tasks/` 不是整目录一条链接：扫描命中的三个文件留在工作区根，仍是普通文件
（`cursor-tasks/LANE-O-orphans.md`、`cursor-tasks/reports/LANE-D.md`、`cursor-tasks/reports/LANE-O.md`）。
下面的重建命令只链接已入库的路径。

## 重建符号链接

克隆到新机器、或链接损坏时，在工作区根执行：

```bash
cd /path/to/stocks && AC=bifrost-trade-infra/agent-config && \
  ln -sfn "$AC/claude" .claude && \
  ln -sfn "$AC/scripts" scripts && \
  ln -sf "$AC/CLAUDE.md" CLAUDE.md && ln -sf "$AC/AGENT_FACTS.md" AGENT_FACTS.md && \
  ln -sf "$AC/AGENTS.md" AGENTS.md && \
  ln -sf "$AC/DESIGN_CONTRACTS.md" DESIGN_CONTRACTS.md && \
  ln -sf "$AC/.mcp.json" .mcp.json && ln -sf "$AC/.mcp.json.README.md" .mcp.json.README.md && \
  mkdir -p cursor-tasks/reports && \
  for f in \
    PLAN-phase0-foundation-2026-10-05.md \
    REVIEW-architecture-discussion-round1-2026-10-05.md \
    REVIEW-system-architecture-2026-10-05.md \
    REVIEW-trade-system-completeness-and-backtest-2026-10-04.md \
    LEDGER-pine-tradingview-gaps.md \
    REQUEST-symbol-paired-ddl-2026-10-06.md \
    REQUEST-w3-archive-before-delete-2026-10-05.md \
    REQUEST-td96-preflight-d10-2026-10-06 \
    cursor-tasks/LANE-D-docs-inventory.md \
    cursor-tasks/LANE-D2-db-prepare.md \
    cursor-tasks/LANE-G-governance-docs.md \
    cursor-tasks/LANE-M-db-role-matrix.md \
    cursor-tasks/LANE-P-platform.md \
    cursor-tasks/LANE-R1-release-chain.md \
    cursor-tasks/LANE-R2-research-marketdata.md \
    cursor-tasks/LANE-S1-agent-security.md \
    cursor-tasks/LANE-S2-platform-api.md \
    cursor-tasks/LANE-T-trade-ib.md \
    cursor-tasks/LANE-T2-ib-status-and-quote-mirror.md \
    cursor-tasks/LANE-U-ui-infra.md \
    cursor-tasks/LANE-U2-ui-frontend.md \
    cursor-tasks/README.md \
    cursor-tasks/reports/LANE-D2.md \
    cursor-tasks/reports/LANE-G.md \
    cursor-tasks/reports/LANE-P.md \
    cursor-tasks/reports/LANE-R1.md \
    cursor-tasks/reports/LANE-R2.md \
    cursor-tasks/reports/LANE-S1.md \
    cursor-tasks/reports/LANE-S2.md \
    cursor-tasks/reports/LANE-T.md \
    cursor-tasks/reports/LANE-U.md \
    cursor-tasks/reports/LANE-U2.md \
  ; do ln -sfn "$AC/work/$f" "$f"; done
```

## 路径约定

- **提交血缘 hook 写在各 repo 的本地 git config 里**（`core.hooksPath` / `bifrost.hooksDir`，用真实绝对路径），不入库。
  克隆到新机器后在工作区根跑 `sh scripts/git-hooks/install.sh`；frontend、platform、research 里入库的转调存根在没跑过 install 的机器上什么也不做。

- **`claude/settings.json` 里的 hook 命令用本目录的绝对真实路径**，不经符号链接 —— 少一层解析、少一个故障点。
  换机器时这些绝对路径需要改（见上方 `AC` 变量）。
- **线程心跳**（W-54）：`scripts/thread-heartbeat.js` 是共用的心跳钩子，`claude/settings.json`、`codex/README.md` 里的 `~/.codex/hooks.json` 各接一份；Cursor 的无头运行（06 上 agentd 的 `exec:cursor`）用下面的 `run` 包装。
  回合开始、工具调用前后、回合结束各 POST 到 PROD `POST /api/v1/agent/threads/heartbeat`（TD-197 的上报令牌，没有令牌就不发）；钩子不输出、不报错、永远 exit 0。第一次登记，以及服务端尚未确认的 `turn_start`，在钩子进程里同步发送；其余发送交给脱离的子进程。钩子从进入起只有一个单调时钟截止时间，5 秒；每一次锁等待只用截止前剩下的时间，进程在该截止时间退出。
  无头运行（`cursor-agent -p` 不触发 stop 钩子）一律这样启动：`node scripts/thread-heartbeat.js run cursor -- cursor-agent -p …`。
  收集员模式（R5:5.5-12 S1-4）默认关闭：配了收集员令牌（`PLATFORM_COLLECTOR_TOKEN` 或 `~/.config/bifrost/collector.token`）才打开，没配时，`scripts/collector-noop.test.js` 对所列输入（S1-0 全部夹具、工具/等待/Cursor/Codex 事件、run 包装器、进度、宿主心跳、令牌文件缺失/空/不可读）逐项比对基线：请求逐字节相同、家目录下的落盘文件相同（时间字段规范化）、stdout/stderr 为空；耗时不比（新接的四个事件会多起一次 node 进程，只查上限），假服务器一律回 202，不含平台的状态机。打开后心跳改用收集员令牌和主机号（`BIFROST_HOST_ID` 或 `~/.config/bifrost/host-id`，都没有退回 OS 短名并记 `host_id_source: hostname`），不带标题，带原始厂商会话号 `session`、世代 `epoch`、`client_bind`、`host_id_source`；另接 SessionStart、PreCompact、SessionEnd（带 timeout）、StopFailure 与 Cursor 的 `sessionStart`。事件表见 `scripts/collector-session.js` 文件头，世代与结束协议见 `scripts/collector-epochs.js` 文件头（结束只在意图落盘后发；拿不到锁时先存待发记录、下次补；认不出进程的结束不关任何世代；补发失败可重试，有上限）；`node scripts/collector-session.js diagnose` 打印模式、主机号来源与问题（不含令牌）。进度文档仍用上报令牌。
  宿主心跳（W-57）：`scripts/host-heartbeat.js` 每 60 秒上报主机名，以及 claude、cursor、codex 的钩子是否接上、上报令牌是否可读（cursor 一项只看本机实际生效的配置；仓库已不再提供 Cursor 的 hooks 模板与安装脚本，平台的 `agentthreads.Vendors` 仍要求三家都上报）。`node scripts/install-host-heartbeat.js` 只把 launchd 模板写到 `~/Library/LaunchAgents`，不加载；模板的环境变量写入 `BIFROST_WORKSPACE`。变量缺失时，脚本从自身位置向上找到含 `bifrost-platform/config/ops-context.yaml` 的工作区。用户级 hook 命令里的相对脚本路径按工作区根解析，这是厂商实际使用的 cwd。
- **`scripts/` 下的脚本自行向上查找工作区根**（标记 `bifrost-platform/config/ops-context.yaml`），
  因此无论从符号链接路径还是真实路径调用都能工作。两条路径都在回归测试覆盖内。

## 版本控制

- `claude/settings.local.json` 已加入 `.gitignore` —— 那是个人本地设置。
  `claude/settings.json` 是**共享**的治理配置，随库走。
- 其余全部入库。

## 校验

```bash
bash scripts/check-governance-consistency.sh   # 在工作区根；infra 根的旧入口 make check-agent-parity 仍可用
node scripts/agent-guard/test.js   # 硬边界回归 25 例
node scripts/thread-heartbeat.test.js   # 心跳：事件映射、节流、钩子失败不拦工具调用、无头包装
node --test scripts/collector-session.test.js scripts/collector-hooks.test.js scripts/collector-noop.test.js scripts/source-capability-witness.test.js scripts/collector-mutation.test.js   # 收集员模式：世代、钩子进程、与基线比对、S1-0 夹具见证、变异检查
python3 -m unittest discover -s scripts -p test_check_session_hooks.py   # 治理一致性检查里会话钩子与 SessionEnd timeout 的规则
```

规则见工作区根 `CLAUDE.md` §7（治理文件只有一份）。
