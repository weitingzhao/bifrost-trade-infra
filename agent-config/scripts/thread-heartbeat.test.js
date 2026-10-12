#!/usr/bin/env node
'use strict'
// node agent-config/scripts/thread-heartbeat.test.js — exits non-zero on failure.
// Payload shapes are the ones Cursor 2026.10.01 and Claude Code 2.1.295 sent
// headless on 2026-10-10 (W-54 probe), trimmed.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { performance } = require('node:perf_hooks')

const SCRIPT = path.join(__dirname, 'thread-heartbeat.js')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-'))
process.env.BIFROST_HOME_OVERRIDE = tmp
// Explicitly opt isolated test processes into sub-second progress intervals.
process.env.NODE_ENV = 'test'
process.env.BIFROST_HEARTBEAT_TEST_FAST_BEATS = '1'
delete process.env.PLATFORM_REPORTER_TOKEN
delete process.env.BIFROST_HEARTBEAT_THREAD
delete process.env.BIFROST_HEARTBEAT_TITLE
delete process.env.BIFROST_WORK
delete process.env.BIFROST_HEARTBEAT_PROGRESS
delete process.env.BIFROST_HEARTBEAT_RUN_BEAT_MS

const { beatFor, toolTimeoutSeconds, shouldSkip, reduceThrottle, allocateStamp, loadGate, supersedeActive, saveIssuedKey, withThreadLock, armHookDeadline, clearHookDeadline, lockRuntime, startProgressBeats } = require('./thread-heartbeat.js')
const ISSUED_KEY = 'ab'.repeat(32)

const CLAUDE_ID = '7e939cd5-b3b1-4705-96e4-0a3b9e61648d'
const CURSOR_ID = '0f549e24-a80b-48a6-9799-f23e4c2926e8'
const claude = (ev, extra = {}) => ({ session_id: CLAUDE_ID, transcript_path: `/x/${CLAUDE_ID}.jsonl`, hook_event_name: ev, ...extra })
const cursor = (ev, extra = {}) => ({ conversation_id: CURSOR_ID, session_id: CURSOR_ID, hook_event_name: ev, ...extra })

function mapping() {
  // Claude: Bash declares its timeout in ms.
  const pre = beatFor('claude', claude('PreToolUse', { tool_name: 'Bash', tool_input: { command: 'sleep 2', timeout: 600000 } }))
  assert.equal(pre.event, 'before_tool')
  assert.equal(pre.thread, CLAUDE_ID)
  assert.equal(pre.tool, 'Bash')
  assert.equal(pre.tool_timeout_s, 600)
  assert.equal(beatFor('claude', claude('UserPromptSubmit', { prompt: 'x' })).event, 'turn_start')
  assert.equal(beatFor('claude', claude('PostToolUse', { tool_name: 'Bash', tool_input: { timeout: 600000 } })).tool_timeout_s, undefined)
  assert.equal(beatFor('claude', claude('Stop', { stop_hook_active: false })).event, 'turn_end')
  assert.equal(beatFor('claude', claude('Notification', { message: 'Claude is waiting for your input' })), null)
  assert.equal(beatFor('claude', claude('Notification', { notification_type: 'auth_success' })), null)
  const waiting = beatFor('claude', claude('Notification', { notification_type: 'permission_prompt' }))
  assert.deepEqual([waiting.event, waiting.reason], ['waiting_owner', 'permission_prompt'])
  assert.equal(beatFor('claude', claude('Notification', { notification_type: 'idle_prompt' })).event, 'waiting_owner')
  assert.equal(beatFor('claude', claude('Notification', { notification_type: 'elicitation' })).event, 'waiting_owner')

  // Cursor: Shell declares `timeout` in ms; headless sends sessionStart / sessionEnd.
  const cpre = beatFor('cursor', cursor('preToolUse', { tool_name: 'Shell', tool_input: { command: 'echo', cwd: '', timeout: 30000 } }))
  assert.deepEqual([cpre.event, cpre.thread, cpre.tool_timeout_s], ['before_tool', CURSOR_ID, 30])
  assert.equal(beatFor('cursor', cursor('beforeSubmitPrompt')).event, 'turn_start')
  assert.equal(beatFor('cursor', cursor('stop', { status: 'completed' })).event, 'turn_end')
  assert.equal(beatFor('cursor', cursor('sessionEnd', { reason: 'completed' })).event, 'turn_end')
  assert.equal(beatFor('cursor', cursor('subagentStop', { subagent_type: 'explore' })).tool, 'subagent:explore')
  assert.equal(beatFor('cursor', cursor('sessionStart')), null)
  assert.equal(beatFor('cursor', cursor('beforeShellExecution')), null)

  // Codex: same shape as Claude; timeout_ms.
  const x = beatFor('codex', { session_id: 'abc-1', hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: 'ls', timeout_ms: 120000 } })
  assert.deepEqual([x.event, x.tool_timeout_s], ['before_tool', 120])

  assert.equal(beatFor('other', claude('Stop')), null)
  assert.equal(beatFor('claude', { hook_event_name: 'Stop' }), null)
  assert.equal(beatFor('claude', 'not an object'), null)

  // A headless wrapper's thread wins over the session's own id.
  process.env.BIFROST_HEARTBEAT_THREAD = 'run-1'
  process.env.BIFROST_HEARTBEAT_TITLE = 'W-54 nightly check'
  const w = beatFor('cursor', cursor('postToolUse', { tool_name: 'Shell' }))
  assert.deepEqual([w.thread, w.title, w.work], ['run-1', 'W-54 nightly check', 'W-54'])
  delete process.env.BIFROST_HEARTBEAT_THREAD
  delete process.env.BIFROST_HEARTBEAT_TITLE

  // Titles: Claude from the lineage-title cache, Codex from its session index.
  fs.mkdirSync(path.join(tmp, '.cache', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(tmp, '.cache', 'bifrost', 'lineage-titles.json'), JSON.stringify({ [CLAUDE_ID]: { ai: 'Generated', custom: 'W-31 decisions' } }))
  const named = beatFor('claude', claude('Stop'))
  assert.deepEqual([named.title, named.work], ['W-31 decisions', 'W-31'])
  fs.mkdirSync(path.join(tmp, '.codex'), { recursive: true })
  fs.writeFileSync(path.join(tmp, '.codex', 'session_index.jsonl'),
    `${JSON.stringify({ id: 'abc-1', thread_name: 'old name' })}\n${JSON.stringify({ id: 'abc-1', thread_name: 'W-54 heartbeat' })}\n`)
  assert.equal(beatFor('codex', { session_id: 'abc-1', hook_event_name: 'Stop' }).title, 'W-54 heartbeat')
}

function timeouts() {
  assert.equal(toolTimeoutSeconds({ timeout: 600000 }), 600)
  assert.equal(toolTimeoutSeconds({ timeout_ms: 1500 }), 2)
  assert.equal(toolTimeoutSeconds({ block_until_ms: 30000 }), 30)
  assert.equal(toolTimeoutSeconds({ arguments: { timeout_seconds: 300 } }), 300)
  assert.equal(toolTimeoutSeconds({ command: 'ls' }), 0)
  assert.equal(toolTimeoutSeconds({ timeout: 'soon' }), 0)
  assert.equal(toolTimeoutSeconds(null), 0)
}

