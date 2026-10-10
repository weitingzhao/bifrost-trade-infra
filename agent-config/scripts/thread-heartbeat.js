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
 * A hook never blocks or slows a tool call: it prints nothing, always exits 0,
 * and hands the POST to a detached child.
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

const EVENTS = {
  claude: {
    UserPromptSubmit: 'turn_start',
    PreToolUse: 'before_tool',
    PostToolUse: 'after_tool',
    PostToolUseFailure: 'after_tool',
    SubagentStop: 'after_tool',
    // Waiting on a person (permission prompt, idle prompt) is not a hang.
    Notification: 'turn_end',
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
  const event = map[payload.hook_event_name]
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
  if (event === 'before_tool' || event === 'after_tool') {
    const tool = String(payload.tool_name || (payload.subagent_type ? `subagent:${payload.subagent_type}` : '')).trim()
    if (tool) body.tool = tool.replace(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 96)
  }
  if (event === 'before_tool') {
    const t = toolTimeoutSeconds(payload.tool_input)
    if (t > 0) body.tool_timeout_s = t
  }
  return body
}

/**
 * Whether to skip a beat: a tool event with no declared timeout within
 * THROTTLE_MS of the last one sent for the same thread. Turn start and end,
 * a declared timeout, and the first event after a turn end always go out.
 */
function shouldSkip(body, last, now) {
  if (!last) return false
  if (body.event !== 'before_tool' && body.event !== 'after_tool') return false
  if (body.tool_timeout_s) return false
  if (last.ev === 'turn_end') return false
  return now - last.at < THROTTLE_MS
}

function throttled(body, now = Date.now()) {
  const file = home('.cache', 'bifrost', 'heartbeat.json')
  const st = readJSON(file) || {}
  const key = `${body.vendor}/${body.thread}`
  if (shouldSkip(body, st[key], now)) return true
  st[key] = { at: now, ev: body.event }
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
  return false
}

async function post(body, timeoutMs = 5000) {
  const tok = token()
  if (!tok || process.env.BIFROST_HEARTBEAT === 'off') return { sent: false, why: tok ? 'off' : 'no reporter token' }
  try {
    const res = await fetch(`${baseURL()}${ROUTE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    })
    return { sent: res.ok, status: res.status }
  } catch (err) {
    return { sent: false, why: err.message }
  }
}

/** Hand the POST to a detached child so the hook returns at once. */
function sendDetached(body) {
  if (!token() || process.env.BIFROST_HEARTBEAT === 'off') return
  const child = spawn(process.execPath, [__filename, '--send'], {
    detached: true,
    stdio: 'ignore',
    env: { ...process.env, BIFROST_HEARTBEAT_BODY: JSON.stringify(body) },
  })
  child.on('error', () => {})
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
  if (!body || throttled(body)) return
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
  await post({ ...base, event: 'turn_start' }, 3000)
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
  await post({ ...base, event: 'turn_end' }, 3000)
  return code
}

async function main(argv) {
  const [mode, vendor, ...rest] = argv
  if (mode === '--send') {
    try {
      await post(JSON.parse(process.env.BIFROST_HEARTBEAT_BODY || '{}'))
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

module.exports = { beatFor, toolTimeoutSeconds, shouldSkip, EVENTS }
