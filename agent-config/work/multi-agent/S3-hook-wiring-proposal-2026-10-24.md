# 4.6 S3 钩子接线提案（2026-10-24，待统筹复核；**本提交没有接线**）

> 依据：`CUT-lifecycle-2026-10-24.md` §4.2、§5 S3；复核 539 F3、F4。
> 本提交只加了脚本和测试：`scripts/agent-host/new-worktree.sh`（`new_worktree.py`、`worktree_owner.py`）、
> `agent-config/claude/hooks/worktree-lease.py`。**没有改任何 settings.json、没有改 `preflight.js`、没有改 Cursor 的 hooks.json。**
> 下面是建议的改法，原样可贴；接不接、什么时候接由统筹定。
>
> 钩子行为的文档依据（2026-10-24 抓取 code.claude.com/docs/en/hooks.md、env-vars.md 与 CHANGELOG）：
> SessionEnd 所有钩子**共享 1.5 秒预算**，某个钩子写了 `timeout` 时预算提到最大的那个（上限 60 秒）；SessionEnd 不能阻断退出；
> SessionStart 的纯文本 stdout 会进上下文；`CLAUDE_CODE_SESSION_ID` 在钩子子进程里有，等于输入里的 `session_id`，**/clear 之后会变**；
> PreToolUse 不给 `permissionDecision`、只给 `hookSpecificOutput.additionalContext`，就是不改权限的提示（CHANGELOG 2.1.9 起）。

## 1. Claude 侧：`agent-config/claude/settings.json`

在 `"hooks"` 里加两项（与已有的 `Stop` 等并列）：

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/worktree-lease.py\"",
        "timeout": 15
      }
    ]
  }
],
"SessionEnd": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/worktree-lease.py\"",
        "timeout": 15
      }
    ]
  }
]
```

- `timeout: 15` 是为了 SessionEnd：钩子在记录被清扫占着时最多等 10 秒拿锁（`worktree_owner.session_event` 的 `wait`），1.5 秒的默认预算不够。
  本机实测没有登记记录时一次 0.18 秒（`python3` 3.12 与 `/usr/bin/python3` 3.9 一样）。
- 钩子永远 exit 0、stdout 不输出任何东西（SessionStart 的 stdout 会进上下文），问题写 stderr。
- `$CLAUDE_PROJECT_DIR/.claude` 经符号链接指到 infra 的 `agent-config/claude`；钩子按自己的真实路径找到 `<infra>/scripts/agent-host/worktree_owner.py`。

**不建议**按切法原文在每次工具调用（PreToolUse）续租。理由：清扫只看 `ended_at`，没有 `ended_at` 时租约新旧不影响删除；
会话在 SessionEnd 之后要再用任何东西，必须先经过一次 SessionStart（resume / clear / fork / startup），那里已经续租并作废结束记录。
每次工具调用多跑一次约 0.2 秒的 Python 换不来额外的保护。如果统筹仍要，加在 `PreToolUse` 的无 matcher 那一组即可，命令同上、`timeout: 5`。

## 2. Cursor 侧：`agent-config/cursor/hooks.json`（再跑 `install-hooks.py` 生成用户级文件）

```json
"sessionEnd": [
  { "command": "node ./scripts/thread-heartbeat.js hook cursor" },
  { "command": "python3 ./.claude/hooks/worktree-lease.py" }
]
```

- 钩子已经认 Cursor 的 `sessionEnd` / `sessionStart` 事件名和 `conversation_id` 字段。
- **没核实**：Cursor 有没有 `sessionStart` 事件；Cursor 的 Agent 怎么拿到自己的 `conversation_id` 传给 `new-worktree.sh --session`（没有已知的环境变量）。
  核实前 Cursor 侧只接 `sessionEnd`；Cursor 建的 worktree 登记时 `--session` 写什么，要先定。
- 双轨：这只是接线，不改规则文本，不需要 bump parity-id。如果同时在 `CLAUDE.md` §5 / `.cursor/rules/workspace.mdc` 加一句「新 worktree 用 `new-worktree.sh`」，两侧的 `workspace-v25` 一起升到 `v26`。

## 3. `preflight.js` 的提示（不拦）

在 `evaluate()` 之外加一个只产生提示的规则；**verdict 为 deny 时仍只输出 deny**，不是 deny 时才看提示：

```js
// 4.6 S3: a worktree made without new-worktree.sh carries no lifecycle record (hint, never a deny).
function worktreeAddHint(cmd) {
  const c = String(cmd || '')
  if (/new-worktree\.sh/.test(c)) return null
  if (!/\bgit\b(?:\s+-[Cc]\s+\S+)*\s+worktree\s+add\b/.test(c)) return null
  return (
    'This worktree gets no lifecycle record, so prune-merged-branches.sh --local-only never removes it; ' +
    'it stays on disk until someone ends it by hand. ' +
    'bifrost-trade-infra/scripts/agent-host/new-worktree.sh <repo> <dir> <branch> --work W-n registers one; ' +
    'new-worktree.sh --end <dir> --work W-n --by <who> registers an existing one when its work is done.'
  )
}
```

`main()` 里，`if (!verdict.deny)` 分支改成：

```js
  if (!verdict.deny) {
    const hint = payload && /^(Bash)$/.test(String(payload.tool_name || '')) ? worktreeAddHint(payload.tool_input?.command) : null
    if (hint && !String(payload.hook_event_name || '').startsWith('before')) {
      // Claude Code: additionalContext without permissionDecision keeps the normal permission flow
      process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', additionalContext: hint } }))
    }
    process.exit(0)
  }
