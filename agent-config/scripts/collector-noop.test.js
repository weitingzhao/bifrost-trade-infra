#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/collector-noop.test.js
//
// No-op equivalence (R5:5.5-12 S1-4): with no collector token configured, the
// requests the hook scripts send are byte for byte the ones the scripts of the
// baseline commit send, for every source-capability fixture and the extra
// events below. This is the safety net for "every session runs the new hook
// code at once". The baseline scripts come from git; without the commit the
// test fails, it does not skip.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const h = require('./collector-test-harness.js')

const BASELINE = '4508170' // the commit this slice is based on
const SCRIPTS = ['thread-heartbeat.js', 'host-heartbeat.js', 'progress-publish.js']
const PRELOAD = h.preloadPath()

function baselineDir() {
  const dir = h.tmpHome('baseline')
  for (const name of SCRIPTS) {
    // The mutation check runs this file from a copy; it names the repository to read from.
    const repo = process.env.COLLECTOR_BASELINE_REPO || h.HERE
    const r = spawnSync('git', ['-C', repo, 'show', `${BASELINE}:agent-config/scripts/${name}`], { encoding: 'utf8' })
    assert.equal(r.status, 0, `git show ${BASELINE}:${name} failed (fetch the baseline commit): ${r.stderr}`)
    fs.writeFileSync(path.join(dir, name), r.stdout)
  }
  return dir
}

const VARIANTS = { baseline: baselineDir(), current: h.HERE }

function sequenceEvents(file) {
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l))
  const pids = { P1: '41001', P2: '41002', P3: '41003' }
  return lines.slice(1).map(l => {
    const payload = h.claudePayload(l.hook.replace(/-compound$/, ''), l.session_id)
    for (const k of ['source', 'reason', 'trigger', 'notification_type', 'error']) if (l[k] != null) payload[k] = l[k]
    return { vendor: 'claude', payload, env: { CLAUDE_PID: l.parent_comm === 'claude' ? pids[l.ppid] : pids.P1 } }
  })
}

function hookFixtureEvents() {
  const dir = path.join(h.FIXTURES, 'claude-2.1.302', 'hooks')
  return fs.readdirSync(dir).sort().map(name => {
    const { payload } = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'))
    return { vendor: 'claude', payload, env: { CLAUDE_PID: '41001' } }
  })
}

const SID = '00000000-0000-4000-8000-0000000000aa'
const CUR = '00000000-0000-4000-8000-0000000000bb'
function extraEvents() {
  const c = (ev, extra) => ({ vendor: 'claude', payload: h.claudePayload(ev, SID, extra), env: { CLAUDE_PID: '41001', CLAUDE_CODE_HOST_SESSION_ID: 'local_sidebar1' } })
  const u = (ev, extra) => ({ vendor: 'cursor', payload: { conversation_id: CUR, session_id: CUR, hook_event_name: ev, ...extra }, env: {} })
  return [
    c('SessionStart', { source: 'startup' }),
    c('UserPromptSubmit', { prompt: 'x' }),
    c('PreToolUse', { tool_name: 'Bash', tool_use_id: 'toolu_1', tool_input: { command: 'sleep 1', timeout: 600000 } }),
    c('PostToolUse', { tool_name: 'Bash', tool_use_id: 'toolu_1' }),
    c('PreToolUse', { tool_name: 'Read', tool_use_id: 'toolu_2' }),
    c('PostToolUse', { tool_name: 'Read', tool_use_id: 'toolu_2' }),
    c('Notification', { notification_type: 'permission_prompt' }),
    c('SubagentStop', { subagent_type: 'explore' }),
    c('PreCompact', { trigger: 'auto' }),
    c('StopFailure', { error: 'rate_limit' }),
    c('Stop', { stop_hook_active: false }),
    c('SessionEnd', { reason: 'other' }),
    u('sessionStart', {}),
    u('beforeSubmitPrompt', {}),
    u('preToolUse', { tool_name: 'Shell', tool_input: { timeout: 30000 } }),
    u('stop', { status: 'completed' }),
    u('sessionEnd', { reason: 'completed' }),
    { vendor: 'codex', payload: { session_id: 'codex-1', hook_event_name: 'UserPromptSubmit' }, env: {} },
    { vendor: 'codex', payload: { session_id: 'codex-1', hook_event_name: 'SessionStart', source: 'startup' }, env: {} },
    { vendor: 'codex', payload: { session_id: 'codex-1', hook_event_name: 'Stop' }, env: {} },
  ]
}

function seedHome(home) {
  fs.mkdirSync(path.join(home, '.cache', 'bifrost'), { recursive: true })
  // Reporter mode reads titles; collector mode must not (checked elsewhere).
  fs.writeFileSync(path.join(home, '.cache', 'bifrost', 'lineage-titles.json'), JSON.stringify({ [SID]: { custom: 'W-31 decisions' } }))
  fs.mkdirSync(path.join(home, '.codex'), { recursive: true })
  fs.writeFileSync(path.join(home, '.codex', 'session_index.jsonl'), `${JSON.stringify({ id: 'codex-1', thread_name: 'W-54 heartbeat' })}\n`)
  // A host id on disk changes nothing without a collector token.
  fs.mkdirSync(path.join(home, '.config', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(home, '.config', 'bifrost', 'host-id'), 'h1\n')
}

// The real server issues a key on a registration; later beats present it.
const respond = rec => (rec.body && rec.body.thread_key ? { status: 202, body: { ok: true } } : null)

async function runEvents(variant, name, events, extraEnv = {}) {
  const dir = VARIANTS[variant]
  const home = h.tmpHome(`noop-${variant}`)
  seedHome(home)
  const srv = await h.fakeServer(respond)
  try {
    for (const [i, ev] of events.entries()) {
      const env = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER, BIFROST_HOST_ID: 'h1', NODE_OPTIONS: `--require ${PRELOAD}`, COLLECTOR_TEST_SEED: `${name}:${i}`, ...extraEnv, ...ev.env })
      const r = await h.runHook(path.join(dir, 'thread-heartbeat.js'), ev.vendor, ev.payload, env)
      assert.equal(r.code, 0)
      assert.equal(r.out, '')
      await h.settle(srv, home, srv.got.length, 200)
    }
    return srv.got.map(({ method, url, auth, type, raw }) => ({ method, url, auth, type, raw }))
  } finally {
    srv.close()
  }
}

