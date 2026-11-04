#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/collector-session.test.js
// Unit tests of collector-session.js: epochs (design §2.3 as corrected by
// §12 D1, D2, D5), the client's diagnosis, the host id, the event table.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const h = require('./collector-test-harness.js')

const HOME = h.tmpHome('unit')
process.env.BIFROST_HOME_OVERRIDE = HOME
for (const k of ['PLATFORM_COLLECTOR_TOKEN', 'BIFROST_HOST_ID', 'BIFROST_PLAN_ROOT', 'BIFROST_PLAN_NODE', 'BIFROST_WORK_DESCRIPTION', 'CLAUDE_PID']) delete process.env[k]
const c = require('./collector-session.js')
const { EVENTS } = require('./thread-heartbeat.js')

const T0 = new Date('2026-11-04T06:00:00.000Z')
const fresh = () => c.loadEpochs(path.join(HOME, 'does-not-exist.json'))
const ev = (name, extra = {}) => ({
  name,
  kind: /^[Ss]essionStart$/.test(name) ? 'start' : /^[Ss]essionEnd$/.test(name) ? 'end' : 'other',
  source: '',
  reason: '',
  pid: 0,
  ppid: 1,
  thread: 'S',
  ...extra,
})
const start = (source, pid) => ev('SessionStart', { source, pid })
const end = (pid, reason = 'other') => ev('SessionEnd', { pid, reason })

test('startup opens epoch 1; the same SessionStart again reuses it (duplicate)', () => {
  const st = fresh()
  assert.deepEqual(c.transition(st, start('startup', 7), T0), { epoch: 1, identity: 'start', replay: [] })
  assert.equal(c.transition(st, start('startup', 7), T0).epoch, 1)
  assert.equal(st.max, 1)
  assert.equal(st.epochs.length, 1)
})

test('fork and clear open epoch 1 of their new session (§12 D2)', () => {
  for (const source of ['fork', 'clear']) {
    const st = fresh()
    assert.equal(c.transition(st, start(source, 7), T0).epoch, 1)
    assert.equal(st.epochs[0].source, source)
  }
})

test('resume opens max+1, supersedes the open epoch and records it as left without an end', () => {
  const st = fresh()
  c.transition(st, start('startup', 7), T0)
  const r = c.transition(st, start('resume', 8), T0)
  assert.equal(r.epoch, 2)
  assert.ok(st.epochs[0].superseded_at)
  assert.deepEqual(c.endGaps(st), [{ epoch: 1, kind: 'end_missing' }])
  assert.equal(c.transition(st, start('resume', 8), T0).epoch, 2, 'a duplicate resume of the same process reuses its epoch')
})

test('two resumes of one session from two processes get two epochs', () => {
  const st = fresh()
  c.transition(st, start('startup', 7), T0)
  c.transition(st, end(7), T0)
  assert.equal(c.transition(st, start('resume', 8), T0).epoch, 2)
  assert.equal(c.transition(st, start('resume', 9), T0).epoch, 3)
  assert.equal(c.transition(st, ev('UserPromptSubmit', { pid: 8 }), T0).epoch, 2, 'each process keeps its own epoch')
  assert.equal(c.transition(st, ev('UserPromptSubmit', { pid: 9 }), T0).epoch, 3)
})

test('compact keeps the epoch; so do PreCompact and the other events of the process', () => {
  const st = fresh()
  c.transition(st, start('startup', 7), T0)
  assert.deepEqual(c.transition(st, start('compact', 7), T0), { epoch: 1, identity: 'pid', replay: [] })
  assert.equal(c.transition(st, ev('PreCompact', { pid: 7 }), T0).epoch, 1)
  assert.equal(st.max, 1)
})

test('a late SessionEnd across a resume is dropped and counted', () => {
  const st = fresh()
  c.transition(st, start('startup', 7), T0)
  c.transition(st, start('resume', 8), T0)
  assert.deepEqual(c.transition(st, end(7), T0), { drop: true, why: 'late_end', epoch: 1 })
  assert.equal(st.dropped_ends, 1)
  assert.equal(st.epochs[0].late_end.reason, 'other', 'the late end is kept for the audit')
  const r = c.transition(st, end(8), T0)
  assert.deepEqual([r.epoch, r.end], [2, true])
  assert.deepEqual(c.transition(st, end(8), T0), { drop: true, why: 'late_end', epoch: 2 }, 'a second end of an ended epoch is dropped')
  assert.equal(st.dropped_ends, 2)
})

test('a SessionEnd of a process the session has never seen is not executed: a gap', () => {
  const st = fresh()
  c.transition(st, start('startup', 7), T0)
  assert.deepEqual(c.transition(st, end(99), T0), { drop: true, why: 'end_unresolved' })
  assert.deepEqual(st.gaps.map(g => g.kind), ['end_unresolved'])
  assert.equal(st.epochs[0].end, undefined)
})

