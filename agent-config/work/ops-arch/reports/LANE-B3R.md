# LANE-B3R

没有改共享 checkout。没有创建令牌文件，没有跑 apply 脚本，没有改 `~/.claude/settings.json`，没有推 main。preflight 没有拦住本道的命令。报告没有推。

`cursor/b3-infra` 已从 `f89e1bc` rebase 到 `origin/main` `3e90d9e7d08268977ef57ef46a69cedeae862b3f`（无冲突）。旧提交重放为 `1403f05beb70d40d1c76d3c5afa1ac583dc70be3`。推送是 `--force-with-lease`（远端当时仍是 `f89e1bc`）。

## B3R

- Claim：成立。返工前 `f89e1bc` 的 `.mcp.json` 与 `cursor/mcp.servers.json` 里 `bifrost-platform`、`bifrost-kubernetes` 的 `MCP_WRITES` 为 `off`；说明要求令牌在进程环境里；直接打审批接口和读 admin 令牌没有 preflight。见 `VERIFY-phase2.md` 的 B3 行与 ADR §5「已知的接受风险」。
- 改动：bifrost-trade-infra · `cursor/b3-infra` · `27ecfaedc7698fcd279321270233eac33f146ced`
  - `.mcp.json` 与 `cursor/mcp.servers.json`：上述两个 server 的 `MCP_WRITES=on`。`bifrost-approve` 仍只在 Claude 侧。
  - `.mcp.json.README.md`：令牌文件 `~/.config/bifrost/mcp-tokens.env`（权限 600）的三个键 `PLATFORM_VIEWER_TOKEN`、`PLATFORM_OPERATOR_TOKEN`、`PLATFORM_ADMIN_TOKEN`；从 `bifrost-platform/.env` 生成且不打印值；Mac mini 上的线程以后同样需要这份文件。读文件本身由 B1R 在 `mcp/platform` 实现，这里只记录。
  - `scripts/agent-guard/preflight.js`：Bash / Read / WebFetch / 浏览器及其他非 `mcp__bifrost-approve__*` 调用里，直接请求 `/api/v1/approvals/<id>/approve|reject`、打开 `#approvals` 去点、读取或引用 `PLATFORM_ADMIN_TOKEN` 与 `mcp-tokens.env`，一律拒绝，提示写明 ADR §5。`mcp__bifrost-approve__*` 放行。Edit/Write 只看目标路径，说明文档可以写这些名字。
  - `claude/settings.json` 的 PreToolUse matcher 加上 `Read|WebFetch`（项目钩子，不是 `~/.claude/settings.json`）。
  - `check_mcp_cutover.py`：`bifrost-platform` 与 `bifrost-kubernetes` 的 `MCP_WRITES` 必须是 `on`；别的 server 只要写了也必须是 `on`。`bifrost-approve` 仍只允许出现在 Claude 侧。原有 loopback / 插值检查保留。
  - 两侧说明与 parity：`workspace-v15` → `workspace-v16`（`CLAUDE.md` 与 `cursor/rules/workspace.mdc` 同一段）。`AGENT_FACTS.md` `agent-facts-v10` → `agent-facts-v11`。
- 防线：
  - `agent-config/scripts/agent-guard/test.js`：`curl POST /api/v1/approvals/req-1/approve` → DENY；`cat mcp-tokens.env` → DENY；`mcp__bifrost-approve__approve_request` → ALLOW。DENY 的输出含 `ADR §5`。同组还有 wget reject、printenv、Read 令牌文件、浏览器打开 `#approvals`。
  - `agent-config/scripts/check_mcp_cutover.py` 的 `--self-test`：`MCP_WRITES=off`、缺 `MCP_WRITES`、bridge server 上的 `off` 都会失败；Cursor 侧出现 `bifrost-approve` 仍失败。
- 门禁（退出码分开看）：
  - `node agent-config/scripts/agent-guard/test.js` → `85 通过 / 0 失败`，exit 0
  - `python3 agent-config/scripts/check_mcp_cutover.py --self-test` → `self-test ok`，exit 0
  - `python3 agent-config/scripts/check_mcp_cutover.py` → `mcp cutover check ok`，exit 0
  - parity（治理符号链接指到本提交，其余仓库仍用工作区共享 checkout）→ `Cursor 20 条 · Claude 20 条`，`spine D10 = BLOCKED`，`✓ Cursor ↔ Claude 治理配置一致`，exit 0。共享 checkout 落后 origin/main 的新鲜度警告是那些目录自己的 HEAD，不是这条分支。
- 验收：

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra rev-parse origin/cursor/b3-infra
# 27ecfaedc7698fcd279321270233eac33f146ced

WT=$(mktemp -d /tmp/b3r-verify.XXXXXX)
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra worktree add --detach "$WT" 27ecfaedc7698fcd279321270233eac33f146ced
node "$WT/agent-config/scripts/agent-guard/test.js" >/tmp/b3r-preflight.out; echo preflight:$?
tail -n 1 /tmp/b3r-preflight.out
python3 "$WT/agent-config/scripts/check_mcp_cutover.py" --self-test; echo self-test:$?
python3 "$WT/agent-config/scripts/check_mcp_cutover.py"; echo cutover:$?

ROOT=$(mktemp -d /tmp/b3r-parity.XXXXXX)
cd /Users/vision-mac-trader/Desktop/stocks
for name in * .[!.]*; do
  [ -e "$name" ] || continue
  case "$name" in CLAUDE.md|.cursor|.claude|scripts|AGENT_FACTS.md) continue ;; esac
  ln -s "/Users/vision-mac-trader/Desktop/stocks/$name" "$ROOT/$name"
done
ln -s "$WT/agent-config/CLAUDE.md" "$ROOT/CLAUDE.md"
ln -s "$WT/agent-config/AGENT_FACTS.md" "$ROOT/AGENT_FACTS.md"
ln -s "$WT/agent-config/cursor" "$ROOT/.cursor"
ln -s "$WT/agent-config/claude" "$ROOT/.claude"
ln -s "$WT/agent-config/scripts" "$ROOT/scripts"
bash "$ROOT/scripts/check-agent-config-parity.sh"; echo parity:$?

git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra worktree remove "$WT"
rm -rf "$ROOT"
```

预期：preflight 最后一行是 `✓ 85 通过 / 0 失败（共 85）` 且 exit 0；self-test 与默认 cutover 都打印 ok 且 exit 0；parity 打印 `Cursor 20 条 · Claude 20 条` 与 `✓ Cursor ↔ Claude 治理配置一致`，exit 0。

- 要 Owner 批：建 `~/.config/bifrost/mcp-tokens.env`，权限 600（三个键从 `bifrost-platform/.env` 抽出，命令见 `.mcp.json.README.md`，不要把值打到终端）。并应用 `permissions.ask`：`bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-release-permissions.sh`（`apply-auto-mode.sh` 不写 `permissions.ask`）。然后实测聊天里批准是否弹窗。本道没有做这三件事。
- 后续：`bifrost-platform` 的 `config/cursor-mcp-bridges.json` 在 `cursor/phase2-platform` 上仍是 `MCP_WRITES=off`（`bifrost-platform` 约第 10 行，`bifrost-kubernetes-bridge` 约第 21 行）。本道不改那个仓库。合并本分支之前那里也要改成 `on`，否则 `check_mcp_cutover.py --cursor` 指到该文件不会绿。Mac mini 上的线程以后同样需要同一份权限 600 的令牌文件。
