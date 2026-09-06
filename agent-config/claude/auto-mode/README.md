# claude/auto-mode — Claude Code auto mode 分类器规则（Bifrost 工作区）

Claude Code 的 **auto mode** 由一个分类器决定每个工具调用放行/拦截。它读取 `settings.json`
里的 `autoMode.{environment, allow, soft_deny, hard_deny}`：`environment` 是给分类器的
环境事实（信任边界、敏感目标），三个列表是规则，`"$defaults"` 表示在该位置继承内置规则。

本目录是这套规则的**版本化 payload**；生效副本在两个 gitignored / 本机文件里。

| 文件 | 写入目标 | 内容 |
|------|---------|------|
| `project.autoMode.json` | `agent-config/claude/settings.local.json`（= `/stocks/.claude/settings.local.json`） | 工作区事实（公开仓、节点池、NodePort、Argo 同步策略、IB 接入模型、敏感位置）+ Bifrost 专属 allow / soft_deny / hard_deny（D10、PROD 库、闸门篡改、外泄、防火墙） |
| `user.autoMode.json` | `~/.claude/settings.json` | 本机通用的几行；明确"项目级覆盖" |
| `apply-auto-mode.sh` | 上面两个文件 | 备份 → 合并 → 删除绕过分类器的旧 allow 条目 → 打印生效配置 → `claude auto-mode critique` |

## 应用（Owner 手动）

```bash
bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-auto-mode.sh
```

为什么必须 Owner 自己跑：

1. 分类器把「Agent 改写自己的 auto mode 规则」视为内置 hard_deny（Auto-Mode Bypass）——这是对的默认；
   Agent 的职责止于准备 payload 并报告。
2. `/auto-mode-setup` 向导拒绝写符号链接目录（`/stocks/.claude` → `agent-config/claude`），
   但 Claude Code **加载**经符号链接的 `settings.local.json` 没有问题（2026-09-06 探针验证）。

## 校验

```bash
claude auto-mode config     # 生效配置（user + project 合并；project 的 environment 行追加在 user 之后）
claude auto-mode defaults   # 内置默认（9 allow / 31 soft_deny / 2 hard_deny）
claude auto-mode critique   # AI 点评自定义规则
```

## 何时更新

- spine D10 → `UNLOCKED` 时：删掉 `hard_deny` 里的 "D10 Trade-Execution Freeze" 条目（与 `CLAUDE.md` §3、`preflight.js` 同步解冻）。
- 节点、NodePort、Argo 同步策略、命名空间变化：先改 `AGENT_FACTS.md` §8c，再同步这里的 `environment`。
- 这是 Claude 专属的 harness 强制层，Cursor 侧无对应文件，不做 parity；但**内容必须与** `AGENT_FACTS.md` /
  `CLAUDE.md` / `trade-execution-freeze.mdc` 一致。

## 已知限制

- `environment` 文本里含 `ib:operator:cmd` 与写动词：用 Bash heredoc 写这个 JSON 会被 `preflight.js` 的
  D10 规则拦截（宁可误报的设计）。改文件请用编辑器或 Edit/Write 工具，不要改 guard。
- 子 repo 没有自己的 `.claude/settings.json`：会话在子 repo 目录启动时既没有 preflight hook 也没有这套
  auto mode 环境。会话一律在 `/stocks` 根启动。
