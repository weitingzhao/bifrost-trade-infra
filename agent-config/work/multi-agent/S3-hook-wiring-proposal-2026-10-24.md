# 4.6 S3 钩子接线提案（2026-10-24，第 4 稿，按复核 551、552、553 改；**没有接线**）

> 依据：`CUT-lifecycle-2026-10-24.md` §4.2、§5 S3；复核 539 F3、F4；复核 551 D1、D2；复核 552 A2、A3；复核 553 A1、A4、D2、§C。
> 脚本和测试：`scripts/agent-host/new-worktree.sh`（`new_worktree.py`、`worktree_owner.py`、`worktree_sessions.py`）、
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

- `timeout: 15` 是为了 SessionEnd：1.5 秒的默认共享预算不够。`worktree_sessions.session_event` 的 `budget`（8 秒）
  **只约束等锁的总时间**；之前扫描记录目录、读记录没有单独的时限（复核 552 纠正了上一稿「整个钩子 8 秒」的说法）。
  本机实测没有登记记录时一次 0.18 秒（`python3` 3.12 与 `/usr/bin/python3` 3.9 一样）。
- SessionStart 的顺序（复核 551 D1、552 A2）：
  1. 原子地发布会话标记 `<status>/lifecycle-sessions/<会话 id>.json`（`active_since`，CLI 会话 id 和 host 会话 id 各一份）；
  2. 不加锁读记录、只挑本会话的（或本线程的）；在等锁预算内逐个续租；
  3. 标记发布失败时：在标记目录写 `<id>.resume-failed`，并在每份**没续租成功**的本会话记录的管理目录里写 `bifrost-owner.resume-failed`（都记时间）；
  4. 清扫保留一个已结束的 worktree，除非能证明它的会话在结束之后没有再启动：标记目录要存在且可读（**不存在算「不知道」，不算「已结束」**），
     会话和 host 会话的标记、`resume-failed`、管理目录里的 `resume-failed`，都不能比 `ended_at` 新，也不能读不了。
     `new-worktree.sh` 登记时会建标记目录；只有 SessionStart 写标记（登记不写：否则同一会话先结束的 worktree 会被当成又启动了）。
  5. 钩子在三种情况下在 stdout 打一个 JSON（`systemMessage` 给用户看，`hookSpecificOutput.additionalContext` 给会话看，两边同一段文字）：
     标记没能发布；有 worktree 什么保护都没写下（标记、续租、resume-failed 全失败）；钩子本身出错。
     文字**第一句**就是「这些 worktree 在 `new-worktree.sh --renew <dir>` 成功之前一个都不要用」，然后最多列 20 个路径并写明还有几个，
     最后才是错误原因（最多 400 字符），所以截断不会丢掉这句指令（复核 553 D2）。
     SessionStart 不能被任何钩子输出挡住；exit 2 也只把 stderr 给用户看（文档 hooks.md「Exit code 2 behavior per event」），所以用 exit 0 加 JSON。
     **这是提示，不是阻断，也不是持久保护**：全部写失败时磁盘上的旧 `ended_at` 仍然成立，要靠会话收到并照做。
- 会话之后再结束时 `ended_at` 前移到标记之后，才重新可删。
- 所有时间都按整数纳秒存、按真实先后比较（`ended_at_ns`、`owner_since_ns`、标记的 `active_since_ns`、`failed_at_ns`，复核 553 A1、A4）：
  同一秒里先启动、后正常结束，会按「已结束」处理，过了宽限期就能删。553 之前写的、只记到秒的记录，标记落在同一秒里时按「已恢复」处理，仍然保留。
- 钩子永远 exit 0；一切正常时 stdout 不输出任何东西（SessionStart 的 stdout 会进上下文），只有上面第 5 条的情况打 JSON；问题写 stderr。
- `$CLAUDE_PROJECT_DIR/.claude` 经符号链接指到 infra 的 `agent-config/claude`；钩子按自己的真实路径找到 `<infra>/scripts/agent-host/worktree_sessions.py`。
- 钩子把输入里的 `cwd` 传进去：别的会话在这个 worktree 里启动时，记录上标 `foreign_use`，清扫一直保留，直到 `--take`。

**不建议**按切法原文在每次工具调用（PreToolUse）续租。理由：清扫只看 `ended_at` 和会话标记，没有 `ended_at` 时租约新旧不影响删除；
会话在 SessionEnd 之后要再用任何东西，必须先经过一次 SessionStart（resume / clear / fork / startup），那里先写标记、再续租并作废结束记录；
即使续租失败，标记也让清扫把它当作在用。
每次工具调用多跑一次约 0.2 秒的 Python 换不来额外的保护。如果统筹仍要，加在 `PreToolUse` 的无 matcher 那一组即可，命令同上、`timeout: 5`。

## 2. Cursor 侧：`agent-config/cursor/hooks.json`（再跑 `install-hooks.py` 生成用户级文件）

```json
"sessionEnd": [
  { "command": "node ./scripts/thread-heartbeat.js hook cursor" },
  { "command": "python3 ./.claude/hooks/worktree-lease.py" }
]
```

