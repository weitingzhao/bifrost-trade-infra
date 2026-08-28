# agent-config — 工作区级 Agent 治理层

Bifrost 工作区（`/stocks`）的 Agent 治理资产。**实体在这里，工作区根是符号链接。**

放在 `bifrost-trade-infra` 是因为：治理层本属 Ops/infra 域，且这样才能纳入版本控制
并接入现有 CI 与 release gate —— 工作区根 `/stocks` 本身不是 git repo。

## 布局与链接

| 工作区根（符号链接） | 实体（本目录） | 内容 |
|---------------------|---------------|------|
| `/stocks/CLAUDE.md` | `CLAUDE.md` | Claude 侧完整治理规则 |
| `/stocks/AGENT_FACTS.md` | `AGENT_FACTS.md` | **两侧共用**事实基线 |
| `/stocks/.mcp.json` | `.mcp.json` | 6 个 MCP server 注册 |
| `/stocks/.mcp.json.README.md` | `.mcp.json.README.md` | MCP 说明（focus 桥、令牌分级） |
| `/stocks/.claude` | `claude/` | settings.json · skills · agents · commands · hooks |
| `/stocks/.cursor` | `cursor/` | rules · skills · commands · hooks · _archive |
| `/stocks/scripts` | `scripts/` | **两侧共用**的 agent-guard 与 parity 校验 |

> 目录名故意用 `claude/` / `cursor/` 而非 `.claude/` / `.cursor/`：
> 避免 Cursor 把 `bifrost-trade-infra/agent-config/.cursor/` 误当成 infra repo 自己的规则目录而重复加载。

## 重建符号链接

克隆到新机器、或链接损坏时，在工作区根执行：

```bash
cd /path/to/stocks && AC=bifrost-trade-infra/agent-config && \
  ln -sfn "$AC/claude" .claude && ln -sfn "$AC/cursor" .cursor && \
  ln -sfn "$AC/scripts" scripts && \
  ln -sf "$AC/CLAUDE.md" CLAUDE.md && ln -sf "$AC/AGENT_FACTS.md" AGENT_FACTS.md && \
  ln -sf "$AC/.mcp.json" .mcp.json && ln -sf "$AC/.mcp.json.README.md" .mcp.json.README.md
```

## 路径约定

- **`claude/settings.json` 里的 hook 命令用本目录的绝对真实路径**，不经符号链接 —— 少一层解析、少一个故障点。
  换机器时这些绝对路径需要改（见上方 `AC` 变量）。
- **`cursor/hooks.json` 用相对路径** `./scripts/agent-guard/preflight.js`，Cursor 以工作区根为 cwd，经符号链接解析。
- **`scripts/` 下的脚本自行向上查找工作区根**（标记 `bifrost-platform/config/ops-context.yaml`），
  因此无论从符号链接路径还是真实路径调用都能工作。两条路径都在回归测试覆盖内。

## 版本控制

- `claude/settings.local.json` 已加入 `.gitignore` —— 那是个人本地设置。
  `claude/settings.json` 是**共享**的治理配置，随库走。
- 其余全部入库。

## 校验

```bash
make check-agent-parity        # 在 bifrost-trade-infra/ 下
node scripts/agent-guard/test.js   # 硬边界回归 25 例
```

规则见工作区根 `CLAUDE.md` §7（双轨维护）与 `cursor/rules/workspace.mdc` §4。
