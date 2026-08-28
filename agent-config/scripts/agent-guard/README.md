# Agent Guard — 硬边界机械拦截

Cursor 与 Claude **共用同一份实现**。双轨维护（`CLAUDE.md` §7）下，规则文档各写一份，
但硬边界只有这一份代码 —— 这是两侧唯一不可能漂移的部分。

## 文件

| 文件 | 作用 |
|------|------|
| `preflight.js` | 拦截器本体。读 stdin JSON，输出 deny 决策或静默放行 |
| `test.js` | 回归测试（25 例）。`node scripts/agent-guard/test.js` |

## 接线

| 事件 | Claude Code | Cursor |
|------|-------------|--------|
| shell 执行前 | `PreToolUse` matcher `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit` | `beforeShellExecution` |
| MCP 调用前 | `PreToolUse` matcher `mcp__.*` | `beforeMCPExecution` |

配置分别在 `.claude/settings.json` 与 `.cursor/hooks.json`。
`scripts/check-agent-config-parity.sh` 会校验两侧都已接线。

## 拦截什么

### D10 交易执行冻结（受 spine 控制）

**只在 spine `decisions[id=D10].status != UNLOCKED` 时生效。**

| 规则 | 例 |
|------|-----|
| 写 `ib:operator:cmd` Stream | `redis-cli XADD ib:operator:cmd …` |
| Monitor 控制端点写操作 | `curl -X POST …/api/monitor/control/…` |
| 把 daemon 扩到 >0 副本 | `kubectl scale deploy/daemon --replicas=1` |
| 删除/移动/截断 D10 guard 文件 | `rm …/daemon-scale-zero.patch.yaml` |
| 删除 daemon overlay/patch | `kubectl delete … daemon … overlay` |
| Edit/Write 命中 guard 文件 | `Edit(k8s/overlays/prod/daemon-observe-safe.patch.yaml)` |
| MCP `scale_deployment` daemon >0 | `{name:"daemon", replicas:2}` |

### dev-services 卫生规则（始终生效）

| 规则 | 例 |
|------|-----|
| 长跑整包服务 | `python scripts/run_platform.py` · `./start.sh` · `run-local-ui.sh` |
| 终止 bdev 托管进程 | `pkill -f platform-api` |
| 裸 port-forward 9090 | `kubectl port-forward … 9090:9090`（除非走 `run_prometheus_pf.sh`） |

## 设计要点

### 1. 闸门与 spine 同源

`d10Status()` 在**每次调用时**读 `bifrost-platform/config/ops-context.yaml`。
Owner 把 D10 改成 `UNLOCKED`，拦截自动停止 —— 不需要改代码，不需要改两处配置。
**解锁只有一个开关。**

读不到 spine 时按 `BLOCKED` 处理（fail-closed）。

### 2. 风险分级

| 类别 | 策略 | 理由 |
|------|------|------|
| **D10** | 宁可误报不可漏报。只读命令也不豁免 | 实盘发单不可逆 |
| **dev-services** | 只读命令（`cat` / `grep` / …）与写文件命令（heredoc / 重定向）豁免 | 卫生规则，误伤成本高于漏报成本 |

### 3. 已知的误报类（已修，勿回退）

开发过程中真实撞到过两次，回归测试里都有对应用例：

- **共现误判**：命令里同时出现 `kill` 和某个服务名就拦 —— 会误伤 JS 的 `p.kill()` 加上
  路径中的 `bifrost-platform`。现要求「终止动词 + 同一命令段内 60 字符内的服务名」。
- **数据当命令**：`cat > f <<'EOF' … pkill -f platform-api … EOF` 是在写文件，
  不是在执行。现对 dev-services 规则豁免写文件类命令。

改规则后**必须**跑 `node scripts/agent-guard/test.js`，25 例全绿才算通过。

### 4. 非对抗性设计

本拦截器防的是**善意 Agent 的误操作**，不是有决心的绕过者。
任何间接层（写脚本再执行、base64、变量拼接）都能绕开正则。
真正的强边界在 K8s RBAC、Redis ACL、NetworkPolicy —— 见 spine D10 与 `AGENT_FACTS.md` §8。

## 排障

被拦截时输出会说明原因与权威链。若确认是误报：

1. 先跑 `node scripts/agent-guard/test.js` 确认现有用例仍全绿
2. 在 `test.js` 里**先加一条应为 ALLOW 的用例**（复现误报）
3. 再改 `preflight.js` 让它变绿，且原有 25 例不许变红
4. 跑 `bash scripts/check-agent-config-parity.sh`

**不要**为了绕过而删规则或改 spine 的 D10 —— 那是 Owner 的决定。
