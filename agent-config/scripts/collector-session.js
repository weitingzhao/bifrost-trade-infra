#!/usr/bin/env node
'use strict'
/**
 * Collector mode of the hook scripts (R5:5.5-12 S1-4, design §2.3, §4, §12).
 *
 * Off by default. thread-heartbeat.js and host-heartbeat.js load this module
 * only to ask whether a collector token is configured; without one they run
 * exactly as before (reporter mode) and nothing here is used.
 *
 *   PLATFORM_COLLECTOR_TOKEN, or the first line of
 *   ~/.config/bifrost/collector.token     the collector:<host> token (role reporter)
 *   BIFROST_HOST_ID, or the first line of
 *   ~/.config/bifrost/host-id             this host's id (the <host> of the token)
 *
 * Event table (vendor hook event → heartbeat event):
 *
 *   hook event                 reporter mode    collector mode
 *   claude UserPromptSubmit    turn_start       turn_start
 *   claude Pre/PostToolUse,    before_tool /    same
 *     PostToolUseFailure,      after_tool
 *     SubagentStop
 *   claude Notification        waiting_owner    same (permission_prompt, idle_prompt, elicitation)
 *   claude Stop                turn_end         turn_end
 *   claude StopFailure         —                turn_end (§12 D4: a failed turn ends too)
 *   claude SessionStart        —                session_start, reason = source
 *                                               (startup, resume, clear, compact, fork; §12 D2)
 *   claude PreCompact          —                precompact, reason = trigger (manual, auto);
 *                                               fires for a refused compaction too (§12 D3)
 *   claude SessionEnd          —                turn_end, under the end protocol below
 *   claude InstructionsLoaded  —                — (never allocates an epoch, §12 D5)
 *   cursor (as before) + sessionStart          session_start (reason its source if the platform
 *                                               knows it, else startup: unverified, §4.2)
 *   cursor sessionEnd          turn_end         turn_end, under the end protocol
 *   codex  (as before)                         unchanged (Codex rows are unsupported, §2.5)
 *
 * Collector beats carry `session` (the vendor's raw session id, never the
 * transport thread id), `epoch`, `client_bind` and `host_id_source`, and never
 * a `title` (C10). The host is the host id. The token is the collector token.
 *
 * Epochs (§2.3): `~/.cache/bifrost/external-work/<vendor>/<session>/epochs.json`,
 * changed only under the flock `epochs.lock` beside it. A process is told
 * apart by CLAUDE_PID (§12 D1); a vendor without it falls back to the current
 * epoch. SessionStart startup / clear / fork opens epoch 1 (a repeat reuses
 * it); resume opens max+1 and supersedes the open one; compact keeps it. The
 * first wired event of a process with no epoch opens one and records the gap
 * `start_lost`.
 *
 * End protocol: SessionEnd first persists the end intent on its epoch, then
 * sends turn_end; the server's answer is recorded as `acked_at`, or as
 * `failed_at` with the gap `end_unacked`. An intent with neither is the gap
 * the audit reports. A later resume of the same session sends an unacked end
 * again before its own beat. A SessionEnd that resolves to an ended or
 * superseded epoch is dropped and counted; one that cannot be resolved by its
 * process is not executed and is recorded as `end_unresolved`.
 *
 * Not here (S1-5): registering external work (the single writer is
 * register-claude-work.py) and appending to the launcher's launch.json. Until
 * then a session with whole launcher context sends no client_bind.
 *
 *   node collector-session.js diagnose    mode, host id and its source, problems (no secrets)
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

// The platform's shapes (agentthreads idRe and hostRe; actuation collectorName).
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const HOST_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/
const COLLECTOR_HOST_RE = /^[a-z0-9-]{1,32}$/
const VENDOR_RE = /^[a-z][a-z0-9-]{0,31}$/
const START_SOURCES = new Set(['startup', 'resume', 'clear', 'compact', 'fork'])
const COMPACT_TRIGGERS = new Set(['manual', 'auto'])
const EPOCH_LOCK_MS = 2000
const KEEP_EPOCHS = 32
const KEEP_GAPS = 50
const KEEP_REPLAYS = 2

// Collector mode adds these to each vendor's reporter-mode table.
const EXTRA_EVENTS = {
  claude: { SessionStart: 'session_start', PreCompact: 'precompact', SessionEnd: 'turn_end', StopFailure: 'turn_end' },
  cursor: { sessionStart: 'session_start' },
  codex: {},
}
const START_HOOKS = new Set(['SessionStart', 'sessionStart'])
const END_HOOKS = new Set(['SessionEnd', 'sessionEnd'])

function home(...p) {
  return path.join(process.env.BIFROST_HOME_OVERRIDE || os.homedir(), ...p)
}

function firstLine(file) {
  try {
    return fs.readFileSync(file, 'utf8').split('\n')[0].trim()
  } catch {
    return ''
  }
}

function collectorToken() {
  const env = (process.env.PLATFORM_COLLECTOR_TOKEN || '').trim()
  if (env) return env
  return firstLine(home('.config', 'bifrost', 'collector.token'))
}

function osShortName() {
  return (os.hostname().split('.')[0] || 'unknown').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

/** This host's id and where it came from: env overrides file; the OS short name is the last resort. */
function hostIdentity() {
  const env = (process.env.BIFROST_HOST_ID || '').trim()
  const file = firstLine(home('.config', 'bifrost', 'host-id'))
  if (env && HOST_RE.test(env)) return { host: env, source: 'env', invalid: false }
  if (file && HOST_RE.test(file)) return { host: file, source: 'file', invalid: Boolean(env) }
  return { host: osShortName(), source: 'hostname', invalid: Boolean(env || file) }
}

