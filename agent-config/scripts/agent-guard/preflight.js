#!/usr/bin/env node
/**
 * Bifrost Agent Guard — 硬边界机械拦截（Cursor 与 Claude 共用同一份实现）。
 *
 * 调用方：
 *   Claude Code : PreToolUse hook            → 输入 {hook_event_name:"PreToolUse", tool_name, tool_input}
 *   Cursor      : beforeShellExecution hook  → 输入 {hook_event_name:"beforeShellExecution", command, cwd}
 *   Cursor      : beforeMCPExecution hook    → 输入 {hook_event_name:"beforeMCPExecution", tool_name, tool_input}
 *
 * 权威源：
 *   D10 状态      → bifrost-platform/config/ops-context.yaml · decisions[id=D10].status
 *   禁止动作清单  → bifrost-trade-infra/agent-config/AGENT_MODES.md · FORBIDDEN_ACTIONS
 *   dev-services  → .cursor/rules/dev-services.mdc · CLAUDE.md §4
 *
 * 设计要点：
 *  1. D10 闸门与 spine 同源 —— Owner 把 spine 里的 D10 改成 UNLOCKED，本脚本自动放行，
 *     不需要改代码、不需要改两处配置。
 *  2. 风险分级 —— D10（高风险）宁可误报不可漏报；dev-services（卫生规则）对只读命令
 *     与写文件命令豁免，避免把"提到某命令的文本"误判成"要执行该命令"。
 *
 * 回归测试见 scripts/agent-guard/README.md。
 *
 * 审批旁路（ADR §5，始终生效，与 D10 是否解锁无关）：
 *  非 mcp__bifrost-approve__* 的工具调用里，直接打审批 approve/reject、
 *  用浏览器打开 #approvals 去点、以及读取或引用 admin 令牌文件，都拒绝。
 *  聊天批准本身仍走 bifrost-approve（permissions.ask 弹窗）。
 */
'use strict'

const fs = require('node:fs')
const path = require('node:path')

/**
 * 从本文件位置向上查找工作区根（标记：bifrost-platform/config/ops-context.yaml）。
 * 这样脚本无论放在工作区根的 scripts/ 还是 bifrost-trade-infra/agent-config/scripts/ 都能定位 spine。
 */