test('Start lost: the first wired event opens the epoch; a late SessionStart adopts it', () => {
  const st = fresh()
  assert.deepEqual(c.transition(st, ev('UserPromptSubmit', { pid: 7 }), T0), { epoch: 1, identity: 'first_event', replay: [] })
  assert.deepEqual(st.gaps.map(g => g.kind), ['start_lost'])
  assert.deepEqual(c.transition(st, start('startup', 7), T0), { epoch: 1, identity: 'pid', replay: [] })
  assert.equal(st.epochs[0].opened_by, 'SessionStart')
  assert.equal(st.max, 1)
  // A resumed process whose SessionStart is lost opens the next epoch.
  c.transition(st, end(7), T0)
  assert.equal(c.transition(st, ev('Stop', { pid: 8 }), T0).epoch, 2)
  assert.equal(c.transition(st, start('resume', 8), T0).epoch, 2, 'its late resume start adopts that epoch')
})

test('a session whose only event is its end opens and ends epoch 1', () => {
  const st = fresh()
  const r = c.transition(st, end(7), T0)
  assert.deepEqual([r.epoch, r.end, r.identity], [1, true, 'first_event'])
})

test('without a process id (Cursor, Codex) the current epoch is used and said to be a fallback', () => {
  const st = fresh()
  assert.equal(c.transition(st, start('startup', 0), T0).epoch, 1)
  assert.deepEqual(c.transition(st, ev('beforeSubmitPrompt'), T0), { epoch: 1, identity: 'current_fallback', replay: [] })
  assert.equal(c.transition(st, start('startup', 0), T0).epoch, 1, 'a repeated start of the same session id is a duplicate')
  const r = c.transition(st, ev('sessionEnd'), T0)
  assert.deepEqual([r.epoch, r.end, r.identity], [1, true, 'current_fallback'])
  assert.equal(c.transition(st, ev('sessionEnd'), T0).drop, true)
})

test('a resume sends again, first, the earlier ends the server never acked', () => {
  const st = fresh()
  c.transition(st, ev('SessionStart', { source: 'startup', pid: 7, thread: 'T1' }), T0)
  c.transition(st, ev('SessionEnd', { pid: 7, thread: 'T1' }), T0)
  const r = c.transition(st, start('resume', 8), T0)
  assert.deepEqual(r.replay, [{ epoch: 1, thread: 'T1' }])
  assert.ok(st.epochs[0].end.replayed_at)
  c.transition(st, end(8), T0)
  assert.deepEqual(c.transition(st, start('resume', 9), T0).replay, [{ epoch: 2, thread: 'S' }], 'a replayed end is not sent a third time')
})

test('the epoch counter never goes back, even when old epochs are pruned', () => {
  const file = path.join(HOME, 'prune', 'epochs.json')
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify({ max: 40, epochs: [] }))
  const st = c.loadEpochs(file)
  assert.equal(c.transition(st, start('resume', 3), T0).epoch, 41)
  fs.writeFileSync(file, '{not json')
  assert.equal(c.loadEpochs(file).max, 0, 'an unreadable file is a session never seen')
})

test('client_bind: closed reasons from the environment, nothing when context is whole', () => {
  const at = T0.toISOString()
  const desc = path.join(HOME, 'desc.json')
  fs.writeFileSync(desc, '{}')
  assert.deepEqual(c.clientBind('', {}, at), { state: 'unlinked', reason: 'no_vendor_session', at })
  assert.deepEqual(c.clientBind('s', {}, at), { state: 'unlinked', reason: 'no_context', at })
  assert.deepEqual(c.clientBind('s', { BIFROST_PLAN_ROOT: 'R5' }, at), { state: 'refused', reason: 'no_context', at })
  assert.deepEqual(c.clientBind('s', { BIFROST_PLAN_ROOT: 'R5', BIFROST_PLAN_NODE: 'R5:1' }, at), { state: 'refused', reason: 'no_description', at })
  assert.deepEqual(c.clientBind('s', { BIFROST_PLAN_ROOT: 'R5', BIFROST_PLAN_NODE: 'R5:1', BIFROST_WORK_DESCRIPTION: path.join(HOME, 'none') }, at).reason, 'no_description')
  assert.equal(c.clientBind('s', { BIFROST_PLAN_ROOT: 'R5', BIFROST_PLAN_NODE: 'R5:1', BIFROST_WORK_DESCRIPTION: desc }, at), null)
})