function throttle() {
  const t = 1_000_000
  const tool = { event: 'after_tool' }
  assert.equal(shouldSkip(tool, undefined, t), false)
  assert.equal(shouldSkip(tool, { at: t - 5000, ev: 'before_tool' }, t), true)
  assert.equal(shouldSkip(tool, { at: t - 16000, ev: 'before_tool' }, t), false)
  assert.equal(shouldSkip(tool, { at: t - 1000, ev: 'turn_end' }, t), false, 'first event after a turn end reopens the thread')
  assert.equal(shouldSkip({ event: 'before_tool', tool_timeout_s: 600 }, { at: t - 1000, ev: 'after_tool' }, t), false)
  assert.equal(shouldSkip({ event: 'turn_end' }, { at: t - 1000, ev: 'after_tool' }, t), false)
  assert.equal(shouldSkip({ event: 'turn_start' }, { at: t - 1000, ev: 'after_tool' }, t), false)
  const pending = { at: t - 1000, ev: 'before_tool', pending: { tool: 'Bash', id: 'tu-hour', timeout: 3600 } }
  const after = { event: 'after_tool', tool: 'Bash', tool_use_id: 'tu-hour' }
  assert.equal(shouldSkip(after, pending, t), false, 'the matching after-tool of a one-hour call is sent')
  const reduced = reduceThrottle(pending, after, t)
  assert.equal(reduced.skip, false)
  assert.equal(reduced.next.pending, null, 'sending the after-tool clears the declared timeout')
  assert.equal(shouldSkip({ event: 'after_tool', tool: 'Read', tool_use_id: 'other' }, pending, t), true)
}

function runScript(args, { stdin = '', env = {} } = {}) {
  return new Promise(resolve => {
    const started = Date.now()
    const p = spawn(process.execPath, [SCRIPT, ...args], { env: { ...process.env, ...env }, stdio: ['pipe', 'pipe', 'pipe'] })
    let out = ''
    let err = ''
    p.stdout.on('data', d => (out += d))
    p.stderr.on('data', d => (err += d))
    p.on('exit', code => resolve({ code, out, err, ms: Date.now() - started }))
    p.stdin.end(stdin)
  })
}

function server(status = 202, payload) {
  const got = []
  const body = payload === undefined ? { ok: true, thread_key: ISSUED_KEY } : payload
  const s = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      got.push({ url: req.url, auth: req.headers.authorization, body: JSON.parse(b || '{}') })
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(typeof body === 'string' ? body : JSON.stringify(body))
    })
  })
  return new Promise(resolve => s.listen(0, '127.0.0.1', () => resolve({ s, got, url: `http://127.0.0.1:${s.address().port}` })))
}

async function waitFor(fn, ms = 4000) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (fn()) return true
    await new Promise(r => setTimeout(r, 50))
  }
  return false
}

// A hook failure must never block a tool call: exit 0, nothing on stdout, fast.
async function neverBlocks() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-nb-'))
  const pre = JSON.stringify(cursor('preToolUse', { tool_name: 'Shell', tool_input: { timeout: 30000 } }))
  const cases = [
    { name: 'garbage stdin', stdin: '{not json', env: {} },
    { name: 'empty stdin', stdin: '', env: {} },
    { name: 'no token', stdin: pre, env: {} },
    { name: 'unreachable platform', stdin: pre, env: { PLATFORM_REPORTER_TOKEN: 't', PLATFORM_HEARTBEAT_URL: 'http://127.0.0.1:9' } },
    { name: 'home not writable', stdin: pre, env: { PLATFORM_REPORTER_TOKEN: 't', BIFROST_HOME_OVERRIDE: '/dev/null/nope', PLATFORM_HEARTBEAT_URL: 'http://127.0.0.1:9' } },
    { name: 'unknown vendor', stdin: pre, env: {}, args: ['hook', 'nobody'] },
  ]
  // Node start-up alone is the baseline; a hook that waited on the network
  // would add the 5 s hook deadline or the 5 s fetch timeout on top of it.
  const baseline = (await runScript(['--version-probe'], {})).ms
  for (const c of cases) {
    const r = await runScript(c.args || ['hook', 'cursor'], { stdin: c.stdin, env: { BIFROST_HOME_OVERRIDE: home, ...c.env } })
    assert.equal(r.code, 0, `${c.name}: exit ${r.code} ${r.err}`)
    assert.equal(r.out, '', `${c.name}: wrote to stdout`)
    assert.ok(r.ms < baseline + 1500, `${c.name}: took ${r.ms}ms (node start-up ${baseline}ms)`)
  }
  // A platform that answers 500 is the same as no platform.
  const srv = await server(500)
  const r = await runScript(['hook', 'claude'], {
    stdin: JSON.stringify(claude('PreToolUse', { tool_name: 'Bash' })),
    env: { BIFROST_HOME_OVERRIDE: home, PLATFORM_REPORTER_TOKEN: 't', PLATFORM_HEARTBEAT_URL: srv.url },
  })
  assert.deepEqual([r.code, r.out], [0, ''])
  srv.s.close()
  const bad = await server(200, 'not-json')
  const badRun = await runScript(['hook', 'claude'], {
    stdin: JSON.stringify(claude('Stop')),
    env: { BIFROST_HOME_OVERRIDE: home, PLATFORM_REPORTER_TOKEN: 't', PLATFORM_HEARTBEAT_URL: bad.url },
  })
  assert.deepEqual([badRun.code, badRun.out], [0, ''])
  bad.s.close()
}

async function endToEnd() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-e2e-'))
  const srv = await server()
  const env = { BIFROST_HOME_OVERRIDE: home, PLATFORM_REPORTER_TOKEN: 'reporter-token', PLATFORM_HEARTBEAT_URL: `${srv.url}/` }
  const r = await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('PreToolUse', { tool_name: 'Bash', tool_input: { timeout: 600000 } })), env })
  assert.deepEqual([r.code, r.out], [0, ''])
  assert.ok(await waitFor(() => srv.got.length === 1), 'first event was not posted')
  const g = srv.got[0]
  assert.equal(g.url, '/api/v1/agent/threads/heartbeat')
  assert.equal(g.auth, 'Bearer reporter-token')
  assert.deepEqual(
    [g.body.thread, g.body.vendor, g.body.event, g.body.tool, g.body.tool_timeout_s],
    [CLAUDE_ID, 'claude', 'before_tool', 'Bash', 600],
  )
  assert.equal(g.body.thread_key, undefined)
  assert.equal(g.body.seq, 1)
  assert.ok(g.body.turn_id)
  assert.ok(g.body.host)
  const keyFile = path.join(home, '.cache', 'bifrost', 'thread-keys', 'claude', CLAUDE_ID)
  assert.equal(fs.statSync(keyFile).mode & 0o777, 0o600)

  // The matching PostToolUse of a declared timeout is not throttled; the Stop is not either.
  await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('PostToolUse', { tool_name: 'Bash', tool_use_id: 'tu-bash' })), env })
  await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('Stop')), env })
  assert.ok(await waitFor(() => srv.got.length === 3), `want 3 posts, got ${srv.got.length}`)
  await new Promise(r => setTimeout(r, 300))
  assert.deepEqual(srv.got.map(x => x.body.event), ['before_tool', 'after_tool', 'turn_end'])
  assert.deepEqual(srv.got.map(x => x.body.seq), [1, 2, 3])
  assert.ok(srv.got.slice(1).every(x => x.body.thread_key === ISSUED_KEY))
  assert.equal(srv.got[1].body.tool_timeout_s, undefined)

  // A later tool call with no declared timeout still throttles its after-tool.
  srv.got.length = 0
  await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('PreToolUse', { tool_name: 'Read' })), env })
  await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('PostToolUse', { tool_name: 'Read' })), env })
  assert.ok(await waitFor(() => srv.got.length === 1), 'unscoped after-tool was not throttled')
  await new Promise(r => setTimeout(r, 300))
  assert.deepEqual(srv.got.map(x => x.body.event), ['before_tool'])

  // Headless: the wrapper reports start and end under one thread, and the
  // command sees that thread for its own hooks; its exit code passes through.
  srv.got.length = 0
  const child = `require('fs').writeFileSync(${JSON.stringify(path.join(home, 'seen'))}, process.env.BIFROST_HEARTBEAT_THREAD); process.exit(3)`
  const w = await runScript(['run', 'cursor', '--', process.execPath, '-e', child], { env: { ...env, BIFROST_WORK: 'W-54' } })
  assert.equal(w.code, 3)
  assert.deepEqual(srv.got.map(x => x.body.event), ['turn_start', 'turn_end'])
  const seen = fs.readFileSync(path.join(home, 'seen'), 'utf8')
  assert.match(seen, /^run-[0-9a-f-]{36}$/)
  assert.ok(srv.got.every(x => x.body.thread === seen && x.body.vendor === 'cursor' && x.body.work === 'W-54'))
  srv.s.close()
}

