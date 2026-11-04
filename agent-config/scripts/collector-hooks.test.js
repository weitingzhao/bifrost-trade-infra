#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/collector-hooks.test.js
// The hooks in collector mode, as real processes against a local fake
// platform (R5:5.5-12 S1-4 test list): lifecycles, lock contention, the end
// protocol, the 5-second exit, the host id, no title, credentials by purpose.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const h = require('./collector-test-harness.js')
const { endGaps } = require('./collector-session.js')

const HB = path.join(h.HERE, 'thread-heartbeat.js')
const S = '00000000-0000-4000-8000-00000000c001'

async function session(tag, respond) {
  const home = h.tmpHome(tag)
  const srv = await h.fakeServer(respond)
  const hook = async (event, { pid = 41001, sid = S, extra = {}, env = {} } = {}) => {
    const r = await h.runHook(HB, 'claude', h.claudePayload(event, sid, extra), h.collectorEnv(home, srv.url, { CLAUDE_PID: pid, ...env }))
    assert.equal(r.code, 0, r.err)
    assert.equal(r.out, '', 'a hook prints nothing')
    await h.settle(srv, home, srv.got.length)
    return r
  }
  return { home, srv, hook, epochs: (sid = S) => h.readEpochs(home, 'claude', sid) }
}

test('startup, prompt, failed turn, end: the collector contract on the wire', async () => {
  const t = await session('life')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('UserPromptSubmit', { extra: { prompt: 'x' } })
    await t.hook('StopFailure', { extra: { error: 'authentication_failed' } })
    await t.hook('SessionEnd', { extra: { reason: 'other' } })
    assert.deepEqual(h.beats(t.srv), [['session_start', 'startup', S, 1], ['turn_start', '', S, 1], ['turn_end', '', S, 1], ['turn_end', '', S, 1]])
    for (const r of t.srv.got) {
      assert.equal(r.auth, `Bearer ${h.COLLECTOR}`)
      assert.equal(r.body.host, 'h1')
      assert.equal(r.body.host_id_source, 'env')
      assert.deepEqual(r.body.client_bind && [r.body.client_bind.state, r.body.client_bind.reason], ['unlinked', 'no_context'])
      for (const local of ['identity', '_end', 'tool_use_id']) assert.equal(local in r.body, false, `${local} is local: ${r.raw}`)
    }
    h.noTitle(t.srv)
    const st = t.epochs()
    assert.equal(st.max, 1)
    assert.ok(st.epochs[0].end.acked_at, 'the end is acked once the server answered')
    assert.deepEqual(endGaps(st), [])
  } finally {
    t.srv.close()
  }
})

test('two resumes in the same second get two epochs; each process keeps its own', async () => {
  const t = await session('resume2')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionEnd', { extra: { reason: 'other' } })
    const env = pid => h.collectorEnv(t.home, t.srv.url, { CLAUDE_PID: pid })
    const both = await Promise.all([41002, 41003].map(pid => h.runHook(HB, 'claude', h.claudePayload('SessionStart', S, { source: 'resume' }), env(pid))))
    assert.deepEqual(both.map(r => r.code), [0, 0])
    await h.settle(t.srv, t.home, 4)
    await t.hook('UserPromptSubmit', { pid: 41002 })
    await t.hook('UserPromptSubmit', { pid: 41003 })
    const got = h.beats(t.srv)
    assert.deepEqual(got.slice(2, 4).map(b => b[3]).sort(), [2, 3])
    const st = t.epochs()
    assert.equal(st.max, 3)
    const of = pid => st.epochs.find(e => e.pid === pid).epoch
    assert.deepEqual(got.slice(4), [['turn_start', '', S, of(41002)], ['turn_start', '', S, of(41003)]])
  } finally {
    t.srv.close()
  }
})

test('a duplicate SessionStart, a compact and PreCompact keep the epoch', async () => {
  const t = await session('dup')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('PreCompact', { extra: { trigger: 'manual', custom_instructions: null } })
    await t.hook('SessionStart', { extra: { source: 'compact' } })
    assert.deepEqual(h.beats(t.srv), [['session_start', 'startup', S, 1], ['session_start', 'startup', S, 1], ['precompact', 'manual', S, 1], ['session_start', 'compact', S, 1]])
    assert.equal(t.epochs().epochs.length, 1)
  } finally {
    t.srv.close()
  }
})

