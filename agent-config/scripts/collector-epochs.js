'use strict'
/**
 * Epochs and the end protocol of collector mode (R5:5.5-12 S1-4, design §2.3
 * as corrected by §12 and by review round 1). Used only through
 * collector-session.js, and only when a collector token is configured.
 *
 * State: `~/.cache/bifrost/external-work/<vendor>/<session>/epochs.json`,
 * changed only under the flock `epochs.lock` beside it.
 *
 * Process identity: CLAUDE_PID (§12 D1); 0 when absent or not a number, and
 * always 0 for Cursor and Codex. One process has one epoch per session:
 * - SessionStart of a process that already has an epoch reuses it, whether
 *   that epoch is open, or ended or superseded within REPEAT_WINDOW_MS; it
 *   never opens one and never supersedes a newer one (review M4). After that
 *   window a closed epoch's pid is one the system reused for a new process.
 * - resume from a new process opens max+1 and supersedes the open epochs;
 *   startup / clear / fork from a new process opens one and supersedes
 *   nothing; compact keeps the epoch.
 * - Another event from a process never seen opens its epoch (the gap
 *   `start_lost`) and supersedes nothing.
 * - Without a process id, events use the current epoch (`current_fallback`).
 *
 * End protocol:
 * - A SessionEnd is sent only with its intent persisted on its epoch first.
 *   Without the lock it is not sent: it is kept in a `pending-end.*.json`
 *   file and folded in at the next lock, as an end the server has not acked
 *   (gap `end_deferred`). An unwritable directory keeps nothing and sends
 *   nothing (review M1).
 * - An end that cannot be told to its process (no process id, or a process
 *   the session has never seen) closes nothing: gap `end_unresolved`
 *   (review M2). A session whose only event is its end opens and ends 1.
 * - An end that resolves to an ended or superseded epoch is dropped and counted.
 * - The answer is `acked_at`, or `failed_at` with the gap `end_unacked`;
 *   an answer that cannot take the lock is kept the same way and folded in.
 * - A resume sends an unacked end again before its own beat: at most
 *   REPLAYS_PER_HOOK per hook, at most MAX_REPLAY_ATTEMPTS in all. Only an
 *   ack ends the retries; an attempt is counted when it is picked (review M3).
 */
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

// The platform's shapes (agentthreads idRe).
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/
const VENDOR_RE = /^[a-z][a-z0-9-]{0,31}$/
const START_HOOKS = new Set(['SessionStart', 'sessionStart'])
const END_HOOKS = new Set(['SessionEnd', 'sessionEnd'])
const KEEP_EPOCHS = 32
const KEEP_GAPS = 50
const REPLAYS_PER_HOOK = 2
const MAX_REPLAY_ATTEMPTS = 5
const PENDING_RE = /^pending-end\.[0-9]+\.[0-9a-f]{16}\.json$/
const REPEAT_WINDOW_MS = 60 * 1000