async function seqLock() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-lock-'))
  const env = { ...process.env, BIFROST_HOME_OVERRIDE: home }
  delete env.PLATFORM_REPORTER_TOKEN
  const code = `
    const { allocateStamp } = require(${JSON.stringify(SCRIPT)})
    const seqs = []
    for (let i = 0; i < 25; i++) {
      const body = { thread: 'same-thread', vendor: 'claude', host: 'h', event: 'before_tool' }
      allocateStamp(body)
      seqs.push(body.seq)
    }
    process.stdout.write(seqs.join(','))
  `
  const once = () =>
    new Promise(resolve => {
      const p = spawn(process.execPath, ['-e', code], { env })
      let out = ''
      let err = ''
      p.stdout.on('data', d => (out += d))
      p.stderr.on('data', d => (err += d))
      p.on('exit', code => resolve({ code, out, err }))
    })
  const [a, b] = await Promise.all([once(), once()])
  assert.equal(a.code, 0, a.err)
  assert.equal(b.code, 0, b.err)
  const seqs = [...a.out.split(','), ...b.out.split(',')].map(Number)
  assert.equal(seqs.length, 50)
  assert.equal(new Set(seqs).size, 50, `duplicate sequence ${seqs.join(',')}`)
  assert.equal(Math.max(...seqs), 50)
}

async function nonceAndUnknownKey() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-nonce-'))
  const got = []
  let phase = 'drop'
  const s = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      const body = JSON.parse(b || '{}')
      got.push(body)
      if (phase === 'drop') {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true }))
        return
      }
      if (phase === 'key' && !body.thread_key) {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
        return
      }
      if (body.thread_key) {
        res.writeHead(409, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'unknown key' }))
        return
      }
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, thread_key: 'cd'.repeat(32) }))
    })
  })
  await new Promise(resolve => s.listen(0, '127.0.0.1', resolve))
  const url = `http://127.0.0.1:${s.address().port}`
  const env = { BIFROST_HOME_OVERRIDE: home, PLATFORM_REPORTER_TOKEN: 't', PLATFORM_HEARTBEAT_URL: url }
  const payload = JSON.stringify(claude('PreToolUse', { tool_name: 'Bash' }))
  await runScript(['hook', 'claude'], { stdin: payload, env })
  assert.equal(got.length, 1)
  assert.equal(got[0].thread_key, undefined)
  assert.match(got[0].register_nonce, /^[0-9a-f]{64}$/)
  phase = 'key'
  await runScript(['hook', 'claude'], { stdin: payload, env })
  assert.equal(got.length, 2)
  assert.equal(got[1].register_nonce, got[0].register_nonce, 'a lost first response retries the same nonce')
  assert.equal(got[1].thread_key, undefined)
  const gateFile = path.join(home, '.cache', 'bifrost', 'thread-keys', 'claude', CLAUDE_ID)
  const saved = JSON.parse(fs.readFileSync(gateFile, 'utf8'))
  assert.equal(saved.records.find(r => r.status !== 'superseded').key, ISSUED_KEY)
  phase = 'reject'
  got.length = 0
  await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('Stop')), env })
  assert.ok(await waitFor(() => got.length >= 2), `unknown key recovery posts, got ${got.length}`)
  const rejected = got.find(b => b.thread_key === ISSUED_KEY)
  const recovered = got.find(b => b.thread !== CLAUDE_ID && !b.thread_key)
  assert.ok(rejected, 'the old key was presented once')
  assert.ok(recovered, 'a new thread id was registered without the old key')
  assert.notEqual(recovered.register_nonce, rejected.register_nonce)
  // The server records the post before the client stores the issued key.
  assert.ok(
    await waitFor(() => {
      const gate = JSON.parse(fs.readFileSync(gateFile, 'utf8'))
      const live = gate.records.find(r => r.status !== 'superseded')
      return live && live.key === 'cd'.repeat(32)
    }),
    'the new record did not keep the issued key',
  )
  const after = JSON.parse(fs.readFileSync(gateFile, 'utf8'))
  const old = after.records.find(r => r.status === 'superseded')
  const live = after.records.find(r => r.status !== 'superseded')
  assert.equal(old.key, ISSUED_KEY, 'the old key is kept and not reused')
  assert.equal(live.key, 'cd'.repeat(32))
  assert.notEqual(live.key, old.key)
  s.close()
}

async function runContinuesSequence() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-run-'))
  const prev = process.env.BIFROST_HOME_OVERRIDE
  process.env.BIFROST_HOME_OVERRIDE = home
  try {
    for (let i = 0; i < 10; i++) allocateStamp({ thread: 'run-fixed', vendor: 'cursor', host: 'h', event: 'before_tool' })
  } finally {
    process.env.BIFROST_HOME_OVERRIDE = prev
  }
  const srv = await server()
  const result = await runScript(['run', 'cursor', '--', process.execPath, '-e', 'process.exit(0)'], {
    env: {
      BIFROST_HOME_OVERRIDE: home,
      PLATFORM_REPORTER_TOKEN: 't',
      PLATFORM_HEARTBEAT_URL: srv.url,
      BIFROST_HEARTBEAT_THREAD: 'run-fixed',
    },
  })
  assert.equal(result.code, 0, result.err)
  assert.ok(await waitFor(() => srv.got.length === 2), `run posts ${srv.got.length}`)
  assert.deepEqual(
    srv.got.map(x => x.body.event),
    ['turn_start', 'turn_end'],
  )
  assert.deepEqual(
    srv.got.map(x => x.body.seq),
    [11, 12],
  )
  assert.equal(srv.got[0].body.turn_id, srv.got[1].body.turn_id)
  assert.ok(srv.got[0].body.turn_id)
  srv.s.close()
}

function lateResponseDoesNotTouchTheCurrentRecord() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-late-'))
  const prev = process.env.BIFROST_HOME_OVERRIDE
  process.env.BIFROST_HOME_OVERRIDE = home
  try {
    const body = { thread: 'same', vendor: 'claude', host: 'h', event: 'turn_start', session: 'same' }
    allocateStamp(body)
    const stale = { ...body }
    const liveBody = { ...body }
    supersedeActive(liveBody)
    assert.notEqual(liveBody.thread, stale.thread)
    assert.equal(saveIssuedKey(stale, '11'.repeat(32)), false)
    const gateFile = path.join(home, '.cache', 'bifrost', 'thread-keys', 'claude', 'same')
    const midway = JSON.parse(fs.readFileSync(gateFile, 'utf8'))
    const current = midway.records.find(r => r.status !== 'superseded')
    assert.equal(current.key, '', 'a late key was written onto the current record')
    assert.equal(midway.records.find(r => r.id === stale.thread).key, '', 'a late key revived the superseded record')
    const again = supersedeActive({ ...stale })
    assert.equal(again, null)
    const after = JSON.parse(fs.readFileSync(gateFile, 'utf8'))
    assert.equal(after.records.length, midway.records.length)
    assert.equal(after.records.find(r => r.status !== 'superseded').id, current.id)
    assert.equal(after.records.some(r => String(r.id).endsWith(':2')), false)
  } finally {
    if (prev === undefined) delete process.env.BIFROST_HOME_OVERRIDE
    else process.env.BIFROST_HOME_OVERRIDE = prev
  }
}