async function equivalent(name, events, extraEnv) {
  const before = await runEvents('baseline', name, events, extraEnv)
  const after = await runEvents('current', name, events, extraEnv)
  assert.ok(before.length > 0 || events.every(e => e.vendor === 'claude'), `${name}: the baseline sent nothing`)
  assert.deepEqual(after, before, `${name}: reporter-mode requests differ from the baseline`)
  return before.length
}

test('every Claude hook sequence fixture sends what the baseline sends', async () => {
  const dir = path.join(h.FIXTURES, 'claude-2.1.302', 'sequences')
  let total = 0
  for (const name of fs.readdirSync(dir).sort()) total += await equivalent(name, sequenceEvents(path.join(dir, name)))
  assert.ok(total > 0, 'the sequences sent no request at all: the comparison would prove nothing')
})

test('every Claude hook fixture, one after another, sends what the baseline sends', async () => {
  assert.ok((await equivalent('hooks', hookFixtureEvents())) > 0)
})

test('tool, wait, compaction, failure, cursor and codex events send what the baseline sends', async () => {
  assert.ok((await equivalent('extra', extraEvents())) >= 10)
})

test('a collector token that is empty or blank is no collector token', async () => {
  assert.ok((await equivalent('blank-token', extraEvents().slice(0, 4), { PLATFORM_COLLECTOR_TOKEN: '  ' })) > 0)
})

async function runWrapper(variant) {
  const home = h.tmpHome(`noop-run-${variant}`)
  const srv = await h.fakeServer(respond)
  try {
    const env = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER, NODE_OPTIONS: `--require ${PRELOAD}`, COLLECTOR_TEST_SEED: 'run' })
    const r = await h.runNode([path.join(VARIANTS[variant], 'thread-heartbeat.js'), 'run', 'claude', '--', process.execPath, '-e', 'process.exit(3)'], { env })
    assert.equal(r.code, 3)
    await h.settle(srv, home, 2)
    return srv.got.map(({ method, url, auth, raw }) => ({ method, url, auth, raw }))
  } finally {
    srv.close()
  }
}

test('the run wrapper sends what the baseline sends', async () => {
  const before = await runWrapper('baseline')
  assert.equal(before.length, 2)
  assert.deepEqual(await runWrapper('current'), before)
})

async function progress(variant) {
  const home = h.tmpHome(`noop-progress-${variant}`)
  const srv = await h.fakeServer()
  try {
    const doc = path.join(home, 'status.json')
    fs.writeFileSync(doc, JSON.stringify({ v: 1, lanes: [] }))
    const env = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER, NODE_OPTIONS: `--require ${PRELOAD}` })
    const r = await h.runNode([path.join(VARIANTS[variant], 'progress-publish.js'), doc], { env })
    assert.equal(r.code, 0)
    return srv.got.map(({ method, url, auth, raw }) => ({ method, url, auth, raw }))
  } finally {
    srv.close()
  }
}

test('progress-publish sends what the baseline sends', async () => {
  const before = await progress('baseline')
  assert.equal(before.length, 1)
  assert.deepEqual(await progress('current'), before)
})

async function hostBeat(variant) {
  const home = h.tmpHome(`noop-host-${variant}`)
  const ws = path.join(home, 'ws')
  fs.mkdirSync(path.join(ws, '.claude'), { recursive: true })
  fs.mkdirSync(path.join(ws, '.cursor'), { recursive: true })
  fs.symlinkSync(VARIANTS[variant], path.join(ws, 'scripts'))
  fs.copyFileSync(path.join(h.HERE, '..', 'claude', 'settings.json'), path.join(ws, '.claude', 'settings.json'))
  fs.copyFileSync(path.join(h.HERE, '..', 'cursor', 'hooks.json'), path.join(ws, '.cursor', 'hooks.json'))
  seedHome(home)
  const srv = await h.fakeServer()
  try {
    const env = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER, BIFROST_WORKSPACE: ws, CODEX_HOME: path.join(home, '.codex'), NODE_OPTIONS: `--require ${PRELOAD}` })
    const r = await h.runNode([path.join(VARIANTS[variant], 'host-heartbeat.js')], { env })
    assert.equal(r.code, 0)
    return srv.got.map(({ method, url, auth, raw }) => ({ method, url, auth, raw }))
  } finally {
    srv.close()
  }
}

test('the host heartbeat sends what the baseline sends', async () => {
  const before = await hostBeat('baseline')
  assert.equal(before.length, 1)
  assert.match(before[0].raw, /"wired":true/)
  assert.deepEqual(await hostBeat('current'), before)
})