function eventMap(vendor, base) {
  if (!base[vendor]) return null
  return { ...base[vendor], ...(EXTRA_EVENTS[vendor] || {}) }
}

/** Reason of a side beat: '' for other events, null when the payload names one the platform refuses. */
function sideReason(vendor, event, payload) {
  if (event === 'session_start') {
    const source = String(payload.source || '')
    if (START_SOURCES.has(source)) return source
    // Cursor's sessionStart fields are unverified (§4.2): every one of them is a start.
    return vendor === 'cursor' ? 'startup' : null
  }
  if (event === 'precompact') {
    const trigger = String(payload.trigger || '')
    return COMPACT_TRIGGERS.has(trigger) ? trigger : null
  }
  return ''
}

function readableFile(file) {
  try {
    return fs.statSync(file).isFile()
  } catch {
    return false
  }
}

/** The client's diagnosis (§3.1), or null when the session has full context: registering it is the writer's. */
function clientBind(session, env, at) {
  const bind = (state, reason) => ({ state, reason, at })
  if (!session) return bind('unlinked', 'no_vendor_session')
  const root = (env.BIFROST_PLAN_ROOT || '').trim()
  const node = (env.BIFROST_PLAN_NODE || '').trim()
  if (!root && !node) return bind('unlinked', 'no_context')
  if (!root || !node) return bind('refused', 'no_context')
  const description = (env.BIFROST_WORK_DESCRIPTION || '').trim()
  if (!description || !readableFile(description)) return bind('refused', 'no_description')
  return null
}

/** The identity fields of a hook beat before its epoch is known. */
function identity(vendor, payload, env = process.env, now = new Date()) {
  const raw = String(payload.session_id || payload.conversation_id || '').trim()
  const session = ID_RE.test(raw) ? raw : ''
  const out = {}
  if (session) out.session = session
  const bind = clientBind(session, env, now.toISOString())
  if (bind) out.client_bind = bind
  out.host_id_source = hostIdentity().source
  return out
}

/** The identity fields of a `run` wrapper's own beat: it is no vendor session. */
function runIdentity(now = new Date()) {
  return { client_bind: { state: 'unlinked', reason: 'no_vendor_session', at: now.toISOString() }, host_id_source: hostIdentity().source }
}

function sessionDir(vendor, session) {
  if (!VENDOR_RE.test(vendor) || !ID_RE.test(session)) return ''
  return home('.cache', 'bifrost', 'external-work', vendor, session)
}

function count(n) {
  return Number.isInteger(n) && n > 0 ? n : 0
}

function loadEpochs(file) {
  let raw = null
  try {
    raw = JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    raw = null
  }
  const st = raw && typeof raw === 'object' ? raw : {}
  const epochs = Array.isArray(st.epochs) ? st.epochs.filter(e => e && count(e.epoch)) : []
  const max = Math.max(count(st.max), ...epochs.map(e => e.epoch))
  return { v: 1, max, epochs, gaps: Array.isArray(st.gaps) ? st.gaps : [], dropped_ends: count(st.dropped_ends) }
}