function home(...p) {
  return path.join(process.env.BIFROST_HOME_OVERRIDE || os.homedir(), ...p)
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

function writeAtomic(file, value) {
  const tmp = `${file}.${process.pid}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(value), { mode: 0o600 })
  fs.renameSync(tmp, file)
}

function saveEpochs(file, st) {
  st.epochs = st.epochs.slice(-KEEP_EPOCHS)
  st.gaps = st.gaps.slice(-KEEP_GAPS)
  writeAtomic(file, st)
}

function isOpen(e) {
  return !e.end && !e.superseded_at
}

function latest(list) {
  let best = null
  for (const e of list) if (!best || e.epoch > best.epoch) best = e
  return best
}

/** Unacked ends to send again, oldest first; each pick is one attempt. */
function pickReplays(st, at) {
  const out = []
  for (const e of st.epochs) {
    if (out.length >= REPLAYS_PER_HOOK) break
    if (!e.end || e.end.acked_at || count(e.end.replay_attempts) >= MAX_REPLAY_ATTEMPTS) continue
    e.end.replay_attempts = count(e.end.replay_attempts) + 1
    e.end.replayed_at = at
    out.push({ epoch: e.epoch, thread: e.end.thread || e.thread || '' })
  }
  return out
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
  const open = (identity, source, supersede) => {
    for (const e of supersede ? st.epochs : []) {
      if (!isOpen(e)) continue
      e.superseded_at = at
      gap('end_missing', e.epoch)
    }
    st.max += 1
    st.epochs.push({ epoch: st.max, pid: ev.pid, ppid: ev.ppid, source, opened_by: ev.name, opened_at: at, thread: ev.thread })
    if (identity === 'first_event') gap('start_lost', st.max)
    return { epoch: st.max, identity, replay: [] }
  }
  if (ev.kind === 'start' && ev.source !== 'compact') {
    // A repeat is the same process: its epoch still open, or opened moments ago. An old,
    // closed epoch under the same pid is a pid the system reused for a new process.
    if (byPid && (isOpen(byPid) || now - Date.parse(byPid.opened_at) < REPEAT_WINDOW_MS)) {
      // A SessionStart after this process's first event adopts its epoch; a repeat is a repeat.
      if (!START_HOOKS.has(byPid.opened_by)) Object.assign(byPid, { opened_by: ev.name, source: ev.source, adopted_at: at })
      return { epoch: byPid.epoch, identity: 'pid', replay: [] }
    }
    if (ev.source === 'resume') {
      const replay = pickReplays(st, at)
      const r = open('start', 'resume', true)
      r.replay = replay
      return r
    }
    if (!current || ev.pid > 0) return open('start', ev.source, false)
    return { epoch: current.epoch, identity: 'current_fallback', replay: [] }
  }
  if (ev.kind === 'end') {
    let e = byPid
    let identity = 'pid'
    if (!e && !current) {
      identity = open('first_event', '', false).identity
      e = latest(st.epochs)
    } else if (!e) {
      st.dropped_ends += 1
      gap('end_unresolved', current.epoch)
      return { drop: true, why: 'end_unresolved' }
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
  if (ev.pid > 0 || !current) return open('first_event', '', false)
  return { epoch: current.epoch, identity: 'current_fallback', replay: [] }
}

/** Without the lock: only an epoch this process already has, for a beat that is not an end. */
function resolveReadOnly(st, ev) {
  const byPid = ev.pid > 0 ? latest(st.epochs.filter(e => e.pid === ev.pid)) : null
  return byPid ? { epoch: byPid.epoch, identity: 'pid', replay: [] } : null
}

/** Fold the ends kept without the lock: each as an end the server has not acked. Caller holds the lock. */
function foldPending(st, dir) {
  let names = []
  try {
    names = fs.readdirSync(dir).filter(n => PENDING_RE.test(n)).sort()
  } catch {
    return []
  }
  const folded = []
  for (const name of names) {
    const file = path.join(dir, name)
    let ev = null
    try {
      ev = JSON.parse(fs.readFileSync(file, 'utf8'))
    } catch {
      ev = null
    }
    folded.push(file)
    if (ev && ev.kind === 'answer' && ev.at) {
      applyAnswer(st, ev.epoch, ev, ev.at)
      continue
    }
    if (!ev || ev.kind !== 'end' || !ev.at) continue
    let r
    try {
      r = transition(st, ev, new Date(ev.at))
    } catch {
      // a kept end that cannot be folded is dropped, so it cannot block the session's lock
      st.gaps.push({ kind: 'end_unfolded', epoch: 0, at: new Date().toISOString() })
      continue
    }
    if (!r.end) continue
    const e = st.epochs.find(x => x.epoch === r.epoch)
    Object.assign(e.end, { failed_at: ev.at, why: 'lock_busy' })
    st.gaps.push({ kind: 'end_deferred', epoch: e.epoch, at: ev.at })
  }
  return folded
}

function withEpochs(vendor, session, deps, fn) {
  const dir = sessionDir(vendor, session)
  if (!dir) throw new Error('no epoch directory')
  const file = path.join(dir, 'epochs.json')
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  return deps.withLock(path.join(dir, 'epochs.lock'), () => {
    const st = loadEpochs(file)
    const folded = foldPending(st, dir)
    const out = fn(st)
    saveEpochs(file, st)
    for (const f of folded) {
      try {
        fs.unlinkSync(f)
      } catch {
        // already folded by another holder of the lock
      }
    }
    return out
  })
}

/** Keep a record that could not take the lock in a file of its own; false when even that cannot be written. */
function deferRecord(dir, pid, record, now) {
  try {
    const name = `pending-end.${pid}.${crypto.randomBytes(8).toString('hex')}.json`
    writeAtomic(path.join(dir, name), { ...record, at: now.toISOString() })
    return true
  } catch {
    return false
  }
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

/**
 * Give a collector beat its epoch. Mutates body.identity and, for a session
 * end, sets body._end. Returns { drop } or { replay: [beats] }.
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
    if (ev.kind === 'end') {
      // No end goes out without its intent (review M1): keep it, or keep nothing and send nothing.
      return { drop: true, why: deferRecord(sessionDir(vendor, id.session), ev.pid, ev, now) ? 'end_deferred' : 'end_unrecorded' }
    }
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
function applyAnswer(st, epoch, res, at) {
  const e = st.epochs.find(x => x.epoch === epoch)
  if (!e || !e.end) return false
  if (res && res.sent) {
    e.end.acked_at = at
    delete e.end.failed_at
    delete e.end.why
    return true
  }
  e.end.failed_at = at
  e.end.why = String((res && (res.status || res.why)) || 'not sent').slice(0, 80)
  st.gaps.push({ kind: 'end_unacked', epoch: e.epoch, at })
  return false
}

/**
 * Record the server's answer to an end beat: acked, or failed with the gap
 * end_unacked. Without the lock the answer is kept beside the epochs and
 * folded in at the next lock, so an ack is not lost to a busy lock.
 */
function recordEnd(end, res, deps) {
  if (!end || !count(end.epoch)) return false
  const now = (deps.now ? deps.now() : new Date()).toISOString()
  try {
    return withEpochs(end.vendor, end.session, deps, st => applyAnswer(st, end.epoch, res, now))
  } catch {
    const answer = { kind: 'answer', epoch: end.epoch, sent: Boolean(res && res.sent), status: (res && res.status) || 0, why: (res && res.why) || '' }
    deferRecord(sessionDir(end.vendor, end.session), 0, answer, new Date(now))
    return false
  }
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

module.exports = {
  home,
  ID_RE,
  VENDOR_RE,
  sessionDir,
  loadEpochs,
  transition,
  resolve,
  recordEnd,
  endGaps,
  MAX_REPLAY_ATTEMPTS,
  REPLAYS_PER_HOOK,
}
