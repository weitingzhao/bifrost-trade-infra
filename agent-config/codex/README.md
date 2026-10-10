# Codex 接入（W-35 / S0-15，2026-10-10）

Codex 的配置在用户级 `~/.codex/`，不进仓库。本文件记录它的内容和安装方法；检查脚本 `check-codex-guard.py` 在本目录。
规则仍只有一份：Codex 经根目录 `AGENTS.md` 读 `CLAUDE.md` 与 `AGENT_FACTS.md`，硬边界由同一个 `preflight.js` 拦截。

## 现状（2026-10-10 实测）

- 命令行随 ChatGPT.app 发布：`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`，版本 `codex-cli 0.162.0-alpha.17.2`（alpha，随 App 更新）。PATH 上的 `~/.local/bin/codex` 是指向它的链接。
- 钩子载荷和 Claude 的 `PreToolUse` 同形：shell 调用是 `tool_name: "Bash"`、`tool_input.command` 字符串；改文件是 `tool_name: "apply_patch"`，补丁全文在 `tool_input.command`；deny 输出也用 Claude 的 `hookSpecificOutput.permissionDecision`。所以只加了一层薄适配 `scripts/agent-guard/codex-pretooluse.js`（apply_patch 按文件拆成 Write，其余原样转发），`preflight.js` 没改。
- **Codex 只跑 trust 过的 hook，没 trust 的直接跳过，不报错。** trust 存在 `config.toml` 的 `[hooks.state."<key>"] trusted_hash`。哈希只覆盖 hooks.json 里这条 hook 的配置（命令串、超时等），不覆盖脚本内容：改 `preflight.js` 或适配层不用重新 trust，改 hooks.json 里的命令就要。

## `~/.codex` 的内容

`~/.codex/hooks.json`（全部工具，不设 matcher）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/opt/homebrew/bin/node /Users/vision-mac-trader/Desktop/stocks/scripts/agent-guard/codex-pretooluse.js",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

`~/.codex/config.toml` 里本项加的部分（其余是 App 自己写的模型、插件、桌面设置，不动）：

```toml
# 顶层
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[projects."/Users/vision-mac-trader/Desktop/stocks"]
trust_level = "trusted"

[projects."/Users/vision-mac-trader/agent-work"]
trust_level = "trusted"

[hooks.state."/Users/vision-mac-trader/.codex/hooks.json:pre_tool_use:0:0"]
trusted_hash = "sha256:e7c800d6102109a9845380ef036b76401952ee13c70cb784b8b98d38c8fa131d"
```

`~/.codex/AGENTS.md`：一段带条件的指针。在 `/stocks` 或 `~/agent-work` 下工作时先读 `/stocks/AGENTS.md`，别的项目不受影响。需要它的原因：Codex 从 git 根往下找 `AGENTS.md`，而 `/stocks` 不是 git 仓库。实测在子仓库（如 `bifrost-trade-frontend`）和 `~/agent-work` 的 worktree 里，Codex 都读不到根目录那份。

## 取值和理由

| 设置 | 取值 | 理由 / 影响 |
|------|------|------------|
| 沙箱 | `workspace-write` | 只能写当前目录和 `/tmp`；**默认不联网**，所以 Codex 不能 `git push`、不能调平台 API。`.git` 在沙箱里是只读的，`git commit` 要走审批 |
| 审批 | `on-request` | 越过沙箱的命令要问人（交互式）；`codex exec` 非交互，越界的命令直接失败 |
| 受信任目录 | `/stocks`（Owner 10-10 定）、`~/agent-work` | 受信任才加载项目级配置。Codex 在 `/stocks` 下启动时，沙箱可写的范围是整个共享 checkout |
| 闸门 | 全部工具都过 `codex-pretooluse.js` | 与 Claude、Cursor 同一份 `preflight.js` |

## Codex 自己的规矩

- 改代码在 `~/agent-work/` 下的 worktree 里做，不改 `/stocks` 下的共享 checkout（STEP0-PLAN S0-15）。
- 推送和发版仍走各仓库的规则（`CLAUDE.md` §5）；沙箱默认不联网，推送要么由人执行，要么在审批里放行那一条命令。
- Gitea 用户和平台令牌随 S0-4c 再给。在那之前 Codex 只当「实现」的候选，岗位等基准通过后再放开。

## 安装（新机器，或重装 App 之后）

1. PATH：`ln -s /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex ~/.local/bin/codex`，然后跑 `codex --version`。
2. 写 `~/.codex/hooks.json`（上面那份；`node` 用绝对路径，从 App 启动时 PATH 里可能没有 Homebrew）。
3. 在 `~/.codex/config.toml` 加上面的顶层两行和两个 `[projects]`。
4. trust hook，二选一：
   - 交互：终端里跑 `codex`，在「Hooks need review」里选 Trust。
   - 非交互：跑 `python3 bifrost-trade-infra/agent-config/codex/check-codex-guard.py`，它会打出当前的 key 和哈希，按上面的格式写进 `[hooks.state."<key>"] trusted_hash`。
   - hooks.json 的命令改了（例如 S0-1 改路径）就要重做这一步。
5. 写 `~/.codex/AGENTS.md`（指针）。
6. 验收：`python3 bifrost-trade-infra/agent-config/codex/check-codex-guard.py --probe`。`--probe` 会在临时 git 仓库里让 Codex 跑一次 `git add -A`，要被 preflight 拦下、暂存区为空。不带 `--probe` 只查配置，不调模型。`bash scripts/check-agent-config-parity.sh` 在本机装了 codex 时会跑不带 `--probe` 的那一版。

## 2026-10-10 的阳性对照

不用 `--dangerously-bypass-hook-trust`，沙箱和审批取 config 的默认值，在临时仓库里跑：

| 动作 | 结果 |
|------|------|
| shell `git add -A` | 被拦：「共享工作树 — 只暂存自己碰过的文件」，暂存区 0 个文件 |
| shell `git status --short` | 通过，exit 0 |
| apply_patch 新建 `k8s/overlays/prod/daemon-observe-safe.patch.yaml` | 被拦：「D10 交易执行冻结」，文件没有生成 |
| apply_patch 新建 `c.txt` | 通过 |

对照组：trust 之前（hook 状态 `untrusted`），同样的 `git add -A` 没有经过 preflight，只是撞上沙箱里 `.git` 只读才失败。这就是第 4 步不能省的原因。