test('a late SessionEnd across a resume is dropped and counted; the resumed one ends', async () => {
  const t = await session('late')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    const before = t.srv.got.length
    await t.hook('SessionEnd', { pid: 41001, extra: { reason: 'other' } })
    assert.equal(t.srv.got.length, before, 'the old process end is not sent')
    await t.hook('SessionEnd', { pid: 41002, extra: { reason: 'prompt_input_exit' } })
    assert.deepEqual(h.beats(t.srv).slice(-1), [['turn_end', '', S, 2]])
    const st = t.epochs()
    assert.equal(st.dropped_ends, 1)
    assert.equal(st.epochs[0].late_end.reason, 'other')
  } finally {
    t.srv.close()
  }
})

test('Start lost: the first event opens epoch 1 with a gap; the late start adopts it', async () => {
  const t = await session('lost')
  try {
    await t.hook('UserPromptSubmit')
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    assert.deepEqual(h.beats(t.srv), [['turn_start', '', S, 1], ['session_start', 'startup', S, 1]])
    assert.deepEqual(t.epochs().gaps.map(g => g.kind), ['start_lost'])
  } finally {
    t.srv.close()
  }
})

test('fork opens epoch 1 of a new session; a stray InstructionsLoaded opens nothing (§12 D2, D5)', async () => {
  const t = await session('fork')
  try {
    const orphan = '00000000-0000-4000-8000-00000000dead'
    await t.hook('InstructionsLoaded', { sid: orphan, extra: { load_reason: 'session_start', memory_type: 'Project', file_path: '<home>/.claude/CLAUDE.md' } })
    assert.equal(t.srv.got.length, 0)
    assert.equal(fs.existsSync(path.dirname(h.epochsFile(t.home, 'claude', orphan))), false)
    await t.hook('SessionStart', { extra: { source: 'fork' } })
    assert.deepEqual(h.beats(t.srv), [['session_start', 'fork', S, 1]])
  } finally {
    t.srv.close()
  }
})

test('nested under the run wrapper: run-thread transport, raw session, its own epoch, no title', async () => {
  const home = h.tmpHome('nested')
  const srv = await h.fakeServer()
  try {
    const child = path.join(home, 'child.js')
    fs.writeFileSync(child, `
const { spawnSync } = require('node:child_process')
for (const [ev, extra] of [['SessionStart', { source: 'startup' }], ['UserPromptSubmit', {}], ['SessionEnd', { reason: 'other' }]]) {
  const r = spawnSync(process.execPath, [${JSON.stringify(HB)}, 'hook', 'claude'], { input: JSON.stringify({ session_id: ${JSON.stringify(S)}, hook_event_name: ev, ...extra }), env: { ...process.env, CLAUDE_PID: '42001' } })
  if (r.status !== 0 || String(r.stdout)) process.exit(9)
  spawnSync('/bin/sleep', ['0.4'])
}
`)
    const env = h.collectorEnv(home, srv.url, { BIFROST_HEARTBEAT_TITLE: 'W-54 nightly', CLAUDE_CODE_HOST_SESSION_ID: 'local_parent' })
    const r = await h.runNode([HB, 'run', 'claude', '--', process.execPath, child], { env })
    assert.equal(r.code, 0, r.err)
    await h.settle(srv, home, 5)
    const rows = srv.got.map(x => [x.body.thread.startsWith('run-'), x.body.event, x.body.session || '', x.body.epoch || 0])
    assert.deepEqual(rows, [[true, 'turn_start', '', 0], [true, 'session_start', S, 1], [true, 'turn_start', S, 1], [true, 'turn_end', S, 1], [true, 'turn_end', '', 0]])
    assert.equal(new Set(srv.got.map(x => x.body.thread)).size, 1, 'one transport thread')
    assert.deepEqual(srv.got[0].body.client_bind.reason, 'no_vendor_session')
    assert.ok(srv.got.every(x => x.body.sidebar === 'local_parent'), '§12 D6: a nested session reports the sidebar it inherited')
    h.noTitle(srv)
  } finally {
    srv.close()
  }
})

