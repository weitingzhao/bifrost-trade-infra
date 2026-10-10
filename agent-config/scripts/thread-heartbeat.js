#!/usr/bin/env node
'use strict'
/**
 * Thread heartbeat (W-54): one script for the hooks of Claude Code, Cursor and
 * Codex. Each turn start, tool call (before / after) and turn end is posted to
 * PROD platform-api, which pages the Owner once when a thread stops mid-turn.
 *
 *   node thread-heartbeat.js hook <claude|cursor|codex>        hook payload on stdin
 *   node thread-heartbeat.js run <vendor> -- <command> [args]  headless run
 *
 * `run` is for headless sessions (`cursor-agent -p` fires no stop hook): it
 * reports turn start, runs the command with BIFROST_HEARTBEAT_THREAD set so the
 * session's own hooks report under the same thread, and reports turn end when
 * the command exits.
 *
 * A hook never blocks or slows a tool call: it prints nothing and always exits 0.
 * The first event of a thread is sent synchronously, with a one-second timeout,
 * so the script can store the server-issued thread key (mode 600). Later events
 * carry that key, a turn id and a sequence, and are handed to a detached child.
 * A failure leaves the key unset and the next event tries again.
 *
 * Config (nothing secret lives in the repo):
 *   PLATFORM_HEARTBEAT_URL    platform-api base (default: PROD VIP NodePort)
 *   PLATFORM_REPORTER_TOKEN   reporter token, or the first line of
 *   ~/.config/bifrost/lineage-reporter.token   (the TD-197 token; no token → nothing is sent)
 *   BIFROST_WORK              work item (W-n); otherwise taken from the thread title
 *   BIFROST_HEARTBEAT=off     send nothing
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { spawn } = require('node:child_process')

const DEFAULT_URL = 'http://192.168.10.100:30876' // bifrost-platform-prod platform-api NodePort on the VIP
const ROUTE = '/api/v1/agent/threads/heartbeat'
const THROTTLE_MS = 15 * 1000
const HOOK_DEADLINE_MS = 3000
const FIRST_EVENT_TIMEOUT_MS = 1000
const KEY_RE = /^[0-9a-f]{64}$/
const TURN_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
// Only these mean the person has to act. Every other notification is ignored.
const WAITING_NOTIFICATIONS = new Set(['permission_prompt', 'idle_prompt', 'elicitation'])

const EVENTS = {
  claude: {
    UserPromptSubmit: 'turn_start',
    PreToolUse: 'before_tool',
    PostToolUse: 'after_tool',
    PostToolUseFailure: 'after_tool',
    SubagentStop: 'after_tool',
    Stop: 'turn_end',
  },
  cursor: {
    beforeSubmitPrompt: 'turn_start',
    preToolUse: 'before_tool',
    postToolUse: 'after_tool',
    postToolUseFailure: 'after_tool',
    subagentStop: 'after_tool',
    stop: 'turn_end',
    sessionEnd: 'turn_end',
  },
  codex: {
    UserPromptSubmit: 'turn_start',
    PreToolUse: 'before_tool',
    PostToolUse: 'after_tool',
    Stop: 'turn_end',
  },
}

function home(...p) {
  return path.join(process.env.BIFROST_HOME_OVERRIDE || os.homedir(), ...p)
}

function token() {
  if (process.env.PLATFORM_REPORTER_TOKEN) return process.env.PLATFORM_REPORTER_TOKEN.trim()
  try {
    return fs.readFileSync(home('.config', 'bifrost', 'lineage-reporter.token'), 'utf8').split('\n')[0].trim()
  } catch {
    return ''
  }
}

function baseURL() {
  return (process.env.PLATFORM_HEARTBEAT_URL || DEFAULT_URL).replace(/\/+$/, '')
}

function hostName() {
  return (os.hostname().split('.')[0] || 'unknown').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

/** Seconds a tool call may legitimately run, from the timeout it declared (0 = none). */
function toolTimeoutSeconds(input) {
  if (!input || typeof input !== 'object') return 0
  const pick = o => {
    if (!o || typeof o !== 'object') return 0
    for (const k of ['timeout', 'timeout_ms', 'block_until_ms', 'yield_time_ms']) {
      if (Number.isFinite(o[k]) && o[k] > 0) return Math.ceil(o[k] / 1000)
    }
    for (const k of ['timeout_seconds', 'timeout_s']) {
      if (Number.isFinite(o[k]) && o[k] > 0) return Math.ceil(o[k])
    }
    return 0
  }
  return Math.min(pick(input) || pick(input.arguments), 86400)
}