async function lostTurnStartThenBeforeTool() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-turn-'))
  const state = { turn: '', event: '', seq: 0, prior: new Set(), key: '' }
  let dropNextStart = false
  const s = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      const body = JSON.parse(b || '{}')
      const refuse = (error) => {
        res.writeHead(409, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error }))
      }
      if (!state.key) {
        state.key = ISSUED_KEY
        state.turn = body.turn_id
        state.event = body.event
        state.seq = body.seq
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
        return
      }
      if (body.thread_key !== state.key) return refuse('unknown key')
      if (body.turn_id !== state.turn && (state.prior.has(body.turn_id) || body.event !== 'turn_start')) {
        return refuse('older turn refused')
      }
      if (dropNextStart && body.event === 'turn_start') {
        dropNextStart = false
        res.writeHead(500, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'lost' }))
        return
      }
      if (body.seq <= state.seq) {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, ignored: true }))
        return
      }
      if (body.turn_id !== state.turn) state.prior.add(state.turn)
      state.turn = body.turn_id
      state.event = body.event
      state.seq = body.seq
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true }))
    })
  })
  await new Promise(resolve => s.listen(0, '127.0.0.1', resolve))
  const env = {
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: 't',
    PLATFORM_HEARTBEAT_URL: `http://127.0.0.1:${s.address().port}`,
  }
  const start = await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('UserPromptSubmit', { prompt: 'x' })), env })
  assert.equal(start.code, 0, start.err)
  const firstTurn = state.turn
  assert.ok(firstTurn)
  assert.equal(state.event, 'turn_start')
  dropNextStart = true
  const lost = await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('UserPromptSubmit', { prompt: 'y' })), env })
  assert.equal(lost.code, 0, lost.err)
  assert.equal(state.turn, firstTurn, 'a lost turn_start moved the server')
  const prevHome = process.env.BIFROST_HOME_OVERRIDE
  process.env.BIFROST_HOME_OVERRIDE = home
  const gate = loadGate('claude', CLAUDE_ID)
  if (prevHome === undefined) delete process.env.BIFROST_HOME_OVERRIDE
  else process.env.BIFROST_HOME_OVERRIDE = prevHome
  const rec = gate.records.find(r => r.status !== 'superseded')
  assert.equal(rec.turn_confirmed, false)
  assert.notEqual(rec.turn_id, firstTurn)
  const tool = await runScript(['hook', 'claude'], {
    stdin: JSON.stringify(claude('PreToolUse', { tool_name: 'Bash', tool_input: { timeout: 600000 } })),
    env,
  })
  assert.equal(tool.code, 0, tool.err)
  assert.equal(state.turn, rec.turn_id, 'the server did not end on the new turn')
  assert.equal(state.event, 'before_tool')
  assert.equal(state.prior.has(firstTurn), true)
  s.close()
}

async function oldKeyUnconfirmedTurnServerRecordPruned() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-pruned-'))
  const oldKey = 'ab'.repeat(32)
  const newKey = 'cd'.repeat(32)
  const threads = new Map()
  const seen = []
  let registrations = 0
  let dropNextStart = false
  const s = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      const body = JSON.parse(b || '{}')
      seen.push(body)
      if (dropNextStart && body.event === 'turn_start') {
        dropNextStart = false
        res.writeHead(500, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'lost' }))
        return
      }
      const cur = threads.get(body.thread)
      if (!cur) {
        const key = registrations === 0 ? oldKey : newKey
        registrations += 1
        threads.set(body.thread, { key, event: body.event, turn: body.turn_id, seq: body.seq })
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, thread_key: key }))
        return
      }
      if (body.thread_key !== cur.key) {
        res.writeHead(409, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: 'unknown key' }))
        return
      }
      cur.event = body.event
      cur.turn = body.turn_id
      cur.seq = body.seq
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true }))
    })
  })
  await new Promise(resolve => s.listen(0, '127.0.0.1', resolve))
  const env = {
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: 't',
    PLATFORM_HEARTBEAT_URL: `http://127.0.0.1:${s.address().port}`,
  }
  const start = await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('UserPromptSubmit', { prompt: 'x' })), env })
  assert.equal(start.code, 0, start.err)
  assert.equal(threads.size, 1)
  dropNextStart = true
  const lost = await runScript(['hook', 'claude'], { stdin: JSON.stringify(claude('UserPromptSubmit', { prompt: 'y' })), env })
  assert.equal(lost.code, 0, lost.err)
  threads.clear()
  const tool = await runScript(['hook', 'claude'], {
    stdin: JSON.stringify(claude('PreToolUse', { tool_name: 'Bash', tool_input: { timeout: 600000 } })),
    env,
  })
  assert.equal(tool.code, 0, tool.err)
  assert.equal(threads.size, 1, `old key, unconfirmed turn, server record pruned: ${[...threads.keys()].join(',')}`)
  const only = threads.get(CLAUDE_ID)
  assert.ok(only, 'the re-registered thread kept its id')
  assert.equal(only.event, 'before_tool')
  assert.equal(only.key, newKey)
  const tools = seen.filter(b => b.event === 'before_tool')
  assert.equal(tools.length, 1)
  assert.equal(tools[0].thread, CLAUDE_ID)
  assert.equal(tools[0].thread_key, newKey)
  const prevHome = process.env.BIFROST_HOME_OVERRIDE
  process.env.BIFROST_HOME_OVERRIDE = home
  try {
    const gate = loadGate('claude', CLAUDE_ID)
    assert.equal(gate.records.length, 1, 'the client superseded the record it had just re-registered')
    assert.equal(gate.records[0].key, newKey)
  } finally {
    if (prevHome === undefined) delete process.env.BIFROST_HOME_OVERRIDE
    else process.env.BIFROST_HOME_OVERRIDE = prevHome
  }
  s.close()
}

// lock preparation consumes the budget
function lockPreparationConsumesTheBudget() {
  const saved = {
    now: lockRuntime.now,
    prepare: lockRuntime.prepare,
    sleep: lockRuntime.sleep,
    spawn: lockRuntime.spawn,
  }
  const prevHome = process.env.BIFROST_HOME_OVERRIDE
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prep-budget-'))
  process.env.BIFROST_HOME_OVERRIDE = home
  const fakeChild = () => ({ unref() {}, kill() {}, stdin: { destroy() {} } })
  try {
    // Preparation takes 750 ms of simulated time. The helper never becomes ready.
    // The hook's limit is 5000 ms, so the wait must end at that deadline and the
    // helper must be given the reduced wait (4250 ms), not a fresh 5000 ms.
    let t = 10_000_000
    const limit = 5000
    const prepMs = 750
    let givenWait = null
    lockRuntime.now = () => t
    lockRuntime.prepare = () => {
      t += prepMs
    }
    lockRuntime.sleep = ms => {
      t += ms
    }
    lockRuntime.spawn = (_lockPath, waitMs) => {
      givenWait = waitMs
      return fakeChild()
    }
    armHookDeadline(limit)
    const deadline = t + limit
    let err = null
    try {
      withThreadLock('claude', 'prep-budget', () => {})
    } catch (e) {
      err = e
    }
    assert.equal(err && err.message, 'thread lock timeout')
    assert.equal(givenWait, limit - prepMs)
    assert.ok(t <= deadline, `lock wait ran past the hook deadline, ended at +${t - (deadline - limit)}ms`)
    assert.equal(t, deadline)

    // Nothing left after preparation: time out without starting the helper.
    clearHookDeadline()
    t = 10_000_000
    givenWait = null
    lockRuntime.prepare = () => {
      t += limit
    }
    armHookDeadline(limit)
    err = null
    try {
      withThreadLock('claude', 'prep-budget-spent', () => {})
    } catch (e) {
      err = e
    }
    assert.equal(err && err.message, 'thread lock timeout')
    assert.equal(givenWait, null)
  } finally {
    lockRuntime.now = saved.now
    lockRuntime.prepare = saved.prepare
    lockRuntime.sleep = saved.sleep
    lockRuntime.spawn = saved.spawn
    clearHookDeadline()
    if (prevHome === undefined) delete process.env.BIFROST_HOME_OVERRIDE
    else process.env.BIFROST_HOME_OVERRIDE = prevHome
  }
}