test('lock contention: a held epoch lock costs at most its cap, and the beat still goes', async () => {
  const t = await session('lock')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    const release = await h.holdLock(path.join(path.dirname(h.epochsFile(t.home, 'claude', S)), 'epochs.lock'))
    try {
      const known = await t.hook('UserPromptSubmit')
      assert.ok(known.ms >= 1800 && known.ms < 4500, `waited ${known.ms} ms`)
      const fresh = await t.hook('UserPromptSubmit', { pid: 41009 })
      assert.ok(fresh.ms < 4500)
    } finally {
      release()
    }
    const got = t.srv.got.slice(1).map(x => [x.body.event, x.body.session || '', x.body.epoch || 0, x.body.client_bind && x.body.client_bind.reason])
    assert.deepEqual(got, [['turn_start', S, 1, 'no_context'], ['turn_start', '', 0, 'identity_fallback']],
      'a known epoch is read without the lock; an unknown one is not guessed')
    assert.equal(t.epochs().max, 1, 'nothing was allocated without the lock')
  } finally {
    t.srv.close()
  }
})

test('the end intent is persisted; a refused or lost answer is a gap; a resume sends it again', async () => {
  let mode = 'ok'
  const t = await session('end', rec => (rec.body.event === 'turn_end' && mode !== 'ok' ? (mode === 'hang' ? 'hang' : { status: 503, body: { error: 'down' } }) : null))
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('UserPromptSubmit')
    mode = 'refuse'
    await t.hook('SessionEnd', { extra: { reason: 'other' } })
    let e = t.epochs().epochs[0]
    assert.ok(e.end.intent_at && e.end.failed_at && !e.end.acked_at)
    assert.equal(e.end.why, '503')
    assert.deepEqual(t.epochs().gaps.map(g => g.kind), ['end_unacked'])
    mode = 'ok'
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    assert.deepEqual(h.beats(t.srv).slice(-2), [['turn_end', '', S, 1], ['session_start', 'resume', S, 2]], 'the unacked end goes first')
    e = t.epochs().epochs[0]
    assert.ok(e.end.acked_at && e.end.replayed_at)
    // The answer never comes: the intent stays without an ack until the sender gives up.
    mode = 'hang'
    await h.runHook(HB, 'claude', h.claudePayload('SessionEnd', S, { reason: 'other' }), h.collectorEnv(t.home, t.srv.url, { CLAUDE_PID: 41002 }))
    assert.ok(await h.waitFor(() => t.srv.got.length === 6))
    assert.deepEqual(endGaps(t.epochs()), [{ epoch: 2, kind: 'end_unacked' }])
    assert.ok(await h.waitFor(() => Boolean(t.epochs().epochs[1].end.failed_at), 9000), 'the detached sender records its timeout')
  } finally {
    t.srv.close()
  }
})

test('both locks held and the server silent: the hook still exits 0 within 5 seconds', async () => {
  const t = await session('deadline', () => 'hang')
  const dir = path.dirname(h.epochsFile(t.home, 'claude', S))
  const releases = [await h.holdLock(path.join(dir, 'epochs.lock')), await h.holdLock(path.join(t.home, '.cache', 'bifrost', 'thread-keys', 'claude', `${S}.lock`))]
  try {
    for (const event of ['SessionStart', 'SessionEnd']) {
      const r = await h.runHook(HB, 'claude', h.claudePayload(event, S, { source: 'startup', reason: 'other' }), h.collectorEnv(t.home, t.srv.url, { CLAUDE_PID: 41001 }))
      assert.deepEqual([r.code, r.out], [0, ''])
      assert.ok(r.ms < 5500, `${event} took ${r.ms} ms`)
    }
    for (const release of releases) release()
    const r = await h.runHook(HB, 'claude', h.claudePayload('SessionStart', S, { source: 'startup' }), h.collectorEnv(t.home, t.srv.url, { CLAUDE_PID: 41001 }))
    assert.ok(r.ms < 5500, `a server that never answers: ${r.ms} ms`)
  } finally {
    for (const release of releases) release()
    t.srv.close()
  }
})