/** Title Claude reported for this transcript (report-thread-title.js keeps it). */
function claudeTitle(id) {
  const st = readJSON(home('.cache', 'bifrost', 'lineage-titles.json'))
  const e = st && st[id]
  return (e && (e.custom || e.ai)) || ''
}

/** Codex keeps thread names in ~/.codex/session_index.jsonl; the last line for an id wins. */
function codexTitle(id) {
  const file = path.join(process.env.CODEX_HOME || home('.codex'), 'session_index.jsonl')
  let fd
  try {
    fd = fs.openSync(file, 'r')
    const size = fs.fstatSync(fd).size
    const len = Math.min(size, 512 * 1024)
    const buf = Buffer.alloc(len)
    fs.readSync(fd, buf, 0, len, size - len)
    const lines = buf.toString('utf8').split('\n')
    for (let i = lines.length - 1; i >= 0; i--) {
      if (!lines[i].includes(id)) continue
      try {
        const rec = JSON.parse(lines[i])
        if (rec.id === id && rec.thread_name) return rec.thread_name
      } catch {
        // a cut first line is not JSON
      }
    }
  } catch {
    // no index: no title
  } finally {
    if (fd !== undefined) fs.closeSync(fd)
  }
  return ''
}

function workFrom(title) {
  const env = (process.env.BIFROST_WORK || '').trim()
  if (env) return env
  const m = /\b(W-\d+)\b/.exec(title || '')
  return m ? m[1] : ''
}

/** Map one hook payload to a heartbeat body, or null when the event is not one we report. */
function beatFor(vendor, payload) {
  const map = EVENTS[vendor]
  if (!map || !payload || typeof payload !== 'object') return null
  let event = map[payload.hook_event_name]
  let reason = ''
  if (payload.hook_event_name === 'Notification') {
    const kind = String(payload.notification_type || '')
    if (!WAITING_NOTIFICATIONS.has(kind)) return null
    event = 'waiting_owner'
    reason = kind
  }
  if (!event) return null
  const thread = String(
    process.env.BIFROST_HEARTBEAT_THREAD || payload.session_id || payload.conversation_id || '',
  ).trim()
  if (!thread) return null
  let title = (process.env.BIFROST_HEARTBEAT_TITLE || '').trim()
  if (!title && vendor === 'claude') title = claudeTitle(thread)
  if (!title && vendor === 'codex') title = codexTitle(thread)
  const body = { thread, vendor, host: hostName(), event }
  const work = workFrom(title)
  if (work) body.work = work
  if (title) body.title = title.slice(0, 160)
  if (reason) body.reason = reason
  if (event === 'before_tool' || event === 'after_tool') {
    const tool = String(payload.tool_name || (payload.subagent_type ? `subagent:${payload.subagent_type}` : '')).trim()
    if (tool) body.tool = tool.replace(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 96)
  }
  if (event === 'before_tool') {
    const t = toolTimeoutSeconds(payload.tool_input)
    if (t > 0) body.tool_timeout_s = t
  }
  const useID = String(payload.tool_use_id || payload.tool_call_id || '').trim()
  if (useID) body.tool_use_id = useID.replace(/[^A-Za-z0-9_.:-]/g, '').slice(0, 128)
  return body
}

function wireBody(body) {
  const out = { ...body }
  delete out.tool_use_id
  return out
}

/**
 * Whether to skip a beat: a tool event with no declared timeout within
 * THROTTLE_MS of the last one sent for the same thread. Turn start and end,
 * a declared timeout, and the first event after a turn end always go out.
 */
function matchesPending(body, last) {
  if (!last || !last.pending || body.event !== 'after_tool') return false
  const pending = last.pending
  if (pending.id) return body.tool_use_id === pending.id
  if (pending.tool && body.tool) return body.tool === pending.tool
  return false
}

function shouldSkip(body, last, now) {
  if (!last) return false
  if (matchesPending(body, last)) return false
  if (body.event !== 'before_tool' && body.event !== 'after_tool') return false
  if (body.tool_timeout_s) return false
  if (last.ev === 'turn_end' || last.ev === 'waiting_owner') return false
  return now - last.at < THROTTLE_MS
}

function sentState(prev, body, now) {
  const next = {
    at: now,
    ev: body.event,
    tool: body.tool || '',
    tool_use_id: body.tool_use_id || '',
    pending: prev && prev.pending ? prev.pending : null,
  }
  if (body.event === 'before_tool' && body.tool_timeout_s) {
    next.pending = { tool: body.tool || '', id: body.tool_use_id || '', timeout: body.tool_timeout_s }
  } else if (
    matchesPending(body, prev) ||
    body.event === 'turn_end' ||
    body.event === 'turn_start' ||
    body.event === 'waiting_owner'
  ) {
    next.pending = null
  }
  return next
}