test('identity: the raw vendor session id, never the transport thread id', () => {
  process.env.BIFROST_HEARTBEAT_THREAD = 'run-abc'
  try {
    const id = c.identity('claude', { session_id: 'sess-1' }, {}, T0)
    assert.deepEqual(id, { session: 'sess-1', client_bind: { state: 'unlinked', reason: 'no_context', at: T0.toISOString() }, host_id_source: 'hostname' })
    assert.equal(c.identity('claude', { session_id: 'bad id!' }, {}, T0).session, undefined, 'a session the platform would refuse is left out')
    assert.equal(c.identity('cursor', { conversation_id: 'conv-1' }, {}, T0).session, 'conv-1')
  } finally {
    delete process.env.BIFROST_HEARTBEAT_THREAD
  }
})

test('host id: env overrides file; the OS short name is the last resort and is said so', () => {
  const file = path.join(HOME, '.config', 'bifrost', 'host-id')
  assert.equal(c.hostIdentity().source, 'hostname')
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, 'mini-01\nignored\n')
  assert.deepEqual(c.hostIdentity(), { host: 'mini-01', source: 'file', invalid: false })
  process.env.BIFROST_HOST_ID = 'mac-02'
  assert.deepEqual(c.hostIdentity(), { host: 'mac-02', source: 'env', invalid: false })
  process.env.BIFROST_HOST_ID = 'no spaces allowed'
  assert.deepEqual(c.hostIdentity(), { host: 'mini-01', source: 'file', invalid: true })
  delete process.env.BIFROST_HOST_ID
  fs.unlinkSync(file)
})

test('the event table: collector mode adds the session events to the reporter table only', () => {
  assert.deepEqual(c.eventMap('claude', EVENTS), { ...EVENTS.claude, SessionStart: 'session_start', PreCompact: 'precompact', SessionEnd: 'turn_end', StopFailure: 'turn_end' })
  assert.deepEqual(c.eventMap('cursor', EVENTS), { ...EVENTS.cursor, sessionStart: 'session_start' })
  assert.deepEqual(c.eventMap('codex', EVENTS), EVENTS.codex)
  assert.equal(c.eventMap('other', EVENTS), null)
  assert.equal(c.eventMap('claude', EVENTS).InstructionsLoaded, undefined, '§12 D5: InstructionsLoaded never reaches the epochs')
  assert.equal(c.sideReason('claude', 'session_start', { source: 'fork' }), 'fork')
  assert.equal(c.sideReason('claude', 'session_start', { source: 'later' }), null, 'a source the platform refuses is not sent')
  assert.equal(c.sideReason('claude', 'session_start', {}), null)
  assert.equal(c.sideReason('cursor', 'session_start', {}), 'startup')
  assert.equal(c.sideReason('cursor', 'session_start', { source: 'new_chat' }), 'startup', 'an unverified Cursor source is a start')
  assert.equal(c.sideReason('claude', 'precompact', { trigger: 'manual' }), 'manual')
  assert.equal(c.sideReason('claude', 'precompact', { trigger: 'x' }), null)
  assert.equal(c.sideReason('claude', 'turn_end', {}), '')
})

test('diagnose: a collector without a host id is a problem; no token is printed', async () => {
  const home = h.tmpHome('diag')
  const script = path.join(h.HERE, 'collector-session.js')
  // The preload fixes the OS host name (TestHost), which is not a collector name.
  const run = env => h.runNode([script, 'diagnose'], { env: h.cleanEnv(home, 'http://127.0.0.1:9', { NODE_OPTIONS: `--require ${h.preloadPath()}`, ...env }) })
  let r = await run({ PLATFORM_COLLECTOR_TOKEN: 'secret-collector' })
  assert.equal(r.code, 1)
  assert.equal(r.out.includes('secret-collector'), false)
  assert.deepEqual(JSON.parse(r.out), { mode: 'collector', host: 'TestHost', host_id_source: 'hostname', problems: ['host_id_missing', 'host_not_collector_name'] })
  r = await run({ PLATFORM_COLLECTOR_TOKEN: 'secret-collector', BIFROST_HOST_ID: 'mini-01' })
  assert.deepEqual([r.code, JSON.parse(r.out).problems, JSON.parse(r.out).host_id_source], [0, [], 'env'])
  r = await run({ PLATFORM_COLLECTOR_TOKEN: 'x', BIFROST_HOST_ID: 'Mini_01' })
  assert.deepEqual([r.code, JSON.parse(r.out).problems], [1, ['host_not_collector_name']])
  r = await run({})
  assert.deepEqual([r.code, JSON.parse(r.out).mode], [0, 'reporter'])
  r = await run({ BIFROST_HEARTBEAT: 'off', PLATFORM_COLLECTOR_TOKEN: 'x' })
  assert.equal(JSON.parse(r.out).mode, 'off')
})
