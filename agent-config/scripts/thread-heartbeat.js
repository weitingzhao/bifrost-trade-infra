#!/usr/bin/env node
'use strict'
/**
 * Thread heartbeat (W-54): one script for the hooks of Claude Code, Cursor and
 * Codex. Each turn start, tool call (before / after) and turn end is posted to
 * PROD platform-api. A mid-turn stop can page the Owner, and that push may
 * arrive twice.
 *
 *   node thread-heartbeat.js hook <claude|cursor|codex>        hook payload on stdin
 *   node thread-heartbeat.js run <vendor> -- <command> [args]  headless run
 *
 * `run` is for headless sessions (`cursor-agent -p` fires no stop hook): it
 * reports turn start, runs the command with BIFROST_HEARTBEAT_THREAD set so the
 * session's own hooks report under the same thread, and reports turn end when
 * the command exits.
 *
 * A hook prints nothing and always exits 0. It does not return a permission
 * denial. It can wait before giving up: a 3 second timer exits the process,
 * and taking the thread lock blocks the event loop for up to 2 seconds. That
 * wait is not cut short by the timer, so one lock can run past the deadline.
 * The real bound is 5 seconds (3 + 2); the process then exits. The first
 * registration, and a turn_start the server has not confirmed, wait on the
 * network inside that bound.
 *
 * Sequence and turn id are allocated under a per-thread flock. A helper holds
 * the lock on an open file descriptor; the operating system releases it when
 * this process exits (the helper's stdin closes). `run` uses that same lock.
 *
 * The client generates a registration nonce and sends it with every event.
 * If the first response is lost, the next event repeats the nonce and the
 * server returns the same key for a short window. A response is applied only
 * to the record it was requested for, the same thread id and nonce, under
 * the lock. A 409 whose error is "unknown key" does not reuse that key: that
 * record is kept as superseded and the event is registered again under a new
 * thread id. A late response never falls back to the current record. An old
 * 409 for a record that is already superseded does nothing.
 * A turn_start the server has not confirmed is kept and sent again before
 * any later event of that turn. A finished turn is not reopened: a 409
 * "older turn refused" does not supersede the record.
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
const LOCK_WAIT_MS = 2000
// The lock wait blocks the event loop, so the 3 second timer cannot fire
// during it. One such wait can finish after the timer was already due.
// HOOK_DEADLINE_MS + LOCK_WAIT_MS is the real give-up bound: 5 seconds.
const HOOK_GIVE_UP_MS = HOOK_DEADLINE_MS + LOCK_WAIT_MS
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
  delete out.session
  return out
}

function threadKey(body) {
  return `${body.vendor}/${body.session || body.thread}`
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
  const key = threadKey(body)
  st[key] = sentState(st[key], body, now)
  writeThrottle(st, now)
}

/** Skip and, when not skipping, remember the beat. Returns true when the beat is dropped. */
function throttled(body, now = Date.now()) {
  const st = readJSON(throttleFile()) || {}
  const key = threadKey(body)
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

function normalizeRecord(raw, fallbackID) {
  if (!raw || typeof raw !== 'object') return null
  const id = typeof raw.id === 'string' && TURN_RE.test(raw.id) ? raw.id : fallbackID
  if (!id || !TURN_RE.test(id)) return null
  return {
    id,
    key: typeof raw.key === 'string' && KEY_RE.test(raw.key) ? raw.key : '',
    nonce: typeof raw.nonce === 'string' && KEY_RE.test(raw.nonce) ? raw.nonce : '',
    turn_id: typeof raw.turn_id === 'string' && TURN_RE.test(raw.turn_id) ? raw.turn_id : '',
    seq: Number.isInteger(raw.seq) && raw.seq > 0 ? raw.seq : 0,
    status: raw.status === 'superseded' ? 'superseded' : 'active',
    // Missing means a gate written before turn confirmation existed. Those
    // records are treated as already confirmed so a restart does not replay
    // a turn_start the server already has. New records always write the flag.
    turn_confirmed: typeof raw.turn_confirmed === 'boolean' ? raw.turn_confirmed : true,
    turn_open_seq: Number.isInteger(raw.turn_open_seq) && raw.turn_open_seq > 0 ? raw.turn_open_seq : 0,
  }
}

function loadGate(vendor, thread) {
  const file = gatePath(vendor, thread)
  if (!file) return { records: [] }
  const st = readJSON(file)
  if (!st || typeof st !== 'object') return { records: [] }
  if (Array.isArray(st.records)) return { records: st.records.map(r => normalizeRecord(r)).filter(Boolean) }
  const one = normalizeRecord(
    { id: thread, key: st.key, nonce: st.nonce, turn_id: st.turn_id, seq: st.seq, status: 'active' },
    thread,
  )
  return { records: one ? [one] : [] }
}

function activeRecord(gate, session) {
  for (let i = gate.records.length - 1; i >= 0; i--) {
    if (gate.records[i].status !== 'superseded') return gate.records[i]
  }
  const created = { id: session, key: '', nonce: '', turn_id: '', seq: 0, status: 'active', turn_confirmed: true, turn_open_seq: 0 }
  gate.records.push(created)
  return created
}

function hasActiveKey(vendor, thread) {
  const gate = loadGate(vendor, thread)
  for (let i = gate.records.length - 1; i >= 0; i--) {
    if (gate.records[i].status !== 'superseded') return gate.records[i].key !== ''
  }
  return false
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
  const body = {
    records: gate.records.map(r => ({
      id: r.id,
      key: r.key,
      nonce: r.nonce,
      turn_id: r.turn_id,
      seq: r.seq,
      status: r.status,
      turn_confirmed: r.turn_confirmed === false ? false : true,
      turn_open_seq: r.turn_open_seq || 0,
    })),
  }
  const tmp = `${file}.${process.pid}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(body), { mode: 0o600 })
  fs.chmodSync(tmp, 0o600)
  fs.renameSync(tmp, file)
  fs.chmodSync(file, 0o600)
}

function sleepSync(ms) {
  const buf = new Int32Array(new SharedArrayBuffer(4))
  const end = Date.now() + ms
  while (Date.now() < end) Atomics.wait(buf, 0, 0, Math.max(1, end - Date.now()))
}

// Holds an exclusive flock until stdin closes, then exits. The kernel drops
// the lock when this helper exits, which happens when the parent exits.
const LOCK_HELPER = String.raw`
use strict;
use Fcntl qw(:flock);
use Time::HiRes qw(time sleep);
my ($path, $wait_ms, $ready) = @ARGV;
my $wait = ($wait_ms || 2000) / 1000;
open my $fh, '>>', $path or die $!;
my $deadline = time() + $wait;
sub publish {
  my ($word) = @_;
  my $tmp = $ready . ".tmp";
  open my $rf, '>', $tmp or die $!;
  print $rf $word, "\n";
  close $rf;
  rename $tmp, $ready or die $!;
}
while (1) {
  if (flock($fh, LOCK_EX | LOCK_NB)) {
    publish("ok");
    1 while sysread(STDIN, my $buf, 4096);
    exit 0;
  }
  if (time() >= $deadline) {
    publish("timeout");
    exit 1;
  }
  sleep(0.02);
}
`

function perlBin() {
  for (const candidate of ['/usr/bin/perl', '/usr/local/bin/perl']) {
    try {
      fs.accessSync(candidate, fs.constants.X_OK)
      return candidate
    } catch {
      // try the next absolute path, then PATH
    }
  }
  return 'perl'
}

function releaseHelper(child, ready) {
  // Kill through the process, not by closing the libuv fd directly. Closing
  // that fd with closeSync corrupts later network I/O in this process.
  // The kernel drops the flock when the helper dies. A crash of this process
  // closes the stdin pipe, so the helper exits even if this kill does not run.
  try {
    child.kill('SIGKILL')
  } catch {
    // the helper is already gone, and so is its flock
  }
  try {
    if (child.stdin) child.stdin.destroy()
  } catch {
    // the pipe is already closed
  }
  try {
    fs.unlinkSync(ready)
  } catch {
    // the ready file is only a signal
  }
}

// The previous lock was a directory. Move it aside by rename so two starters
// cannot both delete it, then flock the file. The file itself is never removed:
// unlinking it would let a second process flock a different inode.
function prepareLockFile(lockPath) {
  try {
    const st = fs.lstatSync(lockPath)
    if (st.isDirectory()) {
      const aside = `${lockPath}.old.${process.pid}.${crypto.randomBytes(4).toString('hex')}`
      try {
        fs.renameSync(lockPath, aside)
        fs.rmSync(aside, { recursive: true, force: true })
      } catch {
        // the other starter already moved the old directory
      }
    }
  } catch (err) {
    if (err.code !== 'ENOENT') throw err
  }
  try {
    const fd = fs.openSync(lockPath, 'a', 0o600)
    fs.closeSync(fd)
    fs.chmodSync(lockPath, 0o600)
  } catch {
    // perl creates the file on the way in; the flock is the lock
  }
}

function holdFlock(lockPath) {
  prepareLockFile(lockPath)
  const ready = `${lockPath}.ready.${process.pid}.${crypto.randomBytes(4).toString('hex')}`
  const child = spawn(perlBin(), ['-e', LOCK_HELPER, lockPath, String(LOCK_WAIT_MS), ready], {
    stdio: ['pipe', 'ignore', 'ignore'],
  })
  // The helper must not keep this process alive after the hook returns.
  // A crash still closes the stdin pipe, so the helper exits and the kernel
  // drops the flock. Release also kills it so the next waiter does not wait
  // out the helper's own timeout.
  child.unref()
  const deadline = Date.now() + LOCK_WAIT_MS + 500
  let line = ''
  try {
    while (line !== 'ok' && line !== 'timeout') {
      if (Date.now() > deadline) throw new Error('thread lock timeout')
      try {
        line = fs.readFileSync(ready, 'utf8').trim()
      } catch {
        line = ''
      }
      if (line !== 'ok' && line !== 'timeout') sleepSync(5)
    }
  } catch (err) {
    releaseHelper(child, ready)
    throw err
  }
  if (line !== 'ok') {
    releaseHelper(child, ready)
    throw new Error('thread lock timeout')
  }
  return {
    release() {
      releaseHelper(child, ready)
    },
  }
}

/** Cross-process lock. The kernel releases the flock when this process exits. */
function withThreadLock(vendor, thread, fn) {
  const file = gatePath(vendor, thread)
  if (!file) return fn()
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 })
  const held = holdFlock(`${file}.lock`)
  try {
    return fn()
  } finally {
    held.release()
  }
}

function nextThreadID(gate, session) {
  const used = new Set(gate.records.map(r => r.id))
  for (let n = 1; n < 1000; n++) {
    const candidate = `${session}:${n}`
    if (TURN_RE.test(candidate) && !used.has(candidate)) return candidate
  }
  return `r${crypto.randomBytes(8).toString('hex')}`
}

/** Allocate turn id and sequence under the per-thread lock and persist them before the POST. */
function allocateStamp(body) {
  const session = body.session || body.thread
  body.session = session
  return withThreadLock(body.vendor, session, () => {
    const gate = loadGate(body.vendor, session)
    const rec = activeRecord(gate, session)
    // An unconfirmed turn keeps its id until the server accepts its turn_start.
    // A confirmed turn, or a record with no turn yet, mints a new id on turn_start.
    const unconfirmed = Boolean(rec.turn_id) && rec.turn_confirmed === false
    if (!unconfirmed && (body.event === 'turn_start' || !rec.turn_id)) {
      rec.turn_id = crypto.randomUUID()
      rec.turn_confirmed = false
      rec.turn_open_seq = 0
    }
    rec.seq += 1
    if (!rec.nonce) rec.nonce = crypto.randomBytes(32).toString('hex')
    if (body.event === 'turn_start' && !rec.turn_open_seq) rec.turn_open_seq = rec.seq
    body.thread = rec.id
    body.turn_id = rec.turn_id
    body.seq = rec.seq
    body.register_nonce = rec.nonce
    if (rec.key) body.thread_key = rec.key
    else delete body.thread_key
    saveGate(body.vendor, session, gate)
    return { key: rec.key }
  })
}

function matchingRecord(gate, body) {
  return gate.records.find(r => r.id === body.thread && r.nonce === body.register_nonce && r.status !== 'superseded')
}

/** Keep the old record, including its key, and open a new thread id that does not reuse it. */
function supersedeActive(body) {
  const session = body.session || body.thread
  body.session = session
  return withThreadLock(body.vendor, session, () => {
    const gate = loadGate(body.vendor, session)
    const rec = matchingRecord(gate, body)
    // A late 409 for a record that is already superseded does nothing.
    if (!rec) return null
    rec.status = 'superseded'
    const created = {
      id: nextThreadID(gate, session),
      key: '',
      nonce: crypto.randomBytes(32).toString('hex'),
      turn_id: crypto.randomUUID(),
      seq: 1,
      status: 'active',
      // This event is the new record's registration. It is not an unconfirmed
      // turn_start of the record that was just superseded.
      turn_confirmed: true,
      turn_open_seq: 0,
    }
    gate.records.push(created)
    saveGate(body.vendor, session, gate)
    body.thread = created.id
    body.turn_id = created.turn_id
    body.seq = created.seq
    body.register_nonce = created.nonce
    delete body.thread_key
    return created
  })
}

function saveIssuedKey(body, key) {
  if (typeof key !== 'string' || !KEY_RE.test(key)) return
  const session = body.session || body.thread
  withThreadLock(body.vendor, session, () => {
    const gate = loadGate(body.vendor, session)
    const rec = matchingRecord(gate, body)
    // No fallback to the current record. A late key for a superseded record is dropped.
    if (!rec) return
    rec.key = key
    saveGate(body.vendor, session, gate)
  })
}

function markTurnConfirmed(body) {
  const session = body.session || body.thread
  withThreadLock(body.vendor, session, () => {
    const gate = loadGate(body.vendor, session)
    const rec = matchingRecord(gate, body)
    if (!rec || rec.turn_id !== body.turn_id) return
    rec.turn_confirmed = true
    saveGate(body.vendor, session, gate)
  })
}

function recordFor(body) {
  const session = body.session || body.thread
  return matchingRecord(loadGate(body.vendor, session), body)
}

/** The unconfirmed turn_start that must go out before a later event of that turn. */
function preludeTurnStart(body) {
  const rec = recordFor(body)
  if (!rec || rec.turn_confirmed !== false || !rec.turn_open_seq) return null
  if (body.turn_id !== rec.turn_id) return null
  if (body.event === 'turn_start' && body.seq === rec.turn_open_seq) return null
  const start = { ...body, event: 'turn_start', seq: rec.turn_open_seq, turn_id: rec.turn_id }
  delete start.tool
  delete start.tool_timeout_s
  delete start.reason
  delete start.tool_use_id
  return start
}

function hasUnconfirmedTurn(vendor, thread) {
  const gate = loadGate(vendor, thread)
  for (let i = gate.records.length - 1; i >= 0; i--) {
    const rec = gate.records[i]
    if (rec.status === 'superseded') continue
    return rec.turn_confirmed === false && rec.turn_id !== ''
  }
  return false
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
    let error = ''
    try {
      const parsed = JSON.parse(await res.text())
      if (parsed && typeof parsed.thread_key === 'string' && KEY_RE.test(parsed.thread_key)) key = parsed.thread_key
      if (parsed && typeof parsed.error === 'string') error = parsed.error
    } catch {
      // a body that is not JSON is a bad response; the next event retries
    }
    return { sent: res.ok, status: res.status, key, error }
  } catch (err) {
    return { sent: false, why: err.message, key: '', error: '' }
  }
}

async function confirmTurnStart(body, timeoutMs) {
  const start = preludeTurnStart(body)
  if (!start) return { ok: true }
  const opened = await post(start, timeoutMs)
  if (opened.key) {
    try {
      saveIssuedKey(start, opened.key)
    } catch {
      // the next event retries with the same nonce
    }
  }
  // A finished turn stays refused. Do not supersede and do not send the later event.
  if (opened.status === 409 && opened.error === 'older turn refused') return { ok: false, res: opened }
  // The record's key is dead. The caller's own post applies that 409 to this record.
  if (opened.status === 409 && opened.error === 'unknown key') return { ok: true, res: opened }
  if (!opened.sent) return { ok: false, res: opened }
  try {
    markTurnConfirmed(start)
  } catch {
    // the start was accepted; the next event sends it again if this write failed
  }
  return { ok: true, res: opened }
}

async function postRecover(body, timeoutMs) {
  const ready = await confirmTurnStart(body, timeoutMs)
  if (!ready.ok) return ready.res
  let res = await post(body, timeoutMs)
  if (res.status === 409 && res.error === 'unknown key') {
    let created = null
    try {
      created = supersedeActive(body)
    } catch {
      return res
    }
    if (!created) return res
    res = await post(body, timeoutMs)
  }
  if (res.key) {
    try {
      saveIssuedKey(body, res.key)
    } catch {
      // the next event retries with the same nonce
    }
  }
  const rec = recordFor(body)
  if (res.sent && (body.event === 'turn_start' || !rec || !rec.turn_open_seq)) {
    try {
      markTurnConfirmed(body)
    } catch {
      // a lost confirmation mark resends the turn_start before the next event
    }
  }
  return res
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
    fs.writeFileSync(file, JSON.stringify(body), { mode: 0o600 })
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
  body.session = body.thread
  const first = !hasActiveKey(body.vendor, body.session)
  // A throttled tool event must not skip the turn_start the server never confirmed.
  if (!first && !hasUnconfirmedTurn(body.vendor, body.session) && throttled(body)) return
  try {
    allocateStamp(body)
  } catch {
    return
  }
  // The turn_start, and any later event until the server confirms it, stay in
  // this process so the start is sent before the later event.
  if (first || hasUnconfirmedTurn(body.vendor, body.session)) {
    const res = await postRecover(body, FIRST_EVENT_TIMEOUT_MS)
    if (res.sent) rememberSent(body)
    return
  }
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
  const base = { thread, vendor, host: hostName(), title, session: thread }
  const work = workFrom(title)
  if (work) base.work = work
  const start = { ...base, event: 'turn_start' }
  try {
    allocateStamp(start)
    await postRecover(start, 3000)
  } catch {
    // a headless run still starts the command
  }
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
  const end = { ...base, event: 'turn_end' }
  try {
    allocateStamp(end)
    await postRecover(end, 3000)
  } catch {
    // the command's exit code is what the caller sees
  }
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
      await postRecover(JSON.parse(raw))
    } catch {
      // a lost detached beat is not retried here; the next event sends again
    }
    return 0
  }
  if (mode === 'run') return run(vendor || 'other', rest)
  if (mode === 'hook') {
    // Nothing may reach stdout (Cursor reads it as a permission answer) and the
    // exit code is always 0. The timer is 3 seconds; a lock wait can push the
    // give-up to HOOK_GIVE_UP_MS because it blocks this timer.
    const deadline = setTimeout(() => process.exit(0), HOOK_DEADLINE_MS)
    deadline.unref()
    try {
      await hook(vendor)
    } catch {
      // a thrown error still exits 0; the wait bound is the timer plus one lock
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

module.exports = {
  beatFor,
  toolTimeoutSeconds,
  shouldSkip,
  reduceThrottle,
  EVENTS,
  WAITING_NOTIFICATIONS,
  allocateStamp,
  loadGate,
  supersedeActive,
  saveIssuedKey,
  withThreadLock,
  HOOK_GIVE_UP_MS,
}