function reduceThrottle(prev, body, now) {
  if (shouldSkip(body, prev, now)) return { skip: true, next: prev }
  return { skip: false, next: sentState(prev, body, now) }
}

function throttleFile() {
  return home('.cache', 'bifrost', 'heartbeat.json')
}

function writeThrottle(st, now) {
  const file = throttleFile()
  for (const k of Object.keys(st)) {
    if (!st[k] || now - st[k].at > 24 * 3600 * 1000) delete st[k]
  }
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    const tmp = `${file}.${process.pid}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(st))
    fs.renameSync(tmp, file)
  } catch {
    // a lost throttle mark only means one extra beat
  }
}

function rememberSent(body, now = Date.now()) {
  const st = readJSON(throttleFile()) || {}
  const key = `${body.vendor}/${body.thread}`
  st[key] = sentState(st[key], body, now)
  writeThrottle(st, now)
}

/** Skip and, when not skipping, remember the beat. Returns true when the beat is dropped. */
function throttled(body, now = Date.now()) {
  const st = readJSON(throttleFile()) || {}
  const key = `${body.vendor}/${body.thread}`
  const decision = reduceThrottle(st[key], body, now)
  if (decision.skip) return true
  st[key] = decision.next
  writeThrottle(st, now)
  return false
}

function gatePath(vendor, thread) {
  if (!/^[a-z][a-z0-9-]{0,31}$/.test(vendor) || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(thread)) return ''
  return home('.cache', 'bifrost', 'thread-keys', vendor, thread)
}

function loadGate(vendor, thread) {
  const file = gatePath(vendor, thread)
  const empty = { key: '', turn_id: '', seq: 0 }
  if (!file) return empty
  const st = readJSON(file)
  if (!st || typeof st !== 'object') return empty
  return {
    key: typeof st.key === 'string' && KEY_RE.test(st.key) ? st.key : '',
    turn_id: typeof st.turn_id === 'string' && TURN_RE.test(st.turn_id) ? st.turn_id : '',
    seq: Number.isInteger(st.seq) && st.seq > 0 ? st.seq : 0,
  }
}

function saveGate(vendor, thread, gate) {
  const file = gatePath(vendor, thread)
  if (!file) return
  const vendorDir = path.dirname(file)
  const root = path.dirname(vendorDir)
  fs.mkdirSync(root, { recursive: true, mode: 0o700 })
  fs.mkdirSync(vendorDir, { recursive: true, mode: 0o700 })
  try {
    fs.chmodSync(root, 0o700)
    fs.chmodSync(vendorDir, 0o700)
  } catch {
    // the mode is retried on the file itself
  }
  const tmp = `${file}.${process.pid}.tmp`
  fs.writeFileSync(tmp, JSON.stringify({ key: gate.key, turn_id: gate.turn_id, seq: gate.seq }), { mode: 0o600 })
  fs.chmodSync(tmp, 0o600)
  fs.renameSync(tmp, file)
  fs.chmodSync(file, 0o600)
}

function stamp(body) {
  const gate = loadGate(body.vendor, body.thread)
  let turn = gate.turn_id
  if (body.event === 'turn_start' || !turn) turn = crypto.randomUUID()
  body.turn_id = turn
  body.seq = gate.seq + 1
  if (gate.key) body.thread_key = gate.key
  return gate
}

async function post(body, timeoutMs = 5000) {
  const tok = token()
  if (!tok || process.env.BIFROST_HEARTBEAT === 'off') return { sent: false, why: tok ? 'off' : 'no reporter token', key: '' }
  try {
    const res = await fetch(`${baseURL()}${ROUTE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
      body: JSON.stringify(wireBody(body)),
      signal: AbortSignal.timeout(timeoutMs),
    })
    let key = ''
    try {
      const parsed = JSON.parse(await res.text())
      if (parsed && typeof parsed.thread_key === 'string' && KEY_RE.test(parsed.thread_key)) key = parsed.thread_key
    } catch {
      // a body that is not JSON is a bad response; the next event retries
    }
    return { sent: res.ok, status: res.status, key }
  } catch (err) {
    return { sent: false, why: err.message, key: '' }
  }
}

/** Hand the POST to a detached child. The body sits in a mode-600 file, not the environment. */
function sendDetached(body) {
  if (!token() || process.env.BIFROST_HEARTBEAT === 'off') return
  const dir = home('.cache', 'bifrost', 'heartbeat-out')
  let file = ''
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
    fs.chmodSync(dir, 0o700)
    file = path.join(dir, `${process.pid}-${crypto.randomBytes(8).toString('hex')}.json`)
    fs.writeFileSync(file, JSON.stringify(wireBody(body)), { mode: 0o600 })
    fs.chmodSync(file, 0o600)
  } catch {
    return
  }
  const child = spawn(process.execPath, [__filename, '--send', file], { detached: true, stdio: 'ignore' })
  child.on('error', () => {
    try {
      fs.unlinkSync(file)
    } catch {
      // the child may already have taken it
    }
  })
  child.unref()
}

