'use strict'
/**
 * Launched and bound sessions in collector mode (R5:5.5-12 S1-5, design §2.2
 * to §2.4, §13 I4 and I6). Used only through collector-session.js, and only
 * when a collector token is configured.
 *
 * A launch is the record dispatch-claude.py writes before it becomes the CLI
 * (`~/.cache/bifrost/external-work/launches/<id>/launch.json`, BIFROST_LAUNCH_ID).
 * A hook belongs to that launch only when its CLAUDE_PID is the record's
 * cli_pid: a session started inside the launched one inherits the whole
 * environment, plan context and sidebar included, and is not the launch's.
 *
 * For the launch's own process, each epoch the hooks open is appended to the
 * record's `sessions`, and for a linked launch the work's single writer
 * (register-claude-work.py event) is started, detached, per event:
 * SessionStart → start; every epoch a resume superseded gets its cancel kept
 * (terminal.json), whichever process resumed and whether or not its work
 * exists yet, so a late start of it registers nothing; an existing work is
 * cancelled by the writer;
 * UserPromptSubmit, Stop and StopFailure → heartbeat each time, other events
 * → heartbeat at most once in TOOL_BEAT_MS, SessionEnd → submit. A session
 * bound after the fact (`register-claude-work.py bind`) has a work directory,
 * and its later events start the writer the same way.
 *
 * client_bind (§3.1; the reasons are the platform's closed set):
 * - the work is registered: linked; its registration was refused: refused /
 *   register_failed;
 * - a linked launch's own session whose registration has not arrived yet:
 *   none is sent. This is "waiting for registration" (§13 I6); the platform has
 *   no reason for it yet, so the client says it only locally (collector-audit.js);
 * - whole plan context in the environment but not the launch's own process
 *   (a nested session) or no launch at all: unlinked / no_context.
 */
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const epochs = require('./collector-epochs.js')

const LAUNCH_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const TOOL_BEAT_MS = 30 * 1000
const EACH_TIME = new Set(['UserPromptSubmit', 'Stop', 'StopFailure'])
const WRITER = path.resolve(__dirname, '..', '..', 'scripts', 'agent-host', 'register-claude-work.py')

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

function launchOf(env) {
  const id = String(env.BIFROST_LAUNCH_ID || '').trim()
  if (!LAUNCH_RE.test(id)) return null
  const dir = epochs.home('.cache', 'bifrost', 'external-work', 'launches', id)
  const launch = readJSON(path.join(dir, 'launch.json'))
  return launch && launch.launch_id === id ? { id, dir, launch } : null
}

function owns(found, pid) {
  return Boolean(found) && pid > 0 && found.launch.cli_pid === pid
}

function workDir(vendor, session, epoch) {
  const dir = epochs.sessionDir(vendor, session)
  return dir && Number.isInteger(epoch) && epoch > 0 ? path.join(dir, String(epoch)) : ''
}

function workState(vendor, session, epoch) {
  const dir = workDir(vendor, session, epoch)
  return dir ? readJSON(path.join(dir, 'state.json')) : null
}

function contextWhole(env) {
  const description = String(env.BIFROST_WORK_DESCRIPTION || '').trim()
  let readable = false
  try {
    readable = Boolean(description) && fs.statSync(description).isFile()
  } catch {
    readable = false
  }
  return Boolean(String(env.BIFROST_PLAN_ROOT || '').trim() && String(env.BIFROST_PLAN_NODE || '').trim() && readable)
}