function saveEpochs(file, st) {
  const dir = path.dirname(file)
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  st.epochs = st.epochs.slice(-KEEP_EPOCHS)
  st.gaps = st.gaps.slice(-KEEP_GAPS)
  const tmp = `${file}.${process.pid}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(st), { mode: 0o600 })
  fs.renameSync(tmp, file)
}

function isOpen(e) {
  return !e.end && !e.superseded_at
}

function latest(list) {
  let best = null
  for (const e of list) if (!best || e.epoch > best.epoch) best = e
  return best
}

/**
 * One hook event folded into a session's epochs (pure; the caller holds the
 * lock). ev: { name, kind: start|end|other, source, reason, pid, ppid, thread }.
 * Returns { epoch, identity: start|pid|first_event|current_fallback, end?, replay[] }
 * or { drop: true, why }.
 */
function transition(st, ev, now) {
  const at = now.toISOString()
  const gap = (kind, epoch) => st.gaps.push({ kind, epoch, at })
  const byPid = ev.pid > 0 ? latest(st.epochs.filter(e => e.pid === ev.pid)) : null
  const current = latest(st.epochs)
  const open = (identity, source) => {
    for (const e of st.epochs) {
      if (!isOpen(e)) continue
      e.superseded_at = at
      gap('end_missing', e.epoch)
    }
    st.max += 1
    st.epochs.push({ epoch: st.max, pid: ev.pid, ppid: ev.ppid, source, opened_by: ev.name, opened_at: at, thread: ev.thread })
    if (identity === 'first_event') gap('start_lost', st.max)
    return { epoch: st.max, identity, replay: [] }
  }
  const adopt = e => {
    // A SessionStart that arrives after this process's first event adopts its epoch.
    if (!START_HOOKS.has(e.opened_by)) Object.assign(e, { opened_by: ev.name, source: ev.source, adopted_at: at })
    return { epoch: e.epoch, identity: byPid ? 'pid' : 'current_fallback', replay: [] }
  }
  if (ev.kind === 'start' && ev.source === 'resume') {
    if (byPid && isOpen(byPid) && (byPid.source === 'resume' || !START_HOOKS.has(byPid.opened_by))) return adopt(byPid)
    const replay = []
    for (const e of st.epochs) {
      if (!e.end || e.end.acked_at || e.end.replayed_at || replay.length >= KEEP_REPLAYS) continue
      e.end.replayed_at = at
      replay.push({ epoch: e.epoch, thread: e.end.thread || e.thread || '' })
    }
    const r = open('start', 'resume')
    r.replay = replay
    return r
  }
  if (ev.kind === 'start' && ev.source !== 'compact') {
    if (!current) return open('start', ev.source)
    return adopt(byPid || current)
  }
  if (ev.kind === 'end') {
    let e = byPid
    let identity = 'pid'
    if (!e && !current) {
      const r = open('first_event', '')
      e = latest(st.epochs)
      identity = r.identity
    } else if (!e && ev.pid > 0) {
      st.dropped_ends += 1
      gap('end_unresolved', current.epoch)
      return { drop: true, why: 'end_unresolved' }
    } else if (!e) {
      e = current
      identity = 'current_fallback'
    }
    if (!isOpen(e)) {
      st.dropped_ends += 1
      if (!e.end) e.late_end = { reason: ev.reason, at }
      return { drop: true, why: 'late_end', epoch: e.epoch }
    }
    e.end = { reason: ev.reason, thread: ev.thread, intent_at: at }
    return { epoch: e.epoch, identity, end: true, replay: [] }
  }
  if (byPid) return { epoch: byPid.epoch, identity: 'pid', replay: [] }
  if (ev.pid > 0 || !current) return open('first_event', '')
  return { epoch: current.epoch, identity: 'current_fallback', replay: [] }
}

/**
 * Resolve without writing (the lock was not had): only an epoch this process
 * already has. An end goes out only for an open epoch, and its intent is not
 * recorded; any other end is dropped, never sent under a guessed key.
 */
function resolveReadOnly(st, ev) {
  const byPid = ev.pid > 0 ? latest(st.epochs.filter(e => e.pid === ev.pid)) : null
  if (ev.kind === 'end') return byPid && isOpen(byPid) ? { epoch: byPid.epoch, identity: 'pid', replay: [] } : { drop: true, why: 'end_unlocked' }
  return byPid ? { epoch: byPid.epoch, identity: 'pid', replay: [] } : null
}

function processID(vendor, env) {
  if (vendor !== 'claude') return 0
  const raw = String(env.CLAUDE_PID || '').trim()
  return /^[1-9][0-9]{0,9}$/.test(raw) ? Number(raw) : 0
}

function hookEvent(vendor, payload, body, env) {
  const name = String(payload.hook_event_name || '')
  const kind = START_HOOKS.has(name) ? 'start' : END_HOOKS.has(name) ? 'end' : 'other'
  return {
    name,
    kind,
    source: kind === 'start' ? body.reason || 'startup' : '',
    reason: kind === 'end' ? String(payload.reason || '').slice(0, 64) : '',
    pid: processID(vendor, env),
    ppid: process.ppid,
    thread: body.thread,
  }
}

function withEpochs(vendor, session, deps, fn) {
  const dir = sessionDir(vendor, session)
  if (!dir) throw new Error('no epoch directory')
  const file = path.join(dir, 'epochs.json')
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  return deps.withLock(path.join(dir, 'epochs.lock'), () => {
    const st = loadEpochs(file)
    const out = fn(st)
    saveEpochs(file, st)
    return out
  })
}

/**
 * Give a collector beat its epoch (§2.3). Mutates body.identity and, for a
 * session end, sets body._end. Returns { drop } or { replay: [beats] }.
 */
function resolve(vendor, payload, body, deps, env = process.env) {
  const id = body.identity
  if (!id || !id.session) return { replay: [] }
  const ev = hookEvent(vendor, payload, body, env)
  const now = deps.now ? deps.now() : new Date()
  let r
  try {
    r = withEpochs(vendor, id.session, deps, st => transition(st, ev, now))
  } catch {
    r = resolveReadOnly(loadEpochs(path.join(sessionDir(vendor, id.session), 'epochs.json')), ev)
  }
  if (r && r.drop) return { drop: true, why: r.why }
  if (!r) {
    // The epoch is unknown: send the beat under the old key rather than a wrong one.
    delete id.session
    id.client_bind = { state: 'unlinked', reason: 'identity_fallback', at: now.toISOString() }
    return { replay: [] }
  }
  id.epoch = r.epoch
  if (r.identity === 'current_fallback' && !id.client_bind) {
    id.client_bind = { state: 'refused', reason: 'identity_fallback', at: now.toISOString() }
  }
  if (r.end) body._end = { vendor, session: id.session, epoch: r.epoch }
  const replay = r.replay.map(rep => {
    const thread = rep.thread || body.thread
    const beat = { thread, vendor, host: body.host, event: 'turn_end' }
    beat.identity = { session: id.session, epoch: rep.epoch, host_id_source: id.host_id_source }
    if (body.sidebar) beat.sidebar = body.sidebar
    beat.session = thread
    beat._end = { vendor, session: id.session, epoch: rep.epoch }
    return beat
  })
  return { replay }
}

/** Record the server's answer to an end beat: acked, or failed with the gap end_unacked. */
function recordEnd(end, res, deps) {
  if (!end || !count(end.epoch)) return false
  const now = (deps.now ? deps.now() : new Date()).toISOString()
  return withEpochs(end.vendor, end.session, deps, st => {
    const e = st.epochs.find(x => x.epoch === end.epoch)
    if (!e || !e.end) return false
    if (res && res.sent) {
      e.end.acked_at = now
      delete e.end.failed_at
      delete e.end.why
      return true
    }
    e.end.failed_at = now
    e.end.why = String((res && (res.status || res.why)) || 'not sent').slice(0, 80)
    st.gaps.push({ kind: 'end_unacked', epoch: e.epoch, at: now })
    return false
  })
}

/** End gaps of one session's epochs: an end intent the server never acked, or an epoch left without an end. */
function endGaps(st) {
  const out = []
  for (const e of st.epochs) {
    if (e.end && !e.end.acked_at) out.push({ epoch: e.epoch, kind: 'end_unacked' })
    else if (!e.end && e.superseded_at) out.push({ epoch: e.epoch, kind: 'end_missing' })
  }
  return out
}

function diagnose() {
  const off = process.env.BIFROST_HEARTBEAT === 'off'
  const collector = collectorToken() !== ''
  const id = hostIdentity()
  const problems = []
  if (collector && id.source === 'hostname') problems.push('host_id_missing')
  if (id.invalid) problems.push('host_id_invalid')
  if (collector && !COLLECTOR_HOST_RE.test(id.host)) problems.push('host_not_collector_name')
  return { mode: off ? 'off' : collector ? 'collector' : 'reporter', host: id.host, host_id_source: id.source, problems }
}

if (require.main === module) {
  if (process.argv[2] !== 'diagnose') {
    process.stderr.write('usage: collector-session.js diagnose\n')
    process.exit(2)
  }
  const d = diagnose()
  process.stdout.write(`${JSON.stringify(d)}\n`)
  process.exit(d.mode === 'collector' && d.problems.length ? 1 : 0)
}

module.exports = {
  collectorToken,
  hostIdentity,
  eventMap,
  sideReason,
  identity,
  runIdentity,
  clientBind,
  transition,
  resolve,
  recordEnd,
  endGaps,
  loadEpochs,
  sessionDir,
  diagnose,
  EXTRA_EVENTS,
  EPOCH_LOCK_MS,
}