test('a missing host id is diagnosed on the beat; the OS short name is the fallback', async () => {
  const home = h.tmpHome('nohost')
  const srv = await h.fakeServer()
  try {
    const env = h.collectorEnv(home, srv.url, { BIFROST_HOST_ID: undefined, NODE_OPTIONS: `--require ${h.preloadPath()}` })
    delete env.BIFROST_HOST_ID
    await h.runHook(HB, 'claude', h.claudePayload('SessionStart', S, { source: 'startup' }), env)
    assert.deepEqual([srv.got[0].body.host, srv.got[0].body.host_id_source], ['TestHost', 'hostname'])
    fs.mkdirSync(path.join(home, '.config', 'bifrost'), { recursive: true })
    fs.writeFileSync(path.join(home, '.config', 'bifrost', 'host-id'), 'mini-01\n')
    await h.runHook(HB, 'claude', h.claudePayload('UserPromptSubmit', S), env)
    assert.deepEqual([srv.got[1].body.host, srv.got[1].body.host_id_source], ['mini-01', 'file'])
  } finally {
    srv.close()
  }
})

test('collector mode never sends a title; reporter mode still does (positive control)', async () => {
  const home = h.tmpHome('title')
  fs.mkdirSync(path.join(home, '.cache', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(home, '.cache', 'bifrost', 'lineage-titles.json'), JSON.stringify({ [S]: { custom: 'W-31 secret plan' }, 'codex-1': { custom: 'x' } }))
  fs.mkdirSync(path.join(home, '.codex'), { recursive: true })
  fs.writeFileSync(path.join(home, '.codex', 'session_index.jsonl'), `${JSON.stringify({ id: 'codex-1', thread_name: 'W-54 codex' })}\n`)
  const srv = await h.fakeServer()
  try {
    const send = (vendor, payload, env) => h.runHook(HB, vendor, payload, env)
    const collector = h.collectorEnv(home, srv.url, { BIFROST_HEARTBEAT_TITLE: 'W-7 env title', CLAUDE_PID: 41001 })
    for (const event of ['SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd']) await send('claude', h.claudePayload(event, S, { source: 'startup' }), collector)
    await send('codex', { session_id: 'codex-1', hook_event_name: 'UserPromptSubmit' }, collector)
    await send('cursor', { conversation_id: 'cur-1', hook_event_name: 'sessionStart' }, collector)
    await h.runNode([HB, 'run', 'cursor', '--', process.execPath, '-e', '0'], { env: collector })
    await h.settle(srv, home, 8)
    assert.equal(srv.got.length, 8)
    h.noTitle(srv)
    assert.ok(srv.got.every(r => r.body.work === undefined), 'no work number is read from a title either')
    const reporter = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER })
    const n = srv.got.length
    await send('claude', h.claudePayload('UserPromptSubmit', S), reporter)
    await h.settle(srv, home, n + 1)
    assert.equal(srv.got[n].body.title, 'W-31 secret plan')
  } finally {
    srv.close()
  }
})

test('credentials by purpose: heartbeats use the collector token, progress keeps the reporter one', async () => {
  const home = h.tmpHome('tokens')
  const srv = await h.fakeServer()
  try {
    const doc = path.join(home, 'status.json')
    fs.writeFileSync(doc, '{"v":1}')
    const both = h.collectorEnv(home, srv.url)
    await h.runHook(HB, 'claude', h.claudePayload('SessionStart', S, { source: 'startup' }), { ...both, CLAUDE_PID: '41001' })
    await h.runNode([path.join(h.HERE, 'progress-publish.js'), doc], { env: both })
    await h.runNode([path.join(h.HERE, 'host-heartbeat.js')], { env: both })
    assert.deepEqual(srv.got.map(r => [r.method, r.url, r.auth]), [
      ['POST', '/api/v1/agent/threads/heartbeat', `Bearer ${h.COLLECTOR}`],
      ['PUT', '/api/v1/agent/progress', `Bearer ${h.REPORTER}`],
      ['POST', '/api/v1/agent/hosts/heartbeat', `Bearer ${h.COLLECTOR}`],
    ])
    assert.equal(srv.got[2].body.host, 'h1')
    assert.ok(Object.values(srv.got[2].body.vendors).every(v => v.token === true))
    const collectorOnly = { ...both }
    delete collectorOnly.PLATFORM_REPORTER_TOKEN
    await h.runNode([path.join(h.HERE, 'progress-publish.js'), doc], { env: collectorOnly })
    assert.equal(srv.got.length, 3, 'a collector token never publishes progress')
  } finally {
    srv.close()
  }
})