async function lockWaitUsesRemainingBudget() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-budget-'))
  const env = { ...process.env, BIFROST_HOME_OVERRIDE: home }
  delete env.PLATFORM_REPORTER_TOKEN
  const holderSrc = `
    const fs = require('fs')
    const { withThreadLock } = require(${JSON.stringify(SCRIPT)})
    withThreadLock('claude', 'budget-thread', () => {
      fs.writeSync(1, 'held\\n')
      const buf = new Int32Array(new SharedArrayBuffer(4))
      Atomics.wait(buf, 0, 0, 30000)
    })
  `
  const holder = spawn(process.execPath, ['-e', holderSrc], { env })
  let held = ''
  holder.stdout.on('data', d => (held += d))
  const sawHeld = await waitFor(() => held.includes('held'))
  assert.equal(sawHeld, true, 'holder did not take the lock')
  const prevHome = process.env.BIFROST_HOME_OVERRIDE
  process.env.BIFROST_HOME_OVERRIDE = home
  const started = performance.now()
  let threw = false
  try {
    armHookDeadline(250)
    withThreadLock('claude', 'budget-thread', () => {})
  } catch {
    threw = true
  } finally {
    clearHookDeadline()
    holder.kill('SIGKILL')
    if (prevHome === undefined) delete process.env.BIFROST_HOME_OVERRIDE
    else process.env.BIFROST_HOME_OVERRIDE = prevHome
  }
  const elapsed = performance.now() - started
  assert.equal(threw, true)
  assert.ok(elapsed < 1000, `lock wait used a fresh budget, took ${elapsed}ms`)
}

async function deadLockRace() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-deadlock-'))
  const log = path.join(home, 'critical.log')
  fs.writeFileSync(log, '')
  const env = { ...process.env, BIFROST_HOME_OVERRIDE: home }
  delete env.PLATFORM_REPORTER_TOKEN
  const holderSrc = `
    const fs = require('fs')
    const { withThreadLock } = require(${JSON.stringify(SCRIPT)})
    withThreadLock('claude', 'dead-thread', () => {
      fs.writeSync(1, 'held\\n')
      const buf = new Int32Array(new SharedArrayBuffer(4))
      Atomics.wait(buf, 0, 0, 30000)
    })
  `
  const holder = spawn(process.execPath, ['-e', holderSrc], { env })
  let held = ''
  holder.stdout.on('data', d => (held += d))
  const sawHeld = await waitFor(() => held.includes('held'))
  assert.equal(sawHeld, true, 'holder did not take the lock')
  holder.kill('SIGKILL')
  await new Promise(r => setTimeout(r, 50))
  const racerSrc = `
    const fs = require('fs')
    const { withThreadLock } = require(${JSON.stringify(SCRIPT)})
    withThreadLock('claude', 'dead-thread', () => {
      fs.appendFileSync(${JSON.stringify(log)}, 'enter ' + process.pid + '\\n')
      const buf = new Int32Array(new SharedArrayBuffer(4))
      Atomics.wait(buf, 0, 0, 200)
      fs.appendFileSync(${JSON.stringify(log)}, 'exit ' + process.pid + '\\n')
    })
    process.stdout.write('done\\n')
  `
  const once = () =>
    new Promise(resolve => {
      const p = spawn(process.execPath, ['-e', racerSrc], { env })
      let out = ''
      let err = ''
      p.stdout.on('data', d => (out += d))
      p.stderr.on('data', d => (err += d))
      p.on('exit', code => resolve({ code, out, err }))
    })
  const [a, b] = await Promise.all([once(), once()])
  assert.equal(a.code, 0, a.err)
  assert.equal(b.code, 0, b.err)
  const lines = fs.readFileSync(log, 'utf8').trim().split('\n').filter(Boolean)
  assert.equal(lines.length, 4, `critical section log: ${lines.join(' | ')}`)
  let inside = false
  const entered = new Set()
  for (const line of lines) {
    const [kind, pid] = line.split(' ')
    if (kind === 'enter') {
      assert.equal(inside, false, `two reclaimers entered together: ${lines.join(' | ')}`)
      inside = true
      entered.add(pid)
    } else {
      assert.equal(kind, 'exit')
      assert.equal(inside, true)
      inside = false
    }
  }
  assert.equal(entered.size, 2)
  assert.equal(inside, false)
  // The helper is what the test required; touch the export so a refactor cannot drop the lock.
  assert.equal(typeof withThreadLock, 'function')
}

function sleepMs(ms) {
  return new Promise(r => setTimeout(r, ms))
}

function writeScript(dir, name, body) {
  const file = path.join(dir, name)
  fs.writeFileSync(file, `'use strict'\n${body}`)
  return file
}

const CHILD_LOOP = `
const fs = require('fs')
const file = process.argv[2]
const writes = Number(process.argv[3])
const gap = Number(process.argv[4])
const code = Number(process.argv[5] || 0)
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
if (writes <= 0) {
  if (gap > 0) sleep(gap)
} else {
  for (let i = 0; i < writes; i++) {
    if (gap > 0) sleep(gap)
    fs.appendFileSync(file, 'x')
  }
  if (gap > 0) sleep(gap)
}
process.exit(code)
`

function runEnv(home, url, extra = {}) {
  return {
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: 't',
    PLATFORM_HEARTBEAT_URL: url,
    BIFROST_HEARTBEAT_PROGRESS: '',
    BIFROST_HEARTBEAT_RUN_BEAT_MS: '',
    ...extra,
  }
}

async function progressBeats() {
  const beat = 200
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-'))
  const progress = path.join(home, 'progress')
  fs.writeFileSync(progress, '')
  const loop = writeScript(home, 'loop.js', CHILD_LOOP)
  const kill = writeScript(home, 'kill.js', `
const fs = require('fs')
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
sleep(300)
fs.appendFileSync(process.argv[2], 'x')
process.kill(process.pid, 'SIGKILL')
`)
  const srv = await server()
  const base = runEnv(home, srv.url, { BIFROST_HEARTBEAT_RUN_BEAT_MS: String(beat) })

  const grew = await runScript(['run', 'cursor', '--', process.execPath, loop, progress, '3', String(beat + 800)], {
    env: { ...base, BIFROST_HEARTBEAT_PROGRESS: progress },
  })
  assert.equal(grew.code, 0, grew.err)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'after_tool', 'after_tool', 'after_tool', 'turn_end'])
  assert.deepEqual(srv.got.filter(g => g.body.event === 'after_tool').map(g => g.body.tool), [
    'headless-progress', 'headless-progress', 'headless-progress',
  ])
  assert.equal(new Set(srv.got.map(g => g.body.thread)).size, 1)
  assert.equal(new Set(srv.got.map(g => g.body.turn_id)).size, 1)
  assert.deepEqual(srv.got.map(g => g.body.seq), [1, 2, 3, 4, 5])

  srv.got.length = 0
  const once = await runScript(['run', 'cursor', '--', process.execPath, loop, progress, '1', String(beat * 3 + 500)], {
    env: { ...base, BIFROST_HEARTBEAT_PROGRESS: progress },
  })
  assert.equal(once.code, 0, once.err)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'after_tool', 'turn_end'])
  assert.equal(srv.got[1].body.tool, 'headless-progress')

  srv.got.length = 0
  const unset = await runScript(['run', 'cursor', '--', process.execPath, loop, progress, '0', String(beat * 3 + 200), '0'], {
    env: base,
  })
  assert.equal(unset.code, 0, unset.err)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'turn_end'])

  srv.got.length = 0
  const missing = path.join(home, 'no-such-progress')
  const gone = await runScript(['run', 'cursor', '--', process.execPath, loop, progress, '0', String(beat * 3 + 200), '4'], {
    env: { ...base, BIFROST_HEARTBEAT_PROGRESS: missing },
  })
  assert.equal(gone.code, 4, gone.err)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'turn_end'])

  srv.got.length = 0
  const sealed = path.join(home, 'sealed')
  fs.mkdirSync(sealed)
  const hidden = path.join(sealed, 'progress')
  fs.writeFileSync(hidden, '')
  fs.chmodSync(sealed, 0o000)
  try {
    const unreadable = await runScript(['run', 'cursor', '--', process.execPath, loop, progress, '0', String(beat * 3 + 200), '4'], {
      env: { ...base, BIFROST_HEARTBEAT_PROGRESS: hidden },
    })
    assert.equal(unreadable.code, 4, unreadable.err)
    assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'turn_end'])
  } finally {
    fs.chmodSync(sealed, 0o700)
  }

  srv.got.length = 0
  const longBeat = '10000'
  const signaled = await runScript(['run', 'cursor', '--', process.execPath, kill, progress], {
    env: { ...base, BIFROST_HEARTBEAT_PROGRESS: progress, BIFROST_HEARTBEAT_RUN_BEAT_MS: longBeat },
  })
  assert.equal(signaled.code, 128 + os.constants.signals.SIGKILL, signaled.err)
  assert.ok(signaled.ms < 4000, `wrapper waited ${signaled.ms}ms after the child was killed`)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'turn_end'])

  srv.got.length = 0
  const quick = writeScript(home, 'quick.js', 'process.exit(0)\n')
  const prompt = await runScript(['run', 'cursor', '--', process.execPath, quick], {
    env: { ...base, BIFROST_HEARTBEAT_PROGRESS: progress, BIFROST_HEARTBEAT_RUN_BEAT_MS: longBeat },
  })
  assert.equal(prompt.code, 0, prompt.err)
  assert.ok(prompt.ms < 4000, `wrapper waited ${prompt.ms}ms after the child exited`)
  assert.deepEqual(srv.got.map(g => g.body.event), ['turn_start', 'turn_end'])
  srv.s.close()
}