function findWorkspace(start) {
  let dir = start
  for (let i = 0; i < 8; i++) {
    if (fs.existsSync(path.join(dir, 'bifrost-platform', 'config', 'ops-context.yaml'))) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  return path.resolve(start, '..', '..')
}

const WORKSPACE = findWorkspace(__dirname)
const SPINE = path.join(WORKSPACE, 'bifrost-platform', 'config', 'ops-context.yaml')

// ─────────────────────────────── spine ───────────────────────────────

/** 读 spine 的 D10 状态。读不到时按 BLOCKED 处理（fail-closed）。 */
function d10Status() {
  try {
    const yaml = fs.readFileSync(SPINE, 'utf8')
    const at = yaml.indexOf('- id: D10')
    if (at === -1) return 'BLOCKED'
    const m = /^\s*status:\s*(\S+)/m.exec(yaml.slice(at, at + 400))
    return m ? m[1].toUpperCase() : 'BLOCKED'
  } catch {
    return 'BLOCKED'
  }
}

// ─────────────────────────────── 命令性质判定 ───────────────────────────────

const READ_PREFIX =
  /^\s*(cat|bat|grep|rg|head|tail|less|more|wc|ls|find|stat|file|sed\s+-n|awk|diff|git\s+(diff|show|log|status))\b/

/** 命令只是在"读"，不是在执行。 */
const isRead = cmd => READ_PREFIX.test(cmd)

/** 命令是在写文件（heredoc / 重定向），其正文属数据而非待执行命令。 */
const isFileWrite = cmd =>
  /<<-?\s*['"]?\w+['"]?/.test(cmd) || /^\s*(cat|printf|echo|tee)\b[^|;&]*>/.test(cmd)

const GUARD_FILES = /daemon-scale-zero\.patch\.yaml|daemon-observe-safe\.patch\.yaml/

const AUTHORITY =
  'spine D10 · bifrost-platform/config/ops-context.yaml · agent-config/AGENT_MODES.md FORBIDDEN_ACTIONS'

// ─────────────────────────────── D10 规则（高风险，不豁免） ───────────────────────────────
// Research domain writes are ALLOWED while D10 is BLOCKED:
//   research.ai_draft kind=order_intent · research.candidate_pool · harness propose-only
// ib:operator:cmd remains blocked (only Daemon may write that stream).

/** 仅在 spine D10 !== UNLOCKED 时生效。 */
function d10Rules(cmd) {
  // 1. 写 ib:operator:cmd（及 :dev / :stg 等派生流；唯一合法写入方是 Daemon 本身）
  //    只拦"真的在写"：redis-cli 带写命令（参数、管道、heredoc 都算），或代码里调用 redis
  //    客户端的写方法 / IbOperatorClient.request。改源码、grep、写 ACL 文件里出现流名与
  //    xadd 字样不算 —— 旧规则按整段文本匹配，连注释里的 "set" 都会误拦（TD-21）。
  const OP_STREAM = 'ib:operator:' + 'cmd'
  const W = 'xadd|xdel|xtrim|xgroup|lpush|rpush|publish|set|hset|del|unlink|rename'
  const cliWrite = /\bredis-cli\b/.test(cmd) && new RegExp('\\b(' + W + ')\\b', 'i').test(cmd)
  const clientWrite =
    new RegExp('\\.(' + W + '|delete)\\s*\\(', 'i').test(cmd) ||
    new RegExp('execute_command\\s*\\(\\s*[\'"](' + W + ')\\b', 'i').test(cmd)
  if (cmd.includes(OP_STREAM) && (cliWrite || clientWrite)) {
    return '写入 `' + OP_STREAM + '` — 唯一合法写入方是 Daemon 本身，Agent 永远不写这个 Stream'
  }
  if (/\bIbOperatorClient\b[\s\S]*\.request(_async)?\s*\(/.test(cmd)) {
    return '经 `IbOperatorClient` 向 `' + OP_STREAM + '` 发命令 — 唯一合法写入方是 Daemon 本身'
  }

  // 2. Monitor 控制端点写操作。monitor 在每个指向它的网关前缀和直连 :8765 下都答
  //    /control/* 与 /account-sync/control/*，按路径尾部匹配，不按前缀（TD-07）。
  //    curl 带 -d / --data / --json / -F 时默认就是 POST，也算写 —— 只认 curl 自己的参数
  //    且区分大小写，否则 `tr -d`、`curl -f` 这类只读命令会被误拦。
  //    TD-96：写法不止 curl。wget / httpie / xh 的写参数，以及 Python / Node / PowerShell
  //    代码里的 HTTP 写调用（requests.post、httpx.put、fetch(…, {method: 'POST'})、urllib 带 data=）
  //    都算写。仍只在同一条命令里同时出现 /control/ 路径时才拦，只读 GET 照常放行。
  const controlPath = /\/(account-sync\/)?control\/[\w-]+/.test(cmd)
  const httpWrite =
    /-X\s*(POST|PUT|DELETE|PATCH)|--request\s*(POST|PUT|DELETE|PATCH)/i.test(cmd) ||
    /\bcurl\b[^|;&]*\s(-d|--data[\w-]*|--json|-F|--form)\b/.test(cmd) ||
    /\bwget\b[^|;&]*\s--(post-data|post-file|body-data|body-file|method[= ]\s*(POST|PUT|DELETE|PATCH))\b/i.test(cmd) ||
    /\b(http|https|xh|xhs)\s+(POST|PUT|DELETE|PATCH)\b/i.test(cmd) ||
    /\.\s*(post|put|delete|patch)\s*\(/i.test(cmd) ||
    /\.\s*request\s*\(\s*['"`](POST|PUT|DELETE|PATCH)/i.test(cmd) ||
    /\bfetch\s*\([\s\S]*\bmethod\s*:\s*['"`](POST|PUT|DELETE|PATCH)/i.test(cmd) ||
    /\burllib\b[\s\S]*(\bmethod\s*=\s*['"](POST|PUT|DELETE|PATCH)|\bdata\s*=)/i.test(cmd) ||
    /\bInvoke-(WebRequest|RestMethod)\b[\s\S]*-Method\s+(Post|Put|Delete|Patch)/i.test(cmd)
  if (controlPath && httpWrite) {
    return 'Monitor `POST …/control/*`（任一网关前缀或 :8765，任一 HTTP 客户端）— 可能武装实盘交易'
  }

  // 3. 把 daemon 扩到 >0 副本。TD-96：不止 `kubectl scale`，`kubectl patch / set / apply / replace`
  //    把 spec.replicas 改成 >0 也是扩容（`--replicas=N` 或 JSON/YAML 里的 `"replicas": N`）。
  if (/kubectl[^;|&]*\b(scale|patch|set|apply|replace|edit)\b/.test(cmd) && /daemon/.test(cmd)) {
    const m = /--replicas[= ]+(\d+)/.exec(cmd) || /["']?\breplicas["']?\s*:\s*(\d+)/.exec(cmd)
    if (m && Number(m[1]) > 0) {
      return `为 daemon 扩容到 ${m[1]} 副本 — STG 必须保持 replicas: 0`
    }
  }

  // 4. 删除 / 移动 / 截断 / 原地改写 D10 guard 文件。TD-96：`sed -i`、`perl -i`、重定向写入、
  //    cp / ln / tee / install / rsync / dd 覆盖、`kubectl patch|edit|apply|replace` 指向 guard 文件、
  //    git rm / mv / checkout / restore 都会让 guard 失效。
  //    只读（cat / grep / sed -n / git log / git diff）照常放行。宁可误报：拿 guard 文件当 cp 源也拦。
  if (
    GUARD_FILES.test(cmd) &&
    (/\b(rm|mv|truncate|unlink|shred|kubectl\s+delete)\b/.test(cmd) ||
      /\bkubectl\b[^|;&]*\b(patch|edit|apply|replace)\b/.test(cmd) ||
      /\bsed\b[^|;&]*\s(-[a-zA-Z]*i[a-zA-Z]*|--in-place)(\s|=|$)/.test(cmd) ||
      /\bperl\b[^|;&]*\s-[a-zA-Z]*i/.test(cmd) ||
      /\b(cp|ln|tee|install|rsync|dd)\b/.test(cmd) ||
      />>?\s*['"]?[^\s'"|;&]*(daemon-scale-zero|daemon-observe-safe)\.patch\.yaml/.test(cmd) ||
      /\bgit\b[^|;&]*\b(rm|mv|checkout|restore)\b/.test(cmd) ||
      /\bopen\s*\([^)]*(daemon-scale-zero|daemon-observe-safe)[^)]*,\s*['"][wax+]/.test(cmd) ||
      /\.write_text\s*\(|\bwriteFileSync\s*\(|\bwriteFile\s*\(/.test(cmd))
  ) {
    return '删除、移动或改写 D10 infra guard（daemon-scale-zero / daemon-observe-safe）'
  }

  // 5. 删除 daemon overlay/patch —— 等同解除 guard
  if (/kubectl[^;|&]*\bdelete\b/.test(cmd) && /daemon/.test(cmd) && /overlay|patch/.test(cmd)) {
    return '删除 daemon overlay/patch —— 等同于解除 D10 guard'
  }

  return null
}

/** 文件写入类工具（Edit / Write / NotebookEdit）的 D10 检查。 */
function d10FileRule(filePath) {
  if (filePath && GUARD_FILES.test(filePath)) {
    return '修改 D10 infra guard 文件（daemon-scale-zero / daemon-observe-safe）'
  }
  return null
}

/** MCP 工具调用的 D10 检查。 */
function d10McpRule(toolName, input) {
  if (!/scale_deployment/.test(String(toolName || ''))) return null
  const target = String(input?.name ?? '')
  const replicas = Number(input?.replicas ?? 0)
  if (/daemon/i.test(target) && replicas > 0) {
    return `MCP \`scale_deployment\` 把 ${target} 扩到 ${replicas} 副本`
  }
  return null
}

// ─────────────────────────────── dev-services 规则（卫生，可豁免） ───────────────────────────────

// 服务进程名拆开拼接，避免本文件自身内容在被 grep / 引用时触发静态扫描。
const MANAGED = [
  'platform' + '-api',
  'platform' + '-console',
  'git' + '-bridge',
  'probe' + '-bridge',
  'trade' + '-ui',
  'run_platform',
  'prometheus' + '-pf',
].join('|')

/** 必须是「终止动词 + 同一命令段内紧随其后的服务名」，避免与 JS 的 `p.kill()`、
 *  路径中的 bifrost-platform、日志文件名等无关文本共现而误伤。 */
const TERMINATE_TARGET = new RegExp(
  '(^|[\\s;|&`(])(sudo\\s+)?(kill|pkill|killall)\\b[^;|&\\n]{0,60}?\\b(' + MANAGED + ')\\b',
)

function devServiceRules(cmd) {
  // 只读命令、以及写文件命令的正文，都不是"要执行的动作"。D10 规则不享受此豁免。
  if (isRead(cmd) || isFileWrite(cmd)) return null

  if (/\brun_platform\.py\b/.test(cmd)) {
    return '直接长跑整包 `run_platform.py` 会与 bdev 拆分 session 双开抢端口、留下 T 状态孤儿 —— 用 `bdev restart platform`'
  }
  if (/(^|[\s/&;])(\.\/)?start\.sh\b/.test(cmd) || /run-local-ui\.sh\b/.test(cmd)) {
    return '直接长跑 `start.sh` / `run-local-ui.sh` —— 用 `bdev restart <name>`'
  }
  if (TERMINATE_TARGET.test(cmd)) {
    return '直接终止 bdev 托管的服务进程 —— 用 `bdev restart <name>`（清 CRASHED 标记并走 supervise）'
  }
  if (/kubectl[^;|&]*port-forward[^;|&]*9090/.test(cmd) && !/run_prometheus_pf\.sh/.test(cmd)) {
    return '手动 `kubectl port-forward …9090` 会造成假健康 —— 用 `bdev restart prometheus-pf`（脚本会注入 KUBECONFIG）'
  }
  return null
}

// ─────────────────────── 共享工作树规则（卫生，可豁免） ───────────────────────
//
// 12 个 repo 是多会话共用的单一 checkout：工作区根不是 repo，且会话必须在根启动
// 才能加载治理层（CLAUDE.md §8），所以 per-session worktree 这条路走不通。后果是
// 一个会话跑整树暂存，会把别的会话**正在写**的文件一并纳入，下一次 commit 就把
// 它们卷走。2026-09-07、2026-09-22 各发生过一次；第二次一整组 greeks 修复被并进了
// 一个标题完全无关的提交，35 个提交之后才被发现。
//
// git 不认为这是破坏性操作（什么都没丢），所以 auto mode 的 [Git Destructive]
// 分类器不管它 —— 这条规则补的就是这个缺口。

/** 拆出 `git <sub>` 的 flag 与 pathspec。第一个非 flag token 之后不再按 flag 解析，
 *  这样提交信息里的 "-a"、路径里的 "." 都不会被误判。 */
function gitArgs(cmd, sub) {
  const m = new RegExp(
    '(?:^|[\\s;|&`(])git\\s+(?:(?:-C|-c)\\s+\\S+\\s+)*' + sub + '\\b([^;|&\\n]*)',
  ).exec(cmd)
  if (!m) return null
  const flags = []
  const paths = []
  let inFlags = true
  for (const tok of m[1].trim().split(/\s+/).filter(Boolean)) {
    if (tok === '--') {
      inFlags = false
      continue
    }
    if (inFlags && tok.startsWith('-')) {
      flags.push(tok)
      continue
    }
    inFlags = false
    paths.push(tok)
  }
  return { flags, paths }
}

const SWEEPS_ALL = /^(-A|--all|-u|--update)$/
const WHOLE_TREE = /^(\.|\.\/|\*)$/
/** 单横杠短 flag 里带 a（-a / -am / -av…）；--amend 这类长 flag 不算。 */
const shortFlagHasA = f => /^-[a-zA-Z]+$/.test(f) && f.includes('a')

function sharedWorktreeRules(cmd) {
  if (isRead(cmd) || isFileWrite(cmd)) return null

  const add = gitArgs(cmd, 'add')
  if (
    add &&
    (add.paths.some(p => WHOLE_TREE.test(p)) ||
      (add.flags.some(f => SWEEPS_ALL.test(f)) && add.paths.length === 0))
  ) {
    return '整棵树暂存（`git add` 的 -A / -u / . 形式）会把别的会话正在写的文件一并纳入 —— 逐个列出自己改过的文件'
  }

  const commit = gitArgs(cmd, 'commit')
  if (commit && commit.flags.some(f => f === '--all' || shortFlagHasA(f))) {
    return '`git commit -a` 绕过暂存区直接提交所有已跟踪改动，包括别的会话的 —— 先逐个 `git add <file>`，再不带 -a 提交'
  }

  return null
}

// ─────────────────────── 推 main 只经 push-main.sh（TD-341） ───────────────────────
//
// 推主线前要先过 CI 自己的 code-health 棘轮。2026-10-13、10-14 两次把超过 800 行的文件
// 推上 platform main；第三次（10-14 c7f4de8）扫描跑了，退出码却被 `| tail -1 &&` 吞掉。
// pre-push 钩子盖不住：platform 的 husky 用相对的 core.hooksPath，worktree 里没有钩子；
// Apple git 2.50 不执行配置里写的钩子。所以在命令这一层拦：直接 `git push` 到 main 一律
// 拒绝，推 main 只走 bifrost-trade-infra/scripts/release/push-main.sh（窗口检查 + 在这个
// 提交的干净 checkout 上跑 CI 同一份扫描 + 推送；脚本里的 push 本闸门看不到）。
// 看不出推到哪个分支的也拒绝（不带 refspec、只写 HEAD、目标里有变量或通配、--all /
// --mirror）：共享 checkout 停在 main 上，裸 `git push` 推的就是 main。
// 推到本地路径（/、.、~、file:）的是测试夹具，放行。

/**
 * 一行命令按 shell 的规则拆成简单命令：在没被引号括住的 ; & | ( ) 和换行处断开，每个简单命令是一组词
 * （复核 244 A3：`-C '/tmp/review checkout'` 这样带引号、带空格的参数要整个认出来）。认单引号、双引号
 * （里面认 \" \\ \$ \` 和续行）、引号外的反斜杠和词首的 # 注释。不做展开：词里留着 $ 和 `，用的地方见到
 * 就当作看不出。词首没被引号括住的 ~ 记在 tilde 上（shell 会把它换成 HOME）。引号没收尾时 ok 为 false。
 */
function shellCommands(cmd) {
  const s = String(cmd)
  const commands = []
  let words = []
  let word = null
  let ok = true
  const endWord = () => {
    if (word !== null) words.push(word)
    word = null
  }
  const endCommand = () => {
    endWord()
    if (words.length > 0) commands.push(words)
    words = []
  }
  const begin = tilde => {
    if (word === null) word = { text: '', tilde }
  }
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (c === "'") {
      begin(false)
      const end = s.indexOf("'", i + 1)
      if (end === -1) {
        ok = false
        break
      }
      word.text += s.slice(i + 1, end)
      i = end
    } else if (c === '"') {
      begin(false)
      let j = i + 1
      for (; j < s.length && s[j] !== '"'; j++) {
        if (s[j] === '\\' && j + 1 < s.length && '"\\$`\n'.includes(s[j + 1])) {
          j++
          if (s[j] === '\n') continue
        }
        word.text += s[j]
      }
      if (j >= s.length) {
        ok = false
        break
      }
      i = j
    } else if (c === '\\') {
      if (s[i + 1] === '\n') {
        i++
        continue
      }
      begin(false)
      if (i + 1 < s.length) word.text += s[++i]
    } else if (c === ' ' || c === '\t' || c === '\r') {
      endWord()
    } else if ('\n;&|()'.includes(c)) {
      endCommand()
    } else if (c === '#' && word === null) {
      const nl = s.indexOf('\n', i)
      i = nl === -1 ? s.length : nl - 1
    } else {
      begin(c === '~')
      word.text += c
    }
  }
  endCommand()
  return { commands, ok }
}

// 命令词前面可以有的东西：变量赋值、shell 关键字和不改变目录的包装命令。
const COMMAND_PREFIX = new Set(['if', 'then', 'else', 'elif', 'do', 'while', 'until', '!', '{', 'time', 'command', 'builtin', 'exec', 'env', 'nohup'])
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/
const IS_GIT = /(^|\/)git$/
// git 的全局选项里带一个值（写在下一个词）的；其余 -- 开头的和 -p / -P / -v / -h 不带值。
const GIT_GLOBAL_WITH_VALUE = new Set(['-C', '-c', '--git-dir', '--work-tree', '--namespace'])

/** 简单命令的命令词（跳过赋值和前缀）。 */
function commandWord(words) {
  const w = words.find(x => !ASSIGNMENT.test(x.text) && !COMMAND_PREFIX.has(x.text))
  return w ? w.text : ''
}

/**
 * 命令词是 git 的简单命令：{ globals（子命令之前的词）, sub（子命令；看不懂全局选项时为 null）, args }。
 * 命令词不是 git 返回 null。
 */
function gitCall(words) {
  let i = 0
  while (i < words.length && (ASSIGNMENT.test(words[i].text) || COMMAND_PREFIX.has(words[i].text))) i++
  if (i >= words.length || !IS_GIT.test(words[i].text)) return null
  const globals = []
  for (i++; i < words.length; i++) {
    const t = words[i].text
    if (GIT_GLOBAL_WITH_VALUE.has(t)) {
      if (i + 1 >= words.length) break
      globals.push(words[i], words[++i])
    } else if (t.startsWith('--') || /^-[pPvh]$/.test(t)) {
      globals.push(words[i])
    } else if (t.startsWith('-')) {
      break
    } else {
      return { globals, sub: t, args: words.slice(i + 1) }
    }
  }
  return { globals, sub: null, args: [] }
}

/** 每一次命令词是 git、子命令是 push 的参数 token（shell 分词）。 */
function tokenizedPushes(cmd) {
  return shellCommands(cmd)
    .commands.map(gitCall)
    .filter(c => c && c.sub === 'push')
    .map(c => c.args.map(w => w.text))
}

/** 每一次 `git … push …` 的参数 token（去掉包在外面的引号与括号）。 */
function gitPushes(cmd) {
  const re = /(?:^|[\s;|&`("'])git\s+(?:(?:-C|-c)\s+\S+\s+|--\S+\s+)*push\b([^;|&\n]*)/g
  const out = []
  for (const m of cmd.matchAll(re)) {
    out.push(
      m[1]
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map(t => t.replace(/^['"(]+|['"`)]+$/g, '')),
    )
  }
  return out
}

const PUSH_VALUE_FLAGS = /^(-o|--push-option|--repo|--receive-pack|--exec)$/
const PUSH_EVERY_BRANCH = /^(--all|--mirror|--branches)$/
const LOCAL_REMOTE = /^(\/|\.|~|file:)/
const MAIN_REF = /^(refs\/heads\/)?main$/

/** 这次 push 会写 main（'main'），或看不出写哪个分支（'unclear'）；都不是返回 null。 */
function pushTarget(tokens) {
  const pos = []
  let tags = false
  let flagsOver = false
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i]
    if (!flagsOver && t === '--') {
      flagsOver = true
      continue
    }
    // git 允许 flag 写在位置参数之后（git push origin x --force），refspec 不会以 - 开头。
    if (!flagsOver && t.startsWith('-')) {
      if (PUSH_EVERY_BRANCH.test(t)) return 'unclear'
      if (t === '--tags') tags = true
      if (PUSH_VALUE_FLAGS.test(t)) i++
      continue
    }
    pos.push(t)
  }
  if (pos.length > 0 && LOCAL_REMOTE.test(pos[0])) return null
  if (pos.length <= 1) return tags ? null : 'unclear'
  for (const spec of pos.slice(1)) {
    const s = spec.replace(/^\+/, '')
    const colon = s.indexOf(':')
    const dst = colon === -1 || colon === s.length - 1 ? s.replace(/:$/, '') : s.slice(colon + 1)
    if (MAIN_REF.test(dst)) return 'main'
    if (dst === 'HEAD' || dst === '@' || /[$`*]/.test(dst)) return 'unclear'
  }
  return null
}

function pushMainRule(cmd) {
  if (isRead(cmd) || isFileWrite(cmd)) return null
  // 文本匹配认得出包在引号里的 push（sh -c "git push …"），shell 分词认得出带引号、带空格的 -C；两边都查
  for (const tokens of [...gitPushes(cmd), ...tokenizedPushes(cmd)]) {
    const target = pushTarget(tokens)
    if (target === 'main') {
      return '直接 `git push` 到 main 不经过 CI 的 code-health 棘轮 —— 用 `bifrost-trade-infra/scripts/release/push-main.sh <checkout> [<commit>]`'
    }
    if (target === 'unclear') {
      return '这次 `git push` 看不出推到哪个分支（不带 refspec、只写 HEAD、目标里有变量或通配、--all / --mirror）；停在 main 上的 checkout 里推的就是 main —— 写明 `<src>:refs/heads/<branch>`，推 main 用 push-main.sh'
    }
  }
  return null
}

// ─────────────── Gitea 做主的仓库不从这里推 GitHub（CUT-gitea-primary 0g） ───────────────
//
// 名单 agent-config/gitea-primary.txt 里的仓库以 Gitea 为主：人和 Agent 推 Gitea，GitHub 只由
// 集群里的同步（k8s/cicd/github-sync，只快进 main 和标签）去推。两头都推会分叉（切法第 7 节）。
// 拦两种：推到名单里某个仓库的 GitHub 地址；推到名为 github 的远端（切换后本机检出的 github
// 远端只读，切换前不存在）。BIFROST_GITEA_PRIMARY_LIST 只给测试改名单的位置。

const GITHUB_HOSTS = new Set(['github.com', 'www.github.com', 'ssh.github.com'])

/**
 * 一个 GitHub 地址指的仓库名（小写）；别的地址返回 null。认 URL（任何 scheme、用户、端口）和
 * scp 写法（git@host:owner/repo）；主机不分大小写、去掉结尾的 / 和 .git。push-main.sh 用同一份规则，
 * 两边对 github-repo-cases.json 里的每个输入给出同一个答案（复核 243 A5、244 第 9 项）：只认可打印的
 * ASCII（别的字符两边的正则和大小写规则不一样，直接返回 null；规则层另外把它们当作看不出），
 * 不用 /i，只去掉 ASCII 空白。
 */
function githubRepoOf(address) {
  const u = String(address).replace(/^[ \t\n\r\f\v]+|[ \t\n\r\f\v]+$/g, '')
  if (NOT_PRINTABLE_ASCII.test(u)) return null
  let host
  let rest
  let m = u.match(/^[A-Za-z][A-Za-z0-9+.-]*:\/\/(?:[^@/]*@)?([^/:]+)(?::[0-9]*)?(\/.*)?$/)
  if (m) {
    host = m[1]
    rest = m[2] || ''
  } else {
    m = u.match(/^(?:[^@/:]+@)?([^/:]+):(.*)$/)
    if (!m) return null
    host = m[1]
    rest = m[2]
  }
  if (!GITHUB_HOSTS.has(host.toLowerCase())) return null
  const parts = rest.split('/').filter(Boolean)
  if (parts.length < 2) return null
  return parts[1].replace(/\.[gG][iI][tT]$/, '').toLowerCase()
}

const NOT_PRINTABLE_ASCII = /[^\x20-\x7e]/

/** 名单里的仓库名（小写）；文件不在或读不了就是空名单（切换前的样子）。 */
function giteaPrimaries() {
  const file = process.env.BIFROST_GITEA_PRIMARY_LIST || path.join(__dirname, '..', '..', 'gitea-primary.txt')
  try {
    return new Set(
      fs
        .readFileSync(file, 'utf8')
        .split('\n')
        .map(l => l.replace(/#.*/, '').trim().toLowerCase())
        .filter(Boolean),
    )
  } catch {
    return new Set()
  }
}

/** 这次 push 的目标：第一个位置参数和 --repo 的值（git 以位置参数为准；两个都查）。 */
function pushDestinations(args) {
  const out = []
  let positional = null
  let flagsOver = false
  for (let i = 0; i < args.length; i++) {
    const t = args[i]
    if (!flagsOver && t === '--') {
      flagsOver = true
      continue
    }
    if (!flagsOver && t.startsWith('-')) {
      if (t.startsWith('--repo=')) out.push(t.slice('--repo='.length))
      else if (t === '--repo') out.push(args[++i] ?? '')
      else if (PUSH_VALUE_FLAGS.test(t)) i++
      continue
    }
    if (positional === null) positional = t
  }
  if (positional !== null) out.unshift(positional)
  return out
}

/** git 的输出行和退出码；起不来或超时时退出码是 -1。 */
function gitLines(args, cwd) {
  try {
    const out = require('node:child_process').execFileSync('git', args, {
      cwd: cwd || process.cwd(),
      encoding: 'utf8',
      timeout: 3000,
      stdio: ['ignore', 'pipe', 'ignore'],
    })
    return { status: 0, lines: out.split('\n').map(l => l.trim()).filter(Boolean) }
  } catch (e) {
    return { status: typeof e.status === 'number' ? e.status : -1, lines: [] }
  }
}

/**
 * `git push <dest>` 会推到的全部地址，按这次命令的全局选项（-C、-c、--git-dir…）在 git 里查。
 * `git remote -v` 列出每个远端的推送地址，已经套上 insteadOf / pushInsteadOf，远端来自哪份配置都列
 * （`remote get-url` 只认检出自己配置里的远端，-c 和全局配置里的它说没有）。dest 是远端名就取它那几行；
 * 不是远端名，git push 把它当地址：这里给它套一个只在这次查询里存在的随机远端名，让 git 自己改写
 * （复核 244 A3）。只写在 .git/remotes、.git/branches 里的旧式远端 remote -v 不列，由 get-url 读。
 * 查不到返回 null。
 */
function effectivePushUrls(dest, globals, cwd) {
  const probe = 'preflight-' + require('node:crypto').randomBytes(8).toString('hex')
  const listing = gitLines([...globals, '-c', `remote.${probe}.url=${dest}`, 'remote', '-v'], cwd)
  if (listing.status !== 0) return null
  const pushUrls = name =>
    listing.lines
      .filter(l => l.startsWith(name + '\t') && l.endsWith(' (push)'))
      .map(l => l.slice(name.length + 1, -' (push)'.length))
  const named = pushUrls(dest)
  if (named.length > 0) return named
  const legacy = gitLines([...globals, 'remote', 'get-url', '--push', '--all', '--', dest], cwd)
  if (legacy.status === 0) return legacy.lines.length > 0 ? legacy.lines : null
  if (legacy.status !== 2) return null
  const anonymous = pushUrls(probe)
  return anonymous.length > 0 ? anonymous : null
}

/** 全局选项原样交给 git，词首的 ~ 按 shell 换成 HOME；里面有变量或命令替换返回 null。 */
function resolvedGlobals(words) {
  const out = []
  for (const w of words) {
    if (/[$`]/.test(w.text)) return null
    if (w.tilde && (w.text === '~' || w.text.startsWith('~/'))) out.push(path.join(require('node:os').homedir(), w.text.slice(1)))
    else if (w.tilde) return null
    else out.push(w.text)
  }
  return out
}

/** 命令词不是 git 的简单命令里包着 git push：git 是参数（xargs git push、sudo git push），或某个词本身是一段含 git push 的命令（bash -c '…'、eval "…"）。 */
function wrapsGitPush(words) {
  const k = words.findIndex(w => IS_GIT.test(w.text))
  if (k !== -1 && words.slice(k + 1).some(w => w.text === 'push')) return true
  return words.some(w => /\s/.test(w.text) && /\bgit\b[\s\S]*\bpush\b/.test(w.text))
}

// 换掉 git 读哪份配置、在哪个仓库、用什么连接的环境变量（复核 243 A3 的 GIT_CONFIG_* 同类）
const GIT_ENV_OVERRIDE =
  /\bGIT_CONFIG_(COUNT|KEY|VALUE|PARAMETERS)\b|(?:^|[\s;|&(])(?:GIT_(?:CONFIG\w*|DIR|WORK_TREE|NAMESPACE|SSH|SSH_COMMAND)|HOME|XDG_CONFIG_HOME)=|--config-env\b/

function githubPushRule(cmd, cwd) {
  if (isRead(cmd) || isFileWrite(cmd)) return null
  if (!/\bgit\b/.test(cmd) || !/\bpush\b/.test(cmd)) return null
  const primaries = giteaPrimaries()
  const listed = primaries.size > 0
  const toGitHub = repo =>
    `${repo} 以 Gitea 为主（agent-config/gitea-primary.txt）：推 Gitea，GitHub 由集群同步（k8s/cicd/github-sync），不从这里推`
  const unclear = why =>
    `看不出这次 git push 推到哪里（${why}）。有仓库以 Gitea 为主时要能查到：写成 \`git -C <检出目录> push <远端> <refspec>\``
  const githubRemote = '`github` 远端只读：以 Gitea 为主的仓库推 Gitea（origin），GitHub 由集群同步（k8s/cicd/github-sync）'
  // 名单空着也拦 github 远端：文本匹配认得出包在引号里的（sh -c "git push github …"），下面的分词认不出
  for (const tokens of gitPushes(cmd)) {
    if (pushDestinations(tokens).includes('github')) return githubRemote
  }
  if (listed && GIT_ENV_OVERRIDE.test(cmd)) {
    return '有仓库以 Gitea 为主时，不在命令行上换 git 的配置、仓库或连接（GIT_CONFIG_*、GIT_DIR、HOME、--config-env…）再推送：看不出推到哪里'
  }
  const { commands, ok } = shellCommands(cmd)
  if (!ok && listed) return unclear('引号没收尾')
  let movedDir = false
  for (const words of commands) {
    if (/^(cd|pushd|popd)$/.test(commandWord(words))) {
      movedDir = true
      continue
    }
    const call = gitCall(words)
    if (call === null) {
      if (listed && wrapsGitPush(words)) return unclear('git push 包在别的命令里')
      continue
    }
    if (call.sub !== 'push') {
      if (!listed) continue
      if (call.sub === null && words.some(w => w.text === 'push')) return unclear('看不懂 git 的全局选项')
      if (call.globals.some(w => /^alias\./i.test(w.text))) return unclear('命令行上定义了 git 别名')
      continue
    }
    const dests = pushDestinations(call.args.map(w => w.text))
    if (dests.includes('github')) return githubRemote
    if (!listed) continue
    // 不写远端时 git 按 branch.<分支>.pushRemote、remote.pushDefault、branch.<分支>.remote、origin 挑（复核 244 A3）
    if (dests.length === 0) return unclear('没写远端，默认推送远端由配置决定')
    if (movedDir) return unclear('前面 cd 过，这里查的不是它推送的仓库')
    const globals = resolvedGlobals(call.globals)
    if (globals === null) return unclear('全局选项里有变量或命令替换')
    for (const dest of dests) {
      if (/[$`]/.test(dest)) return unclear(`远端 ${dest} 里有变量或命令替换`)
      if (NOT_PRINTABLE_ASCII.test(dest)) return unclear(`远端 ${dest} 里有可打印 ASCII 以外的字符`)
      const literal = githubRepoOf(dest)
      if (literal && primaries.has(literal)) return toGitHub(literal)
      const urls = effectivePushUrls(dest, globals, cwd)
      if (urls === null) return unclear(`查不到 ${dest} 的推送地址`)
      for (const url of urls) {
        if (NOT_PRINTABLE_ASCII.test(url)) return unclear(`${dest} 推到 ${url}，里面有可打印 ASCII 以外的字符`)
        const repo = githubRepoOf(url)
        if (repo && primaries.has(repo)) return toGitHub(repo)
      }
    }
  }
  return null
}

// ─────────────────────── 审批旁路（ADR §5，始终生效） ───────────────────────
//
// Owner 2026-10-07：聊天批准保留。admin 令牌在本机进程可读是已知的接受风险，
// 这条文本拦截挡的是「不走弹窗、直接批准」和「把令牌读出来自己用」。
// 防的是善意误操作，不是有决心的绕过（同本文件其他规则）。
//
// Edit / Write 只看目标路径，不看正文：说明文档必须能写这些名字。
// Bash、Read、浏览器和其他工具调用看整段输入。

const ADMIN_TOKEN_NAME = 'PLATFORM_' + 'ADMIN_TOKEN'
const TOKEN_FILE_NAME = 'mcp-tokens' + '.env'
const APPROVALS_HASH = '#' + 'approvals'
const QUESTIONS_HASH = '#' + 'questions'
const APPROVAL_API = new RegExp(
  '/api/v1/' + 'approvals/[^/\\s"\'`?#]+/(approve|reject|resolve)\\b',
)
const QUESTION_ANSWER_API = new RegExp(
  '/api/v1/' + 'questions/[^/\\s"\'`?#]+/answer\\b',
)
const OPENS_PAGE = /\b(curl|wget|fetch|open|xdg-open|chrome|chromium|osascript|browse|click|locator|getByRole|getByText|playwright|puppeteer|selenium)\b/i

function approvalText(toolName, input, cmd) {
  const name = String(toolName || '')
  if (/^(Edit|Write|MultiEdit|NotebookEdit)$/.test(name)) {
    return String((input && (input.file_path || input.notebook_path)) || '')
  }
  const parts = []
  if (cmd) parts.push(String(cmd))
  if (input && typeof input === 'object') {
    try {
      parts.push(JSON.stringify(input))
    } catch {
      parts.push(String(input))
    }
  } else if (input) {
    parts.push(String(input))
  }
  return parts.join('\n')
}

function approvalGuard(toolName, input, cmd) {
  const name = String(toolName || '')
  const text = approvalText(name, input, cmd)
  if (text) {
    if (QUESTION_ANSWER_API.test(text)) {
      return (
        '直接请求 `/api/v1/questions/<id>/answer`。回答只在控制台由 Owner 完成。' +
        '线程用 `wait_for_answer` 等答案，不要自己答'
      )
    }
    const browserName = /browser|WebFetch|playwright|puppeteer|selenium/i.test(name)
    if (text.includes(QUESTIONS_HASH) && (browserName || OPENS_PAGE.test(text))) {
      return '用浏览器或 HTTP 客户端打开 `#questions`。线程用 `wait_for_answer` 等答案，不要去点问题页'
    }
  }
  // 问题检查在批准豁免之前：approve 工具的输入里如果夹了回答路由，一样拒绝。
  if (/^mcp__bifrost-approve__/.test(name)) return null
  if (!text) return null

  if (text.includes(ADMIN_TOKEN_NAME) || text.includes(TOKEN_FILE_NAME)) {
    return (
      '读取或引用 `' + ADMIN_TOKEN_NAME + '` 或 `' + TOKEN_FILE_NAME +
      '`。ADR §5：admin 令牌留在本机只为聊天批准弹窗，不给 Agent 拿去直接用'
    )
  }
  if (APPROVAL_API.test(text)) {
    return (
      '直接请求 `/api/v1/approvals/<id>/approve`、`/reject` 或 `/resolve`（curl、wget、fetch 等都算）。' +
      'ADR §5：批准只走会弹窗的 bifrost-approve'
    )
  }

  const browserName = /browser|WebFetch|playwright|puppeteer|selenium/i.test(name)
  const opensPage = text.includes(APPROVALS_HASH) && (browserName || OPENS_PAGE.test(text))
  if (opensPage) {
    return '用浏览器或 HTTP 客户端打开 `#approvals`。ADR §5：Agent 不得绕过聊天弹窗去点审批页'
  }
  if (browserName && /approvals/.test(text) && /\b(approve|reject|click)\b/i.test(text)) {
    return '在浏览器里对审批页点批准或驳回。ADR §5：批准只走 `mcp__bifrost-approve__*` 的弹窗'
  }
  return null
}


// ─────────────────────── Owner 凭证（LANE-W33D） ───────────────────────
//
// Cursor 与 Claude 共用这一份闸门（scripts/agent-guard/preflight.js）。
// Cursor 侧不用另改。Owner 应用 preflight-w33d.patch 之后才生效。
// Bash、Read、Grep、Glob 的路径或文本里出现 Owner 目录或 owner.env 就拒绝。
// KUBECONFIG= 或 --kubeconfig 指向 ~/.kube/bifrost-k3s.yaml 以外也拒绝。
// ~、$HOME、${HOME} 和绝对路径都认。未设置 KUBECONFIG 的命令放行。

const OWNER_MARK = '.bifrost-' + 'owner'
const OWNER_ENV_MARK = 'owner' + '.env'
const ALLOWED_KUBE_TAIL = '.kube/bifrost-k3s.yaml'

function ownerToolText(toolName, input, cmd) {
  const parts = []
  if (cmd) parts.push(String(cmd))
  if (input && typeof input === 'object') {
    for (const field of ['command', 'file_path', 'path', 'pattern', 'glob_pattern', 'target_directory']) {
      if (input[field]) parts.push(String(input[field]))
    }
    try { parts.push(JSON.stringify(input)) } catch { parts.push(String(input)) }
  }
  return parts.join('\n')
}

function kubeconfigValueAllowed(raw) {
  let value = String(raw || '').trim()
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    value = value.slice(1, -1).trim()
  }
  if (value === '~/' + ALLOWED_KUBE_TAIL) return true
  if (value === '$HOME/' + ALLOWED_KUBE_TAIL) return true
  if (value === '${HOME}/' + ALLOWED_KUBE_TAIL) return true
  // One home directory, one file: /tmp/x/.kube/bifrost-k3s.yaml is a copy, and
  // a:b is a list kubectl merges (the first file's context wins).
  if (/^\/(?:Users|home)\/[^/:\s]+\/\.kube\/bifrost-k3s\.yaml$/.test(value)) return true
  return false
}

function foreignKubeconfig(cmd) {
  const text = String(cmd || '')
  // An unquoted value ends at a shell separator: `KUBECONFIG=~/.kube/bifrost-k3s.yaml;`
  // is the allowed file followed by `;`.
  const re = /(?:^|[\s;&|`(])(?:export\s+)?KUBECONFIG=("[^"]*"|'[^']*'|[^\s;&|`()<>]+)|--kubeconfig(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|`()<>]+)/g
  let match
  while ((match = re.exec(text))) {
    const value = match[1] || match[2]
    if (!kubeconfigValueAllowed(value)) return value
  }
  return null
}

// Scripts that read the Owner's credentials (owner.env, the admin kubeconfig,
// the node key). The gate only sees command text, so running one would read
// what a direct cat is refused. Tests (*_test.sh) stay allowed.
const OWNER_SCRIPT_RE = new RegExp([
  'scripts/owner/(?:make-agent-kubeconfig|move-owner-secrets|owner-run|owner-env)\\.sh',
  'materialize_k8s_trade_secrets\\.py',
  'trade-operator-tokens\\.sh',
  'bifrost-password-rotate\\.sh',
  'sync_redis_ib_trade_config\\.sh',
  'redis-ib-env-users\\.sh',
  'render-redis-ib-acl\\.sh',
  'scripts/unifi_(?![A-Za-z0-9_]*_test\\.)[A-Za-z0-9_]+\\.(?:sh|py)',
].join('|'))

// TD-278: plugin redis-ib scripts that load the Owner env when they run.
// Only running them is refused (bash/sh/source with any flags, ./ after a
// space or separator, or the make target);
// reading, editing or committing them by name is not.
const OWNER_RUN_RE = new RegExp(
  '(?:^|[;&|(`]\\s*|(?:^|[\\s;&|(`])(?:bash|sh|zsh|source|exec)\\s+(?:-\\S+\\s+)*|(?:^|\\s)\\.\\s+|(?:^|\\s)(?=\\./))(?:\\./)?(?:[\\w.~$/-]*/)?' +
    '(?:verify-ib-gateway(?:-live)?|verify-redis-ib|verify-trade-quotes-e2e|sync_redis_ib_secrets|install-redis-ib)\\.sh\\b' +
    '|\\bmake\\b[^;&|\\n]*\\s(?:verify-ib-gateway(?:-live)?|verify-redis-ib|verify-trade-quotes-e2e|sync-redis-ib-secrets|install-redis-ib)(?=$|[\\s;&|)])',
  'm'
)

function ownerScript(cmd) {
  const text = String(cmd || '')
  return OWNER_SCRIPT_RE.test(text) || OWNER_RUN_RE.test(text)
}

function ownerCredentialGuard(toolName, input, cmd) {
  const name = String(toolName || '')
  const watched = /^(Bash|Read|Grep|Glob)$/.test(name)
  const command = cmd || (input && input.command) || ''
  if (!watched && !command) return null
  const effective = watched ? name : 'Bash'
  const text = ownerToolText(effective, input, command)
  const sentence = '这是 Owner 的凭证，写操作走平台动作或 owner_run_command'
  if (text.includes(OWNER_MARK) || text.includes(OWNER_ENV_MARK)) return sentence
  if (effective === 'Bash') {
    if (foreignKubeconfig(command || text)) return sentence
    if (ownerScript(command)) return sentence + '（这是只给 Owner 运行的脚本）'
  }
  return null
}

// ─────────────────────── 本机 NAS 共享（TD-326，文本绊线） ───────────────────────

const NAS_REASON = '这是 NAS 上的共享，里面有未加密的备份；要看备份内容走平台动作或请 Owner 处理'

/** 只解析挂载表，不访问挂载点；SMB 与 NFS 都要求来源主机精确匹配。 */
function nasMountPoints(mountText) {
  const points = []
  for (const line of String(mountText || '').split('\n')) {
    const m = /^(\S+) on (.+) \((smbfs|nfs)(?:,|\))/.exec(line)
    if (!m) continue
    const source = m[1]
    const isNas = m[3] === 'smbfs'
      ? /^\/\/(?:[^/@]+@)?192\.168\.10\.20\//.test(source)
      : /^192\.168\.10\.20:\//.test(source)
    if (isNas) points.push(m[2])
  }
  return points
}

/** 挂载表文本可由测试直接给定；表不可用时固定底线仍然生效。 */
function nasPathRule(text, mountText) {
  text = String(text || '')
  // 固定底线：k3s 的两个共享，以及 Time Machine 自己的网络挂载点（来源写的是 Bonjour 名，挂载表那条规则认不出）。
  if (text.includes('/Volumes/k3s-') || text.includes('/Volumes/.timemachine/')) return NAS_REASON
  for (const point of nasMountPoints(mountText)) {
    let at = text.indexOf(point)
    while (at !== -1) {
      const next = text[at + point.length]
      if (next === undefined || /[\s/"'`;|&()<>{}\[\],]/.test(next)) return NAS_REASON
      at = text.indexOf(point, at + 1)
    }
  }
  return null
}

function readMountTable() {
  // 只在真要读表时才加载：顶层加载会让每一次调用多花几毫秒。
  const { execFileSync } = require('node:child_process')
  return execFileSync('/sbin/mount', [], {
    encoding: 'utf8', timeout: 1000, maxBuffer: 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'],
  })
}

function nasGuard(toolName, input, cmd, readMounts = readMountTable) {
  // 文件工具只看路径，不把待写入的文档正文当作读取目标。
  const parts = [String(cmd || '')]
  for (const field of ['file_path', 'path', 'notebook_path', 'target_directory', 'glob_pattern']) {
    if (input && input[field]) parts.push(String(input[field]))
  }
  const text = parts.join('\n')
  if (!text.includes('/Volumes/')) return null
  const fixed = nasPathRule(text, '')
  if (fixed) return fixed
  let mountText = ''
  try { mountText = readMounts() } catch { /* 读取失败只保留固定底线。 */ }
  return nasPathRule(text, mountText)
}

// ─────────────────────────────── 判定 ───────────────────────────────

function evaluate(payload, readMounts = readMountTable) {
  const event = String(payload.hook_event_name || '')
  const isCursorShell = event === 'beforeShellExecution'
  const toolName = payload.tool_name || (isCursorShell ? 'Bash' : '')
  const input = payload.tool_input || (isCursorShell ? { command: payload.command } : {})

  const locked = d10Status() !== 'UNLOCKED'
  const cmd = String(input.command ?? payload.command ?? '')

  const nas = nasGuard(toolName, input, cmd, readMounts)
  if (nas) return { deny: true, kind: 'nas', reason: nas }

  const owner = ownerCredentialGuard(toolName, input, cmd)
  if (owner) return { deny: true, kind: 'owner', reason: owner }

  const approval = approvalGuard(toolName, input, cmd)
  if (approval) return { deny: true, kind: 'approval', reason: approval }

  if (cmd) {
    const dev = devServiceRules(cmd)
    if (dev) return { deny: true, kind: 'dev-services', reason: dev }
    const sw = sharedWorktreeRules(cmd)
    if (sw) return { deny: true, kind: 'shared-worktree', reason: sw }
    const pm = pushMainRule(cmd)
    if (pm) return { deny: true, kind: 'push-main', reason: pm }
    const gp = githubPushRule(cmd, payload.cwd)
    if (gp) return { deny: true, kind: 'gitea-primary', reason: gp }
    if (locked) {
      const d10 = d10Rules(cmd)
      if (d10) return { deny: true, kind: 'D10', reason: d10 }
    }
  }

  if (locked && /^(Edit|Write|MultiEdit|NotebookEdit)$/.test(String(toolName))) {
    const f = d10FileRule(String(input.file_path ?? input.notebook_path ?? ''))
    if (f) return { deny: true, kind: 'D10', reason: f }
  }

  if (locked) {
    const m = d10McpRule(toolName, input)
    if (m) return { deny: true, kind: 'D10', reason: m }
  }

  return { deny: false }
}

function denyMessage(kind, reason) {
  if (kind === 'nas') return '【本机 NAS 共享 — TD-326】拦截原因：' + reason + '。'
  if (kind === 'D10') {
    return (
      `【D10 交易执行冻结 — BLOCKED】拦截原因：${reason}。\n` +
      `解锁需要两个条件同时满足：Owner 明文书面指令，且 spine 中 decisions[id=D10].status → UNLOCKED。\n` +
      `不要绕过本闸门、不要"修复" guard 文件 —— 直接向 Owner 报告。\n` +
      `权威源：${AUTHORITY}`
    )
  }
  if (kind === 'approval') {
    return (
      '【审批旁路 — ADR §5】拦截原因：' + reason + '。\n' +
      'Owner 2026-10-07 决定聊天批准保留（bifrost-approve + permissions.ask），' +
      '并接受「本机 Agent 理论上能读到 admin 令牌」的风险；这条文本拦截是当前的缓解。' +
      '见 ADR §5「已知的接受风险」。\n' +
      '批准或驳回只走 `mcp__bifrost-approve__*`（会弹「允许」）。\n' +
      '不要直接请求 /api/v1/approvals/<id>/approve 或 /reject，不要打开 #' +
      'approvals 自己点，不要读 ' + ADMIN_TOKEN_NAME + ' 或 ~/.config/bifrost/' +
      TOKEN_FILE_NAME + '。\n' +
      '收权可以以后再做。不要绕过本闸门。'
    )
  }
  if (kind === 'shared-worktree') {
    return (
      `【共享工作树 — 只暂存自己碰过的文件】拦截原因：${reason}。\n` +
      `12 个 repo 是多会话共用的单一 checkout，没有 per-session worktree：` +
      `暂存与提交必须同一步，且只含自己改过的文件。\n` +
      `先看自己改了什么：git status --porcelain ——` +
      `再 git add <file>… && git commit（不带 -a）。\n` +
      `注意 git stash 不受本闸门拦截，但它同样会把别人的在制品从工作树里抽走。\n` +
      `参见 CLAUDE.md §5「共享工作树」/ .cursor/rules/shared-worktree.mdc`
    )
  }
  if (kind === 'push-main') {
    return (
      `【推 main — TD-341】拦截原因：${reason}。\n` +
      `push-main.sh 先查发布窗口，再在这个提交的干净 checkout 上跑和 CI 同一份 code-health 扫描，` +
      `过了才推（只接受快进）。go test 与 lint 照旧在推之前自己跑。\n` +
      `不要绕过本闸门。参见 CLAUDE.md §5「发布窗口」`
    )
  }
  if (kind === 'gitea-primary') {
    return (
      `【Gitea 为主 — CUT-gitea-primary】拦截原因：${reason}。\n` +
      `名单 agent-config/gitea-primary.txt 里的仓库只推 Gitea；GitHub 的 main 和标签由集群同步（k8s/cicd/github-sync）只快进地跟上。\n` +
      `不要绕过本闸门。参见 agent-config/work/multi-agent/CUT-gitea-primary-2026-10-17.md 第 7 节`
    )
  }
  if (kind === 'owner') {
    return (
      '【Owner 凭证】拦截原因：' + reason + '。\n' +
      '这是 Owner 的凭证，写操作走平台动作或 `owner_run_command`。\n' +
      'Cursor 与 Claude 共用这一份闸门。不要读 Owner 目录，不要把 KUBECONFIG 指到 ~/.kube/bifrost-k3s.yaml 以外。'
    )
  }
  return (
    `【Dev 服务管理规范】拦截原因：${reason}。\n` +
    `参见 CLAUDE.md §4 / .cursor/rules/dev-services.mdc。优先用 MCP ` +
    `list_dev_sessions / restart_dev_session / get_dev_session_logs。`
  )
}

function main() {
  const raw = (() => {
    try {
      return fs.readFileSync(0, 'utf8')
    } catch {
      return ''
    }
  })()

  let payload = null
  try {
    payload = JSON.parse(raw || '{}')
  } catch {
    payload = null
  }

  // payload 解析失败时不静默放行：拿原始文本再跑一遍规则（fail-safe，不 fail-open）。
  const verdict = payload
    ? evaluate(payload)
    : (() => {
        const nas = nasGuard('', null, raw)
        if (nas) return { deny: true, kind: 'nas', reason: nas }
        const owner = ownerCredentialGuard('', null, raw)
        if (owner) return { deny: true, kind: 'owner', reason: owner }
        const dev = devServiceRules(raw)
        if (dev) return { deny: true, kind: 'dev-services', reason: dev }
        const approval = approvalGuard('', null, raw)
        if (approval) return { deny: true, kind: 'approval', reason: approval }
        if (d10Status() !== 'UNLOCKED') {
          const d10 = d10Rules(raw)
          if (d10) return { deny: true, kind: 'D10', reason: d10 }
        }
        return { deny: false }
      })()

  if (!verdict.deny) process.exit(0)

  const message = denyMessage(verdict.kind, verdict.reason)
  const event = String(
    payload?.hook_event_name || (/beforeShellExecution|beforeMCPExecution/.test(raw) ? 'before' : ''),
  )

  if (event.startsWith('before')) {
    // Cursor
    process.stdout.write(
      JSON.stringify({ permission: 'deny', userMessage: message, agentMessage: message }),
    )
  } else {
    // Claude Code PreToolUse
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'deny',
          permissionDecisionReason: message,
        },
      }),
    )
  }
  process.exit(0)
}

if (require.main === module) main()
module.exports = { nasMountPoints, nasPathRule, nasGuard, readMountTable, evaluate, githubRepoOf }