test('BIFROST_HEARTBEAT=off in collector mode sends nothing and keeps no epochs', async () => {
  const t = await session('off')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' }, env: { BIFROST_HEARTBEAT: 'off' } })
    await t.hook('SessionEnd', { extra: { reason: 'other' }, env: { BIFROST_HEARTBEAT: 'off' } })
    assert.equal(t.srv.got.length, 0)
    assert.equal(t.epochs(), null)
  } finally {
    t.srv.close()
  }
})

// Review round 1 (Codex, S1-4): each test below failed on 21d277b.

test('M1: a SessionEnd under a held epoch lock is not sent; the next resume sends it and records the ack', async () => {
  const t = await session('m1')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    const release = await h.holdLock(path.join(path.dirname(h.epochsFile(t.home, 'claude', S)), 'epochs.lock'))
    try {
      const r = await t.hook('SessionEnd', { extra: { reason: 'other' } })
      assert.ok(r.ms < 4500, `${r.ms} ms`)
    } finally {
      release()
    }
    assert.deepEqual(h.beats(t.srv), [['session_start', 'startup', S, 1]], 'no end goes out without its intent')
    assert.equal(t.epochs().epochs[0].end, undefined)
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    assert.deepEqual(h.beats(t.srv).slice(1), [['turn_end', '', S, 1], ['session_start', 'resume', S, 2]])
    const e = t.epochs().epochs[0]
    assert.ok(e.end.intent_at && e.end.acked_at, 'the kept end has its intent and now its ack')
    assert.ok(t.epochs().gaps.some(g => g.kind === 'end_deferred'))
  } finally {
    t.srv.close()
  }
})

test('M1: a SessionEnd whose state directory cannot be written is not sent', async () => {
  const t = await session('m1ro')
  const dir = path.dirname(h.epochsFile(t.home, 'claude', S))
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    fs.chmodSync(dir, 0o500)
    await t.hook('SessionEnd', { extra: { reason: 'other' } })
    assert.deepEqual(h.beats(t.srv), [['session_start', 'startup', S, 1]])
  } finally {
    fs.chmodSync(dir, 0o700)
    t.srv.close()
  }
})

test('M2: a SessionEnd without a usable CLAUDE_PID after a resume is not sent; the resumed process ends', async () => {
  const t = await session('m2')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    await t.hook('SessionEnd', { pid: '', extra: { reason: 'other' } })
    await t.hook('SessionEnd', { pid: 'not-a-pid', extra: { reason: 'other' } })
    assert.equal(h.beats(t.srv).length, 2, 'neither end is sent')
    assert.equal(t.epochs().epochs[1].end, undefined)
    await t.hook('SessionEnd', { pid: 41002, extra: { reason: 'other' } })
    assert.deepEqual(h.beats(t.srv).slice(-1), [['turn_end', '', S, 2]])
    assert.deepEqual(t.epochs().gaps.filter(g => g.kind === 'end_unresolved').length, 2)
  } finally {
    t.srv.close()
  }
})

test('M3: an end refused at the end and again at the first resume is sent at the second resume', async () => {
  let refuse = true
  const t = await session('m3', rec => (rec.body.event === 'turn_end' && refuse ? { status: 503, body: { error: 'down' } } : null))
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionEnd', { extra: { reason: 'other' } })
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    assert.ok(!t.epochs().epochs[0].end.acked_at)
    refuse = false
    await t.hook('SessionStart', { pid: 41003, extra: { source: 'resume' } })
    assert.deepEqual(h.beats(t.srv).slice(-2), [['turn_end', '', S, 1], ['session_start', 'resume', S, 3]])
    assert.ok(t.epochs().epochs[0].end.acked_at)
  } finally {
    t.srv.close()
  }
})

test('M4: an older process repeating its resume start leaves the newer epoch and its end alone', async () => {
  const t = await session('m4')
  try {
    await t.hook('SessionStart', { extra: { source: 'startup' } })
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    await t.hook('SessionStart', { pid: 41003, extra: { source: 'resume' } })
    await t.hook('SessionStart', { pid: 41002, extra: { source: 'resume' } })
    assert.deepEqual(h.beats(t.srv).slice(-1), [['session_start', 'resume', S, 2]])
    assert.equal(t.epochs().max, 3)
    await t.hook('SessionEnd', { pid: 41003, extra: { reason: 'other' } })
    assert.deepEqual(h.beats(t.srv).slice(-1), [['turn_end', '', S, 3]], 'the newer process still ends')
  } finally {
    t.srv.close()
  }
})