function listen(s) {
  return new Promise(resolve => s.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${s.address().port}`)))
}

async function progressEdges() {
  const beat = 200
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-edge-'))
  const progress = path.join(home, 'progress')
  fs.writeFileSync(progress, '0123456789abcdef')
  const trunc = writeScript(home, 'trunc.js', `
const fs = require('fs')
const file = process.argv[2]
const gap = Number(process.argv[3])
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
sleep(gap)
fs.writeFileSync(file, 'x')
sleep(gap)
fs.appendFileSync(file, 'yyyy')
sleep(gap)
process.exit(0)
`)
  const truncSrv = await server()
  const truncRun = await runScript(['run', 'cursor', '--', process.execPath, trunc, progress, String(beat + 800)], {
    env: runEnv(home, truncSrv.url, { BIFROST_HEARTBEAT_PROGRESS: progress, BIFROST_HEARTBEAT_RUN_BEAT_MS: String(beat) }),
  })
  assert.equal(truncRun.code, 0, truncRun.err)
  assert.deepEqual(truncSrv.got.map(g => g.body.event), ['turn_start', 'after_tool', 'turn_end'])
  assert.equal(truncSrv.got[1].body.tool, 'headless-progress')
  truncSrv.s.close()

  const flightHome = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-flight-'))
  const flightFile = path.join(flightHome, 'progress')
  fs.writeFileSync(flightFile, '')
  const flightChild = writeScript(flightHome, 'flight.js', `
const fs = require('fs')
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
fs.appendFileSync(process.argv[2], 'x')
sleep(500)
process.exit(0)
`)
  const flightGot = []
  const flightSrv = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      const body = JSON.parse(b || '{}')
      flightGot.push(body)
      const delay = body.event === 'after_tool' ? 3000 : 0
      setTimeout(() => {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
      }, delay)
    })
  })
  const flightURL = await listen(flightSrv)
  const flight = await runScript(['run', 'cursor', '--', process.execPath, flightChild, flightFile], {
    env: runEnv(flightHome, flightURL, { BIFROST_HEARTBEAT_PROGRESS: flightFile, BIFROST_HEARTBEAT_RUN_BEAT_MS: '120' }),
  })
  assert.equal(flight.code, 0, flight.err)
  assert.ok(flight.ms < 2200, `in-flight progress delayed turn_end: wrapper ${flight.ms}ms`)
  assert.ok(await waitFor(() => flightGot.some(b => b.event === 'turn_end') && flightGot.some(b => b.event === 'after_tool')))
  const prog = flightGot.find(b => b.event === 'after_tool')
  const end = flightGot.find(b => b.event === 'turn_end')
  assert.equal(prog.tool, 'headless-progress')
  assert.ok(prog.seq < end.seq, `progress seq ${prog.seq} is not before turn_end seq ${end.seq}`)
  assert.equal(flightGot.filter(b => b.event === 'after_tool').length, 1)
  flightSrv.close()

  const lockHome = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-lock-'))
  const lockFile = path.join(lockHome, 'progress')
  const go = path.join(lockHome, 'go')
  const ready = path.join(lockHome, 'ready')
  const stamp = path.join(lockHome, 'stamp')
  fs.writeFileSync(lockFile, '')
  const thread = 'run-lock-exit'
  const exitChild = writeScript(lockHome, 'exit.js', `
const fs = require('fs')
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
sleep(400)
fs.writeFileSync(process.argv[3], 'go')
const ready = process.argv[5]
const until = Date.now() + 3000
while (!fs.existsSync(ready) && Date.now() < until) sleep(20)
fs.appendFileSync(process.argv[2], 'x')
sleep(250)
fs.writeFileSync(process.argv[4], String(Date.now()))
process.exit(0)
`)
  const holderCode = `
    const fs = require('fs')
    const hb = require(process.argv[1])
    const go = process.argv[2]
    const until = Date.now() + 5000
    while (!fs.existsSync(go) && Date.now() < until) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20)
    hb.withThreadLock('cursor', process.argv[3], () => {
      fs.writeFileSync(process.argv[4], 'held')
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 8000)
    })
  `
  const holder = spawn(process.execPath, ['-e', holderCode, SCRIPT, go, thread, ready], {
    env: { ...process.env, BIFROST_HOME_OVERRIDE: lockHome },
  })
  const lockGot = []
  const lockSrv = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      lockGot.push({ body: JSON.parse(b || '{}'), at: Date.now() })
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
    })
  })
  try {
    const lockURL = await listen(lockSrv)
    const locked = await runScript(['run', 'cursor', '--', process.execPath, exitChild, lockFile, go, stamp, ready], {
      env: runEnv(lockHome, lockURL, {
        BIFROST_HEARTBEAT_PROGRESS: lockFile,
        BIFROST_HEARTBEAT_RUN_BEAT_MS: '80',
        BIFROST_HEARTBEAT_THREAD: thread,
      }),
    })
    assert.equal(locked.code, 0, locked.err)
    const exitedAt = Number(fs.readFileSync(stamp, 'utf8'))
    const delta = Date.now() - exitedAt
    // The lock is still held, so turn_end waits out its own budget once. A beat
    // that blocked the event loop would add a second wait on top of that.
    assert.ok(delta > 1000 && delta < 3200, `wrapper reached turn_end ${delta}ms after the child exited`)
  } finally {
    holder.kill('SIGKILL')
    lockSrv.close()
  }

  const skipHome = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-skip-'))
  const skipFile = path.join(skipHome, 'progress')
  fs.writeFileSync(skipFile, '')
  const skipReady = path.join(skipHome, 'ready')
  const skipHolderCode = `
    const fs = require('fs')
    const hb = require(process.argv[1])
    hb.withThreadLock('cursor', 'run-skip', () => {
      fs.writeFileSync(process.argv[2], 'held')
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 8000)
    })
  `
  const skipHolder = spawn(process.execPath, ['-e', skipHolderCode, SCRIPT, skipReady], {
    env: { ...process.env, BIFROST_HOME_OVERRIDE: skipHome },
  })
  const saved = {
    home: process.env.BIFROST_HOME_OVERRIDE,
    token: process.env.PLATFORM_REPORTER_TOKEN,
    url: process.env.PLATFORM_HEARTBEAT_URL,
    progress: process.env.BIFROST_HEARTBEAT_PROGRESS,
    beat: process.env.BIFROST_HEARTBEAT_RUN_BEAT_MS,
  }
  const skipSrv = await server()
  let stop = () => {}
  try {
    assert.ok(await waitFor(() => fs.existsSync(skipReady)))
    process.env.BIFROST_HOME_OVERRIDE = skipHome
    process.env.PLATFORM_REPORTER_TOKEN = 't'
    process.env.PLATFORM_HEARTBEAT_URL = skipSrv.url
    process.env.BIFROST_HEARTBEAT_PROGRESS = skipFile
    process.env.BIFROST_HEARTBEAT_RUN_BEAT_MS = '60'
    let alive = true
    stop = await startProgressBeats({ thread: 'run-skip', session: 'run-skip', vendor: 'cursor', host: 'h' }, () => alive)
    const t0 = Date.now()
    fs.appendFileSync(skipFile, 'a')
    await sleepMs(400)
    assert.ok(Date.now() - t0 < 1000, 'a busy progress lock blocked the event loop')
    assert.equal(skipSrv.got.length, 0, 'a beat was sent while the lock was busy')
    skipHolder.kill('SIGKILL')
    await sleepMs(120)
    assert.equal(skipSrv.got.length, 0, 'skipped growth was sent once the lock freed without further growth')
    fs.appendFileSync(skipFile, 'b')
    assert.ok(await waitFor(() => skipSrv.got.length === 1), 'growth after the lock was free sent nothing')
    await sleepMs(150)
    assert.equal(skipSrv.got.length, 1)
    assert.equal(skipSrv.got[0].body.tool, 'headless-progress')
    alive = false
  } finally {
    stop()
    skipHolder.kill('SIGKILL')
    skipSrv.s.close()
    for (const [key, value] of Object.entries({
      BIFROST_HOME_OVERRIDE: saved.home,
      PLATFORM_REPORTER_TOKEN: saved.token,
      PLATFORM_HEARTBEAT_URL: saved.url,
      BIFROST_HEARTBEAT_PROGRESS: saved.progress,
      BIFROST_HEARTBEAT_RUN_BEAT_MS: saved.beat,
    })) {
      if (value == null) delete process.env[key]
      else process.env[key] = value
    }
  }
}

// Force contention after the progress stamp, when 409 recovery used to wait
// synchronously. turn_end may spend its own lock budget, but never a beat's too.
async function progressRecoveryDoesNotDelayExit(accepted = false) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-prog-recover-'))
  const file = path.join(home, 'progress')
  const go = path.join(home, 'go')
  const ready = path.join(home, 'ready')
  const replied = path.join(home, 'replied')
  const exited = path.join(home, 'exited')
  const thread = 'run-recovery-exit'
  fs.writeFileSync(file, '')
  const child = writeScript(home, 'exit.js', `