/** Append one (vendor, session, epoch) to the launch's sessions, once, under the launch's lock. */
function noteSession(found, entry, deps) {
  deps.withLock(path.join(found.dir, 'launch.lock'), () => {
    const file = path.join(found.dir, 'launch.json')
    const rec = readJSON(file)
    if (!rec || !Array.isArray(rec.sessions)) return
    if (rec.sessions.some(s => s.vendor === entry.vendor && s.session === entry.session && s.epoch === entry.epoch)) return
    rec.sessions.push(entry)
    const tmp = `${file}.${process.pid}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(rec), { mode: 0o600 })
    fs.renameSync(tmp, file)
  })
}

/** The client's diagnosis, undefined for "send none", or 'keep' to leave the one already made. */
function bindFor(owned, linkedLaunch, whole, state, at) {
  if (state && state.id) return { state: 'linked', at }
  if (state && state.failed) return { state: 'refused', reason: 'register_failed', at }
  if (whole && owned && linkedLaunch) return undefined
  if (whole) return { state: 'unlinked', reason: 'no_context', at }
  return 'keep'
}

function writerEvents(r) {
  if (r.end) return [['submit', r.epoch]]
  if (r.kind === 'start') return [...r.superseded.map(e => ['cancel', e]), ['start', r.epoch]]
  if (EACH_TIME.has(r.name)) return [['heartbeat', r.epoch]]
  return [['heartbeat', r.epoch, 'tool']]
}

/**
 * Keep a work's end or cancel before the writer starts: the writer may never run
 * (no python3, a busy lock, a failed read), and the next call for the work, bind
 * included, delivers what is kept. The first one kept stands; the writer
 * (collector_work.note_terminal) writes the same file the same way.
 */
function noteTerminal(dir, event) {
  const target = path.join(dir, 'terminal.json')
  try {
    if (fs.existsSync(target)) return
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
    const tmp = path.join(dir, `.terminal.json.${process.pid}.tmp`)
    fs.writeFileSync(tmp, JSON.stringify({ event, at: new Date().toISOString() }), { mode: 0o600 })
    try {
      fs.linkSync(tmp, target)
    } catch {
      // another writer kept one first
    }
    fs.unlinkSync(tmp)
  } catch {
    // not kept: the audit reports the end as not delivered
  }
}

/** Tool events start the writer at most once in TOOL_BEAT_MS per epoch (§2.3). */
function toolThrottled(dir, now) {
  const file = path.join(dir, 'hook-beat')
  try {
    if (now - fs.statSync(file).mtimeMs < TOOL_BEAT_MS) return true
  } catch {
    // never beaten yet
  }
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
    fs.writeFileSync(file, '')
    fs.utimesSync(file, new Date(now), new Date(now))
  } catch {
    // a lost mark is one more heartbeat
  }
  return false
}

function spawnWriter(args, env) {
  try {
    const child = spawn('python3', [WRITER, 'event', ...args], { detached: true, stdio: 'ignore', env })
    child.on('error', () => {})
    child.unref()
  } catch {
    // no python3: the work stays unregistered and the audit shows it
  }
}

/** After a collector beat has its epoch: the launch's sessions, client_bind, and the writer. */
function afterResolve(vendor, payload, body, r, deps, env, url) {
  const id = body.identity
  if (vendor !== 'claude' || !r || r.drop || !r.epoch || !id || !id.session) return
  const session = id.session
  const found = launchOf(env)
  const owned = owns(found, r.pid)
  const linkedLaunch = owned && found.launch.mode === 'linked'
  const whole = contextWhole(env)
  const at = (deps.now ? deps.now() : new Date()).toISOString()
  if (owned && (r.opened || r.kind === 'start')) {
    try {
      noteSession(found, { vendor, session, epoch: r.epoch, at }, deps)
    } catch {
      // not recorded: the audit counts this launch's sessions from the record
    }
  }
  const state = workState(vendor, session, r.epoch)
  const bind = bindFor(owned, linkedLaunch, whole, state, at)
  if (bind !== 'keep') {
    if (bind) id.client_bind = bind
    else delete id.client_bind
  }
  const writes = (linkedLaunch && whole) || Boolean(state)
  if (linkedLaunch && whole) {
    // The work directory exists from this hook on, before any writer runs: a resume from any
    // process, launched or not, then finds it and keeps its cancel (review M3).
    try {
      fs.mkdirSync(workDir(vendor, session, r.epoch), { recursive: true, mode: 0o700 })
    } catch {
      // the writer creates it too
    }
  }
  const now = Date.parse(at)
  for (const [event, epoch, tool] of writerEvents(r)) {
    const dir = workDir(vendor, session, epoch)
    if (!dir) continue
    if (event === 'cancel') {
      // Every superseded epoch gets its cancel kept, whoever superseded it and whether or not its
      // work exists yet: a start writer that comes later registers nothing (review R2-M2). A
      // writer runs only for a work that exists.
      noteTerminal(dir, 'cancel')
      if (!workState(vendor, session, epoch)) continue
    } else if (!writes) continue
    if (tool && toolThrottled(dir, now)) continue
    if (event === 'submit') noteTerminal(dir, event)
    const args = ['--event', event, '--vendor', vendor, '--session', session, '--epoch', String(epoch), '--url', url]
    if (linkedLaunch && event !== 'cancel') args.push('--launch', found.id)
    spawnWriter(args, env)
  }
}

module.exports = { afterResolve, launchOf, owns, bindFor, writerEvents, workState, WRITER, TOOL_BEAT_MS }