- 钩子已经认 Cursor 的 `sessionEnd` / `sessionStart` 事件名和 `conversation_id` 字段。
- **上面这段先不要接**（复核 551 D1）：只有结束事件、没有可靠的「恢复时作废结束」，就会出现结束过的会话恢复后 worktree 仍被当作已结束。
  要等两件事都核实：Cursor 有 `sessionStart`（或等价的恢复事件），以及 Cursor 的 Agent 能拿到自己的会话 id 传给 `new-worktree.sh --session`。
  在那之前 Cursor 建的 worktree 不登记会话结束，也就不会被自动清；要清由人 `new-worktree.sh --end <dir> --work W-n --by <谁>`。
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
| fork 出来的会话、或别的会话要用一个 worktree | 不隐式共享（复核 551 D2）：记录只认一个会话 | 先 `new-worktree.sh --take <dir> --session <新会话> [--host-session <新会话的线程 id>]` 接管，记录进入新的所有权代际（`generation`、`owner_since`）。调用者不是新会话时，不继承调用者的 host，`--host-session` 不给就记为未知（复核 552 A3）。之后：旧会话的结束事件按会话 id 不再匹配；只按 host 匹配的结束事件，要记录的接管历史完整（`taken_from` 里每个更早的代际都还在，最多保留 32 次接管），该会话没有拥有过更早的代际，并且它的标记按纳秒晚于 `owner_since` 才算（同一线程里更早的会话迟到的结束不算，同一秒内也一样）。接管超过 32 次、或历史不完整的旧记录，只按自己的会话 id 或 `new-worktree.sh --end` 结束（复核 554 A1）。`--renew` 不转移使用权 |
| 别的会话在别人的 worktree 里启动（SessionStart 的 cwd 在里面） | 钩子在记录上标 `foreign_use`；清扫一直保留它 | `--take` 或人工 `--end --by` 清掉标记。会话都在工作区根启动，这条只覆盖少数情况；以绝对路径去改别人的 worktree 钩子看不到，只有清扫那一刻的 lsof 能挡 |
| 清扫与 `disk-guard.sh sweep` | 两者用同一把机器锁（`$AGENT_WORK/.lifecycle.lock`），不会同时跑 | disk-guard 还没调用 S2；以后接时要么先放锁再调，要么把锁交给子进程，不能在持锁时直接调（会拿不到锁、退出 3） |

## 5. 接线的验收

1. 接线提交里 `bash scripts/check-agent-config-parity.sh` 过（工作区根上跑；它今天在 base 上已经因为两个既有的写死路径失败，见 S2/S3 报告）。
2. 在一个新会话里：`new-worktree.sh <repo> ~/agent-work/<lane>/<repo> <branch> --work W-31`，`--show` 是 `in-use`；
   退出会话后 `--show` 是 `ended`（或 `ended-recently`）；`claude --resume` 回来，`--show` 回到 `in-use`，`voided_ends` 多一条，
   `<status>/lifecycle-sessions/<会话 id>.json` 已写；再退出，`ended_at` 在标记之后。
3. `/clear` 一次，`--show` 仍是 `in-use`。
4. 以上每步之后 `prune-merged-branches.sh --local-only`（只报）给出的原因依次是 `not-ended`、可删（`would-remove`）或 `end-too-recent`、`not-ended`。

## 6. 接线前要在真实 app 里量的（复核 553 §C，作为接线验收）

接线之前，下面每一项都要在真实的 Claude Desktop / Claude Code 里量到，结果写进接线提交的说明。Python 测试通过不能代替这些。

1. **事件与身份**：startup、resume、`/clear`、fork（以及重开）各自触发什么事件，`reason`/`source` 是什么，输入里的 `session_id` 是什么；
   钩子子进程里的 `CLAUDE_CODE_SESSION_ID` 和 `CLAUDE_CODE_HOST_SESSION_ID` 是否和它一致；开始事件是否总在第一次用到 worktree 之前完成。
   还要看：接管之后旧会话的事件、同一线程里有多个 CLI 会话、没有 host 的路径。
2. **顺序**：正常启动 → 正常结束 → 再恢复 → 再结束，以及同一秒内快速启停，记录和标记的先后都对；迟到或重复的 SessionEnd 不能结束新一代的使用权；
   关闭、归档、杀进程这些没有结束事件的情况，worktree 保持保留。
3. **失败路径**：标记目录只读、记录锁被占、管理目录也不可写，以及很多 worktree 同时失败：用户能不能看到 `systemMessage`；
   会话能不能在第一次工具调用之前看到完整的 `additionalContext`，并在 `--renew` 成功之前不用这些路径。
4. **时间**：实际登记规模下、和其他钩子同时跑时的耗时，共享超时，输出有没有被截断或丢掉。等锁预算 8 秒不是整个钩子的硬上限，扫描本身没有时限；
   尤其要量「保护全部写失败、还没打出 JSON 就被 harness 超时杀掉」这条路径。
5. **一致性**：同一组隔离夹具里，`new-worktree.sh --show` 和只报清扫的结果随上面这些事件一致变化；再核对 settings、提示规则和两侧 parity。
   Cursor 的可靠开始事件没确认之前，Cursor 的结束登记继续不接。