const fs = require('fs')
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
fs.appendFileSync(process.argv[2], 'x')
const until = Date.now() + 5000
while (!fs.existsSync(process.argv[3]) && Date.now() < until) sleep(10)
if (!fs.existsSync(process.argv[3])) process.exit(91)
sleep(80)
fs.writeFileSync(process.argv[4], String(Date.now()))
process.exit(7)
`)
  const holder = spawn(process.execPath, ['-e', `
const fs = require('fs')
const hb = require(process.argv[1])
const until = Date.now() + 8000
while (!fs.existsSync(process.argv[2]) && Date.now() < until) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10)
hb.withThreadLock('cursor', process.argv[3], () => {
  fs.writeFileSync(process.argv[4], 'held')
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 8000)
})
`, SCRIPT, go, thread, ready], {
    env: { ...process.env, BIFROST_HOME_OVERRIDE: home },
    stdio: 'ignore',
  })
  const got = []
  let heldAtReply = false
  const srv = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', async () => {
      const body = JSON.parse(b || '{}')
      got.push(body)
      if (body.event === 'after_tool') {
        fs.writeFileSync(go, 'go')
        heldAtReply = await waitFor(() => fs.existsSync(ready))
        res.writeHead(accepted ? 202 : 409, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify(accepted ? { ok: true, thread_key: ISSUED_KEY } : { error: 'unknown key' }))
        fs.writeFileSync(replied, 'replied')
      } else {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ thread_key: ISSUED_KEY }))
      }
    })
  })
  try {
    const url = await listen(srv)
    const result = await runScript(['run', 'cursor', '--', process.execPath, child, file, replied, exited], {
      env: runEnv(home, url, {
        BIFROST_HEARTBEAT_PROGRESS: file,
        BIFROST_HEARTBEAT_RUN_BEAT_MS: '80',
        BIFROST_HEARTBEAT_THREAD: thread,
      }),
    })
    assert.ok(heldAtReply, 'the recovery lock was not held when 409 was returned')
    assert.equal(result.code, 7, result.err)
    const delay = Date.now() - Number(fs.readFileSync(exited, 'utf8'))
    assert.ok(delay > 1000 && delay < 3200, `progress recovery added to turn_end's lock budget: ${delay}ms`)
    assert.deepEqual(got.map(b => b.event), ['turn_start', 'after_tool'], 'a dropped beat retried registration')
    const gate = JSON.parse(fs.readFileSync(path.join(home, '.cache', 'bifrost', 'thread-keys', 'cursor', thread), 'utf8'))
    assert.equal(gate.records.length, 1, 'recovery continued after child exit')
    assert.equal(gate.records[0].status, 'active')
  } finally {
    holder.kill('SIGKILL')
    srv.close()
    srv.closeAllConnections()
  }
}

// The wrapped agent's hook shares the wrapper thread and declares a real timeout.
async function pendingToolSuppressesProgress() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-pending-'))
  const file = path.join(home, 'progress')
  fs.writeFileSync(file, '')
  const child = writeScript(home, 'hooks.js', `
const fs = require('fs')
const { spawnSync } = require('child_process')
const sleep = ms => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
const hook = payload => {
  const r = spawnSync(process.execPath, [${JSON.stringify(SCRIPT)}, 'hook', 'cursor'], {
    input: JSON.stringify({ conversation_id: 'c1', session_id: 'c1', ...payload }), env: process.env
  })
  if (r.status !== 0 || r.stdout.length) process.exit(92)
}
const grow = ms => { const until = Date.now() + ms; while (Date.now() < until) { fs.appendFileSync(process.argv[2], 'x'); sleep(50) } }
hook({ hook_event_name: 'preToolUse', tool_name: 'Shell', tool_input: { timeout: 1800000 } })
grow(600)
hook({ hook_event_name: 'postToolUse', tool_name: 'Shell' })
grow(600)
hook({ hook_event_name: 'preToolUse', tool_name: 'Shell', tool_input: { timeout: 1000 } })
grow(1700)
`)
  const got = []
  const srv = http.createServer((req, res) => {
    let raw = ''
    req.on('data', d => (raw += d))
    req.on('end', () => {
      const body = JSON.parse(raw)
      const throttle = body.event === 'before_tool'
        ? JSON.parse(fs.readFileSync(path.join(home, '.cache', 'bifrost', 'heartbeat.json'), 'utf8')) : {}
      got.push({ body, at: Date.now(), declaredAt: (throttle[`cursor/${body.thread}`] || {}).at })
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
    })
  })
  try {
    const result = await runScript(['run', 'cursor', '--', process.execPath, child, file], {
      env: runEnv(home, await listen(srv), { BIFROST_HEARTBEAT_PROGRESS: file, BIFROST_HEARTBEAT_RUN_BEAT_MS: '80' }),
    })
    assert.equal(result.code, 0, result.err)
    const events = got.sort((a, b) => a.body.seq - b.body.seq)
    const pre = events.filter(g => g.body.event === 'before_tool')
    const after = events.find(g => g.body.event === 'after_tool' && g.body.tool === 'Shell')
    const beats = events.filter(g => g.body.tool === 'headless-progress')
    assert.equal(pre.length, 2)
    assert.ok(after, 'matching tool completion was not sent')
    assert.equal(pre[0].body.tool_timeout_s, 1800)
    assert.equal(pre[1].body.tool_timeout_s, 1)
    assert.ok(events.every(g => g.body.thread === events[0].body.thread), 'hook and wrapper did not share a thread')
    assert.equal(beats.filter(g => g.body.seq > pre[0].body.seq && g.body.seq < after.body.seq).length, 0, 'beat clobbered a pending declared tool timeout')
    assert.ok(beats.some(g => g.body.seq > after.body.seq && g.body.seq < pre[1].body.seq), 'beats did not resume after after_tool')
    const expired = beats.filter(g => g.body.seq > pre[1].body.seq)
    assert.ok(expired.length, 'beats did not resume after timeout expiry')
    assert.ok(expired.every(g => g.at - pre[1].declaredAt >= 1000), 'beat appeared before declared timeout expired')
  } finally {
    srv.close()
    srv.closeAllConnections()
  }
}

