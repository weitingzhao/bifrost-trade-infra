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
const APPROVAL_API = new RegExp(
  '/api/v1/' + 'approvals/[^/\\s"\'`?#]+/(approve|reject)\\b',
)

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
  if (/^mcp__bifrost-approve__/.test(name)) return null

  const text = approvalText(name, input, cmd)
  if (!text) return null

  if (text.includes(ADMIN_TOKEN_NAME) || text.includes(TOKEN_FILE_NAME)) {
    return (
      '读取或引用 `' + ADMIN_TOKEN_NAME + '` 或 `' + TOKEN_FILE_NAME +
      '`。ADR §5：admin 令牌留在本机只为聊天批准弹窗，不给 Agent 拿去直接用'
    )
  }
  if (APPROVAL_API.test(text)) {
    return (
      '直接请求 `/api/v1/approvals/<id>/approve` 或 `/reject`（curl、wget、fetch 等都算）。' +
      'ADR §5：批准只走会弹窗的 bifrost-approve'
    )
  }

  const browserName = /browser|WebFetch|playwright|puppeteer|selenium/i.test(name)
  const opensPage =
    text.includes(APPROVALS_HASH) &&
    (browserName ||
      /\b(curl|wget|fetch|open|xdg-open|chrome|chromium|osascript|browse|click|locator|getByRole|getByText|playwright|puppeteer|selenium)\b/i.test(
        text,
      ))
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

// ─────────────────────────────── 判定 ───────────────────────────────

function evaluate(payload) {
  const event = String(payload.hook_event_name || '')
  const isCursorShell = event === 'beforeShellExecution'
  const toolName = payload.tool_name || (isCursorShell ? 'Bash' : '')
  const input = payload.tool_input || (isCursorShell ? { command: payload.command } : {})

  const locked = d10Status() !== 'UNLOCKED'
  const cmd = String(input.command ?? payload.command ?? '')

  const owner = ownerCredentialGuard(toolName, input, cmd)
  if (owner) return { deny: true, kind: 'owner', reason: owner }

  const approval = approvalGuard(toolName, input, cmd)
  if (approval) return { deny: true, kind: 'approval', reason: approval }

  if (cmd) {
    const dev = devServiceRules(cmd)
    if (dev) return { deny: true, kind: 'dev-services', reason: dev }
    const sw = sharedWorktreeRules(cmd)
    if (sw) return { deny: true, kind: 'shared-worktree', reason: sw }
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

main()
