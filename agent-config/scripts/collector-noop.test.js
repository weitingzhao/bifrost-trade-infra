#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/collector-noop.test.js
//
// No-op equivalence (R5:5.5-12 S1-4): with no collector token configured, the
// hook scripts are compared with the scripts of the baseline commit, for every
// source-capability fixture and the extra events and credential cases below.
// What is compared, and nothing more: the requests (method, path, credential,
// content type, body bytes), the files left in the home directory (time
// fields normalized), exit code 0 and empty stdout and stderr. Timing is not
// equal: the events newly wired into settings start one more node process;
// for those only an upper bound is checked. Every request goes to a local
// fake server that answers 202, so the platform's own state machine is not
// part of this comparison. The baseline scripts come from git; without the
// commit the test fails, it does not skip.
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

// Every file under the home directory, with time fields normalized. The test's own markers are not the scripts'.
function homeFiles(home) {
  const out = {}
  const walk = rel => {
    for (const e of fs.readdirSync(path.join(home, rel), { withFileTypes: true })) {
      const name = path.join(rel, e.name)
      if (name === '.marks') continue
      if (e.isDirectory()) walk(name)
      else {
        let text = '<unreadable>'
        try {
          text = fs.readFileSync(path.join(home, name), 'utf8').replace(/"at":\d+/g, '"at":0')
        } catch {
          // a mode-000 credential file stays as it was set up
        }
        out[name] = text
      }
    }
  }
  walk('')
  return out
}

// Hook events this slice wires that the baseline never saw: no request, no file, so a bound on time is checked.
const NEW_EVENTS = new Set(['SessionStart', 'PreCompact', 'SessionEnd', 'StopFailure', 'sessionStart'])

async function runEvents(variant, name, events, extraEnv = {}, setup = seedHome) {
  const dir = VARIANTS[variant]
  const home = h.tmpHome(`noop-${variant}`)
  setup(home)
  const srv = await h.fakeServer(respond)
  try {
    for (const [i, ev] of events.entries()) {
      const env = h.cleanEnv(home, srv.url, { PLATFORM_REPORTER_TOKEN: h.REPORTER, BIFROST_HOST_ID: 'h1', NODE_OPTIONS: `--require ${PRELOAD}`, COLLECTOR_TEST_SEED: `${name}:${i}`, ...extraEnv, ...ev.env })
      const r = await h.runHook(path.join(dir, 'thread-heartbeat.js'), ev.vendor, ev.payload, env)
      assert.deepEqual([r.code, r.out, r.err], [0, '', ''], `${variant} ${name}:${i}`)
      if (variant === 'current' && NEW_EVENTS.has(ev.payload.hook_event_name)) assert.ok(r.ms < 2000, `${name}:${i} took ${r.ms} ms`)
      await h.settle(srv, home, srv.got.length, 200)
    }
    return { requests: srv.got.map(({ method, url, auth, type, raw }) => ({ method, url, auth, type, raw })), files: homeFiles(home) }
  } finally {
    srv.close()
  }
}

async function equivalent(name, events, extraEnv, setup) {
  const before = await runEvents('baseline', name, events, extraEnv, setup)
  const after = await runEvents('current', name, events, extraEnv, setup)
  assert.ok(before.requests.length > 0 || events.every(e => e.vendor === 'claude'), `${name}: the baseline sent nothing`)
  assert.deepEqual(after.requests, before.requests, `${name}: reporter-mode requests differ from the baseline`)
  assert.deepEqual(after.files, before.files, `${name}: reporter-mode files differ from the baseline`)
  assert.ok(Object.keys(before.files).some(f => f.includes('thread-keys')) || before.requests.length === 0, `${name}: no state file was compared`)
  return before.requests.length
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

test('credential files: a reporter token on disk, and a collector token file that is blank or unreadable', async () => {
  const onDisk = home => {
    seedHome(home)
    fs.writeFileSync(path.join(home, '.config', 'bifrost', 'lineage-reporter.token'), `${h.REPORTER}\n`)
  }
  const collectorFile = (contents, mode) => home => {
    onDisk(home)
    const file = path.join(home, '.config', 'bifrost', 'collector.token')
    fs.writeFileSync(file, contents)
    fs.chmodSync(file, mode)
  }
  const noEnv = { PLATFORM_REPORTER_TOKEN: undefined }
  const events = extraEvents().slice(0, 6)
  assert.ok((await equivalent('reporter-file', events, noEnv, onDisk)) > 0)
  assert.ok((await equivalent('collector-blank', events, noEnv, collectorFile(' \n\n', 0o600))) > 0)
  assert.ok((await equivalent('collector-unreadable', events, noEnv, collectorFile('collector-x\n', 0o000))) > 0)
  assert.equal(await equivalent('no-token', events, noEnv, seedHome), 0, 'no token: neither version sends anything')
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
  fs.symlinkSync(VARIANTS[variant], path.join(ws, 'scripts'))
  fs.copyFileSync(path.join(h.HERE, '..', 'claude', 'settings.json'), path.join(ws, '.claude', 'settings.json'))
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