function readStdin(limit = 1 << 20) {
  return new Promise(resolve => {
    let s = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', d => {
      if (s.length < limit) s += d
    })
    process.stdin.on('end', () => resolve(s))
    process.stdin.on('error', () => resolve(s))
  })
}

async function hook(vendor) {
  const raw = await readStdin()
  let payload
  try {
    payload = JSON.parse(raw || '{}')
  } catch {
    return
  }
  const body = beatFor(vendor, payload)
  if (!body) return
  const gate = stamp(body)
  if (!gate.key) {
    const res = await post(body, FIRST_EVENT_TIMEOUT_MS)
    if (res.sent && res.key) {
      saveGate(body.vendor, body.thread, { key: res.key, turn_id: body.turn_id, seq: body.seq })
      rememberSent(body)
    }
    return
  }
  if (throttled(body)) return
  saveGate(body.vendor, body.thread, { key: gate.key, turn_id: body.turn_id, seq: body.seq })
  sendDetached(body)
}

async function run(vendor, argv) {
  const sep = argv.indexOf('--')
  const cmd = sep >= 0 ? argv.slice(sep + 1) : argv
  if (cmd.length === 0) {
    process.stderr.write('usage: thread-heartbeat.js run <vendor> -- <command> [args...]\n')
    return 2
  }
  const thread = process.env.BIFROST_HEARTBEAT_THREAD || `run-${crypto.randomUUID()}`
  const title = (process.env.BIFROST_HEARTBEAT_TITLE || `headless ${path.basename(cmd[0])}`).slice(0, 160)
  const base = { thread, vendor, host: hostName(), title }
  const work = workFrom(title)
  if (work) base.work = work
  const turn = crypto.randomUUID()
  const started = await post({ ...base, event: 'turn_start', turn_id: turn, seq: 1 }, 3000)
  if (started.sent && started.key) saveGate(vendor, thread, { key: started.key, turn_id: turn, seq: 1 })
  const child = spawn(cmd[0], cmd.slice(1), {
    stdio: 'inherit',
    env: { ...process.env, BIFROST_HEARTBEAT_THREAD: thread, BIFROST_HEARTBEAT_TITLE: title },
  })
  const forward = sig => () => child.kill(sig)
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, forward(sig))
  const code = await new Promise(resolve => {
    child.on('error', err => {
      process.stderr.write(`thread-heartbeat: ${err.message}\n`)
      resolve(127)
    })
    child.on('exit', (c, sig) => resolve(c === null ? 128 + (os.constants.signals[sig] || 0) : c))
  })
  const gate = loadGate(vendor, thread)
  const end = {
    ...base,
    event: 'turn_end',
    turn_id: gate.turn_id || turn,
    seq: (gate.seq || 1) + 1,
  }
  if (gate.key) end.thread_key = gate.key
  const ended = await post(end, 3000)
  if (ended.sent && gate.key) saveGate(vendor, thread, { key: gate.key, turn_id: end.turn_id, seq: end.seq })
  return code
}

async function main(argv) {
  const [mode, vendor, ...rest] = argv
  if (mode === '--send') {
    try {
      const raw = fs.readFileSync(vendor, 'utf8')
      try {
        fs.unlinkSync(vendor)
      } catch {
        // unlinking a sent file is best-effort
      }
      await post(JSON.parse(raw))
    } catch {
      // nothing to do: a lost beat at worst delays nothing and pages nothing
    }
    return 0
  }
  if (mode === 'run') return run(vendor || 'other', rest)
  if (mode === 'hook') {
    // Nothing may reach stdout (Cursor reads it as a permission answer) and the
    // exit code is always 0, whatever happens.
    const deadline = setTimeout(() => process.exit(0), HOOK_DEADLINE_MS)
    deadline.unref()
    try {
      await hook(vendor)
    } catch {
      // a hook never blocks a session
    }
    return 0
  }
  process.stderr.write('usage: thread-heartbeat.js hook <vendor> | run <vendor> -- <command>\n')
  return 0
}

if (require.main === module) {
  process.on('uncaughtException', () => process.exit(0))
  process.on('unhandledRejection', () => process.exit(0))
  main(process.argv.slice(2)).then(
    code => process.exit(code),
    () => process.exit(0),
  )
}

module.exports = { beatFor, toolTimeoutSeconds, shouldSkip, reduceThrottle, EVENTS, WAITING_NOTIFICATIONS }
