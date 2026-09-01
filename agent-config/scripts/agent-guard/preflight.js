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
 *   禁止动作清单  → bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts · FORBIDDEN_ACTIONS
 *   dev-services  → .cursor/rules/dev-services.mdc · CLAUDE.md §4
 *
 * 设计要点：
 *  1. D10 闸门与 spine 同源 —— Owner 把 spine 里的 D10 改成 UNLOCKED，本脚本自动放行，
 *     不需要改代码、不需要改两处配置。
 *  2. 风险分级 —— D10（高风险）宁可误报不可漏报；dev-services（卫生规则）对只读命令
 *     与写文件命令豁免，避免把"提到某命令的文本"误判成"要执行该命令"。
 *
 * 回归测试见 scripts/agent-guard/README.md。
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
  'spine D10 · bifrost-platform/config/ops-context.yaml · agentProtocolCatalog.ts FORBIDDEN_ACTIONS'

// ─────────────────────────────── D10 规则（高风险，不豁免） ───────────────────────────────
// Research domain writes are ALLOWED while D10 is BLOCKED:
//   research.ai_draft kind=order_intent · research.candidate_pool · harness propose-only
// ib:operator:cmd remains blocked (only Daemon may write that stream).

/** 仅在 spine D10 !== UNLOCKED 时生效。 */
function d10Rules(cmd) {
  // 1. 写 ib:operator:cmd（唯一合法写入方是 Daemon 本身）
  const OP_STREAM = 'ib:operator:' + 'cmd'
  if (cmd.includes(OP_STREAM) && /\b(xadd|lpush|rpush|publish|set|hset|del)\b/i.test(cmd)) {
    return '写入 `' + OP_STREAM + '` — 唯一合法写入方是 Daemon 本身，Agent 永远不写这个 Stream'
  }

  // 2. Monitor 控制端点写操作
  if (
    /\/api\/monitor\/control\//.test(cmd) &&
    /-X\s*(POST|PUT|DELETE)|--request\s*(POST|PUT|DELETE)/i.test(cmd)
  ) {
    return 'Monitor `POST /api/monitor/control/*` — 可能武装实盘交易'
  }

  // 3. 把 daemon 扩到 >0 副本
  if (/kubectl[^;|&]*\bscale\b/.test(cmd) && /daemon/.test(cmd)) {
    const m = /--replicas[= ]+(\d+)/.exec(cmd)
    if (m && Number(m[1]) > 0) {
      return `为 daemon 扩容到 ${m[1]} 副本 — STG 必须保持 replicas: 0`
    }
  }

  // 4. 删除 / 移动 / 截断 D10 guard 文件
  if (GUARD_FILES.test(cmd) && /\b(rm|mv|truncate|kubectl\s+delete)\b/.test(cmd)) {
    return '删除或移动 D10 infra guard（daemon-scale-zero / daemon-observe-safe）'
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

// ─────────────────────────────── 判定 ───────────────────────────────

function evaluate(payload) {
  const event = String(payload.hook_event_name || '')
  const isCursorShell = event === 'beforeShellExecution'
  const toolName = payload.tool_name || (isCursorShell ? 'Bash' : '')
  const input = payload.tool_input || (isCursorShell ? { command: payload.command } : {})

  const locked = d10Status() !== 'UNLOCKED'
  const cmd = String(input.command ?? payload.command ?? '')

  if (cmd) {
    const dev = devServiceRules(cmd)
    if (dev) return { deny: true, kind: 'dev-services', reason: dev }
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
        const dev = devServiceRules(raw)
        if (dev) return { deny: true, kind: 'dev-services', reason: dev }
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
