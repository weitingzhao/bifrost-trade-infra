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
 *   claude SessionEnd          —                turn_end, under the end protocol
 *   claude InstructionsLoaded  —                — (never allocates an epoch, §12 D5)
 *   cursor (as before) + sessionStart          session_start (reason its source if the platform
 *                                               knows it, else startup: unverified, §4.2)
 *   cursor sessionEnd          turn_end         not sent: no process id tells its epoch, so it
 *                                               closes none (gap end_unresolved, review M2)
 *   codex  (as before)                         unchanged (Codex rows are unsupported, §2.5)
 *
 * Collector beats carry `session` (the vendor's raw session id, never the
 * transport thread id), `epoch`, `client_bind` and `host_id_source`, and never
 * a `title` (C10). The host is the host id. The token is the collector token.
 *
 * Epochs and the end protocol (§2.3) are in collector-epochs.js: process
 * identity by CLAUDE_PID (§12 D1), one epoch per process and session, an
 * end sent only with its intent persisted, retried at later resumes.
 *
 * Not here (S1-5): registering external work (the single writer is
 * register-claude-work.py) and appending to the launcher's launch.json. Until
 * then a session with whole launcher context sends no client_bind.
 *
 *   node collector-session.js diagnose    mode, host id and its source, problems (no secrets)
 */
const fs = require('node:fs')
const os = require('node:os')
const epochs = require('./collector-epochs.js')

const { home, ID_RE } = epochs

// The platform's shapes (agentthreads hostRe; actuation collectorName).
const HOST_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/
const COLLECTOR_HOST_RE = /^[a-z0-9-]{1,32}$/
const START_SOURCES = new Set(['startup', 'resume', 'clear', 'compact', 'fork'])
const COMPACT_TRIGGERS = new Set(['manual', 'auto'])
const EPOCH_LOCK_MS = 2000

// Collector mode adds these to each vendor's reporter-mode table.
const EXTRA_EVENTS = {
  claude: { SessionStart: 'session_start', PreCompact: 'precompact', SessionEnd: 'turn_end', StopFailure: 'turn_end' },
  cursor: { sessionStart: 'session_start' },
  codex: {},
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
  transition: epochs.transition,
  resolve: epochs.resolve,
  recordEnd: epochs.recordEnd,
  endGaps: epochs.endGaps,
  loadEpochs: epochs.loadEpochs,
  sessionDir: epochs.sessionDir,
  MAX_REPLAY_ATTEMPTS: epochs.MAX_REPLAY_ATTEMPTS,
  diagnose,
  EXTRA_EVENTS,
  EPOCH_LOCK_MS,
}
