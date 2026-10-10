# claude/auto-mode — Claude Code auto mode 分类器规则（Bifrost 工作区）

Claude Code 的 **auto mode** 由一个分类器决定每个工具调用放行/拦截。它读取 `settings.json`
里的 `autoMode.{environment, allow, soft_deny, hard_deny}`：`environment` 是给分类器的
环境事实（信任边界、敏感目标），三个列表是规则，`"$defaults"` 表示在该位置继承内置规则。

本目录是这套规则的**版本化 payload**；生效副本只有一份：用户级 `~/.claude/settings.json`。

## 为什么全部写进用户级

分类器只从用户级 `~/.claude/settings.json`、managed settings 与 `--settings` 读 `autoMode`；
项目级 `.claude/settings.json` 与 `.claude/settings.local.json` 里的 `autoMode` **一律忽略**
（防止仓库自带 allow 规则，见 [Configure auto mode](https://code.claude.com/docs/en/auto-mode-config.md)）。

原设计（2026-09-06）把 `project.autoMode.json` 写进项目级 `settings.local.json`，因此**从未生效**：
2026-09-26 应用后 `claude auto-mode config` 仍只有用户级 5 条 environment 与默认规则。2.1.268 上用真实文件、
符号链接、共享 `settings.json` 三种项目级探针复核，都读不到。所以两份 payload 现在合并写进用户级；
代价是这些规则对本机所有项目生效（本机基本只跑 Bifrost，D10、端口等条目在别处无害）。

| 文件 | 写入目标 | 内容 |
|------|---------|------|
| `user.autoMode.json` | `~/.claude/settings.json` 的 `autoMode`（排在前面） | 本机通用的几行；声明被下面的工作区段覆盖 |
| `project.autoMode.json` | 同上（追加在后面） | 工作区事实（公开仓、节点池、NodePort、Argo 同步策略、IB 接入模型、敏感位置）+ Bifrost 专属 allow / soft_deny / hard_deny（D10、PROD 库、闸门篡改、外泄、防火墙） |
| `apply-auto-mode.sh` | `~/.claude/settings.json` · `agent-config/claude/settings.local.json` | 备份 → 合并两份 payload 写进用户级（`$defaults` 保留一次、在最前）→ 删掉项目级失效的 `autoMode` 块与绕过分类器的旧 allow 条目 → 打印生效配置并**逐条核对自定义规则都在** → `claude auto-mode critique` |
| `release-permissions.json` + `apply-release-permissions.sh` | `~/.claude/settings.json` 的 `permissions.allow` / `permissions.ask` | 发布类放行规则（Owner 2026-10-05）：窄 Bash allow 在 auto mode 下先于分类器放行，ask 优先于 allow 兜住删 PVC/PV/ns、prune、DROP/TRUNCATE、force push、`window --clear`。同一份 `ask` 里还有聊天批准：`mcp__bifrost-approve__approve_request` 与 `mcp__bifrost-approve__reject_request`（每次都要 Owner 点允许）。`apply-auto-mode.sh` 不写 `permissions.ask`。散文 `autoMode.allow` 拦不住 `[Production Deploy]`，所以走 permissions。payload 里工作区根写成 `@WORKSPACE@`（`*.autoMode.json` 里 Claude 的项目目录名写成 `@WORKSPACE_SLUG@`），两个 apply 脚本换成本机的根：`BIFROST_WORKSPACE`，否则取 `bifrost-trade-infra` 的上一级。规则不是批准，见 CLAUDE.md §5。同样由 Owner 执行（Agent 写会被判 Self-Modification）。auto mode 下这两条 MCP ask 会不会真的弹窗，要 Owner 应用之后当场看，payload 在仓库里不等于已经弹过 |

## 应用（Owner 手动）

```bash
bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-auto-mode.sh
```

为什么必须 Owner 自己跑：

1. 分类器把「Agent 改写自己的 auto mode 规则」视为内置 hard_deny（Auto-Mode Bypass）——这是对的默认；
   Agent 的职责止于准备 payload 并报告。
2. `/auto-mode-setup` 向导拒绝写符号链接目录（`/stocks/.claude` → `agent-config/claude`）。

脚本最后一步若打印 `NOT LIVE` 并以非零退出，说明有自定义条目没进生效配置——不要当作已应用。

## 校验

```bash
claude auto-mode config     # 生效配置（用户级 + 内置默认）；自定义条目逐字出现在对应列表里才算生效
claude auto-mode defaults   # 内置默认
claude auto-mode critique   # AI 点评自定义规则（要求 claude CLI 已登录）
```

判据是 `claude auto-mode config` 的内容，不是 settings 文件里有没有这段。

## 何时更新

- spine D10 → `UNLOCKED` 时：删掉 `hard_deny` 里的 "D10 Trade-Execution Freeze" 条目（与 `CLAUDE.md` §3、`preflight.js` 同步解冻）。
- 节点、NodePort、Argo 同步策略、命名空间变化：先改 `AGENT_FACTS.md` §8c，再同步这里的 `environment`。
- 这是 Claude 专属的 harness 强制层，Cursor 侧无对应文件，不做 parity；但**内容必须与** `AGENT_FACTS.md` /
  `CLAUDE.md` / `trade-execution-freeze.mdc` 一致。

## 已知限制

- `environment` 文本里含 `ib:operator:cmd` 与写动词：用 Bash heredoc 写这个 JSON 会被 `preflight.js` 的
  D10 规则拦截（宁可误报的设计）。改文件请用编辑器或 Edit/Write 工具，不要改 guard。
- auto mode 规则在用户级，任何目录启动的会话都有；但 preflight hook 只在 `/stocks/.claude/settings.json`：
  会话在子 repo 目录启动时没有 hook、也没有共享记忆。会话一律在 `/stocks` 根启动。