// A slow turn_end leaves time for the planted missing-stop violation to fire.
async function noBeatAfterExit() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-after-exit-'))
  const file = path.join(home, 'progress')
  fs.writeFileSync(file, '')
  const child = writeScript(home, 'exit.js', `
const fs = require('fs')
Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 150)
fs.appendFileSync(process.argv[2], 'x')
process.exit(0)
`)
  const got = []
  const srv = http.createServer((req, res) => {
    let raw = ''
    req.on('data', d => (raw += d))
    req.on('end', async () => {
      const body = JSON.parse(raw)
      got.push(body)
      if (body.event === 'turn_end') await sleepMs(1200)
      res.writeHead(202, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ ok: true, thread_key: ISSUED_KEY }))
    })
  })
  try {
    const result = await runScript(['run', 'codex', '--', process.execPath, child, file], {
      env: runEnv(home, await listen(srv), { BIFROST_HEARTBEAT_PROGRESS: file, BIFROST_HEARTBEAT_RUN_BEAT_MS: '400' }),
    })
    assert.equal(result.code, 0, result.err)
    const end = got.find(b => b.event === 'turn_end')
    assert.ok(end)
    assert.equal(got.filter(b => b.seq > end.seq).length, 0, 'event sequence continued after turn_end')
    assert.equal(got.filter(b => b.tool === 'headless-progress').length, 0, 'beat sent after child exit')
  } finally {
    srv.close()
    srv.closeAllConnections()
  }
}

async function hookIgnoresProgress() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-hook-env-'))
  const file = path.join(home, 'progress')
  fs.writeFileSync(file, 'x')
  const trace = path.join(home, 'trace')
  const preload = writeScript(home, 'trace.js', `
const fs = require('fs')
const trace = ${JSON.stringify(trace)}, file = ${JSON.stringify(file)}
const counts = { reads: 0, stats: 0 }
process.env = new Proxy(process.env, { get(target, key) {
  // Node enumerates the inherited environment when spawning the lock helper.
  // Only a direct script read is an added hook dependency.
  if (key === 'BIFROST_HEARTBEAT_PROGRESS' && !new Error().stack.split('\\n')[2].includes('node:')) counts.reads++
  return target[key]
} })
for (const api of [fs, fs.promises]) {
  for (const name of ['stat', 'statSync']) {
    if (!api[name]) continue
    const original = api[name]
    api[name] = function (target, ...args) {
      if (target === file) counts.stats++
      return original.call(this, target, ...args)
    }
  }
}
process.on('exit', () => fs.writeFileSync(trace, JSON.stringify(counts)))
`)
  for (const vendor of ['cursor', 'claude', 'codex']) {
    const stdin = JSON.stringify({ session_id: 'hook-env', conversation_id: 'hook-env', hook_event_name: vendor === 'cursor' ? 'preToolUse' : 'PreToolUse', tool_name: 'Shell', tool_input: { timeout: 30000 } })
    const env = { BIFROST_HOME_OVERRIDE: home, NODE_OPTIONS: `--require=${preload}`, BIFROST_HEARTBEAT_PROGRESS: '' }
    const without = await runScript(['hook', vendor], { stdin, env })
    assert.deepEqual(JSON.parse(fs.readFileSync(trace)), { reads: 0, stats: 0 })
    const withProgress = await runScript(['hook', vendor], { stdin, env: { ...env, BIFROST_HEARTBEAT_PROGRESS: file } })
    assert.deepEqual(JSON.parse(fs.readFileSync(trace)), { reads: 0, stats: 0 }, `${vendor} hook inspected progress`)
    assert.deepEqual([withProgress.code, withProgress.out, withProgress.err], [without.code, without.out, without.err])
    assert.deepEqual([withProgress.code, withProgress.out, withProgress.err], [0, '', ''])
  }
}

async function progressBoundsAndAsyncStat() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-bounds-'))
  const probe = writeScript(home, 'bounds.js', `
const assert = require('assert/strict'), fs = require('fs')
const hb = require(${JSON.stringify(SCRIPT)})
const file = process.env.BIFROST_HEARTBEAT_PROGRESS
const originalStat = fs.statSync
fs.statSync = function (target, ...args) { assert.notEqual(target, file, 'progress stat blocked event loop'); return originalStat.call(this, target, ...args) }
let resolveStat
fs.promises.stat = () => new Promise(resolve => { resolveStat = resolve })
const originalTimer = global.setTimeout
let interval, tick
;(async () => {
  for (const [raw, expected] of [['0.01', 1000], ['3000000000', 2147483647], ['1000', 1000], ['2000', 2000], ['bad', 120000], ['0', 1000], ['-1', 1000]]) {
    process.env.BIFROST_HEARTBEAT_RUN_BEAT_MS = raw
    global.setTimeout = (fn, ms) => { interval = ms; tick = fn; return { unref() {} } }
    const ready = hb.startProgressBeats({ thread: 'bounds', vendor: 'cursor', host: 'h' }, () => true)
    let responsive = false
    await new Promise(resolve => setImmediate(() => { responsive = true; resolve() }))
    assert.ok(responsive)
    resolveStat({ size: 0 })
    const stop = await ready
    assert.equal(interval, expected)
    const looking = tick()
    await new Promise(resolve => setImmediate(resolve))
    stop()
    resolveStat({ size: 1 })
    await looking
  }
  global.setTimeout = originalTimer
})().catch(err => { console.error(err); process.exit(1) })
`)
  const result = await runScript(['run', 'cursor', '--', process.execPath, probe], {
    env: { BIFROST_HOME_OVERRIDE: home, BIFROST_HEARTBEAT_PROGRESS: path.join(home, 'missing'), BIFROST_HEARTBEAT_TEST_FAST_BEATS: '', PLATFORM_REPORTER_TOKEN: '' },
  })
  assert.equal(result.code, 0, result.err)
}

async function main() {
  mapping()
  timeouts()
  throttle()
  lateResponseDoesNotTouchTheCurrentRecord()
  await neverBlocks()
  await seqLock()
  await nonceAndUnknownKey()
  await runContinuesSequence()
  await lostTurnStartThenBeforeTool()
  await oldKeyUnconfirmedTurnServerRecordPruned()
  lockPreparationConsumesTheBudget()
  await lockWaitUsesRemainingBudget()
  await deadLockRace()
  await endToEnd()
  await progressBeats()
  await progressEdges()
  await progressRecoveryDoesNotDelayExit()
  await progressRecoveryDoesNotDelayExit(true)
  await pendingToolSuppressesProgress()
  await noBeatAfterExit()
  await hookIgnoresProgress()
  await progressBoundsAndAsyncStat()
  console.log('thread-heartbeat: ok')
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