```

- 文案按文档建议写成事实，不写成指令（指令式的上下文可能触发提示注入防御）。
- **Cursor 侧不输出提示**：Cursor `beforeShellExecution` 的非阻断通道没核实；返回 `permission: 'allow'` 可能等于替用户批准命令，不能这样做。
  Cursor 侧先只在 `.cursor/rules` 里写一句（随 §2 的 parity 一起）。
- `test.js` 建议加的用例：`git -C bifrost-platform worktree add ../x -b y` 有提示；`scripts/agent-host/new-worktree.sh …` 没有；
  `git worktree list` 没有；一条本来被 deny 的命令（例如 `git add -A`）仍然只有 deny、没有提示。
- 工具自己（`push-main.sh`、`merge_accepted.py`）在脚本里跑 `git worktree add`，不经过 Bash 命令文本，不会被提示；
  它们留下的检出按 R11 与普通 worktree 同一门槛：没有记录就不删。要让它们能被自动清，下一步是让这两个工具登记并在退出时 `--end`（不在 S3 范围）。

## 4. 接线之后仍然没有覆盖的

| 情况 | 结果 | 方向 |
|---|---|---|
| 进程被杀、Desktop 关闭或归档时 SessionEnd 是否触发（文档没说） | 没有 `ended_at`，worktree 一直「在用」 | 安全方向；要清时手工 `new-worktree.sh --end` |
| `/clear`：SessionEnd(reason=clear) 被钩子跳过；之后 CLI 会话 id 变了 | 记录靠 `host_session`（`CLAUDE_CODE_HOST_SESSION_ID`，Desktop 线程 id）跟着线程走 | **没核实**这个变量在钩子进程里有（Bash 工具子进程里有，本会话实测）；没有时记录停在「在用」，安全方向 |
| fork 出来的会话用母会话的 worktree | fork 的 SessionStart 只续它自己的 id；母会话结束后，干净且全有副本的 worktree 过宽限期可被清 | 不丢对象（副本、reflog 归档、状态干净才删）；fork 要继续用就 `new-worktree.sh --renew <dir>` |
| 别的会话（没登记）在一个已结束的 worktree 里干活 | 钩子不知道；只有 lsof 在清扫那一刻看到的进程能挡住 | 要长期用别人的 worktree，先 `--renew` |
| 清扫与 `disk-guard.sh sweep` | 两者用同一把机器锁（`$AGENT_WORK/.lifecycle.lock`），不会同时跑 | disk-guard 还没调用 S2；以后接时要么先放锁再调，要么把锁交给子进程，不能在持锁时直接调（会拿不到锁、退出 3） |

## 5. 接线的验收

1. 接线提交里 `bash scripts/check-agent-config-parity.sh` 过（工作区根上跑；它今天在 base 上已经因为两个既有的写死路径失败，见 S2/S3 报告）。
2. 在一个新会话里：`new-worktree.sh <repo> ~/agent-work/<lane>/<repo> <branch> --work W-31`，`--show` 是 `in-use`；
   退出会话后 `--show` 是 `ended`（或 `ended-recently`）；`claude --resume` 回来，`--show` 回到 `in-use`，`voided_ends` 多一条。
3. `/clear` 一次，`--show` 仍是 `in-use`。
4. 以上每步之后 `prune-merged-branches.sh --local-only`（只报）给出的原因依次是 `not-ended`、可删（`would-remove`）或 `end-too-recent`、`not-ended`。
