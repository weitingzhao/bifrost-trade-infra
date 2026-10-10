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

const SCRIPT = path.join(__dirname, 'thread-heartbeat.js')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'heartbeat-'))
process.env.BIFROST_HOME_OVERRIDE = tmp
delete process.env.PLATFORM_REPORTER_TOKEN
delete process.env.BIFROST_HEARTBEAT_THREAD
delete process.env.BIFROST_HEARTBEAT_TITLE
delete process.env.BIFROST_WORK

const { beatFor, toolTimeoutSeconds, shouldSkip, reduceThrottle, allocateStamp } = require('./thread-heartbeat.js')
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
  // would add the 3 s hook deadline or the 5 s fetch timeout on top of it.
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

async function main() {
  mapping()
  timeouts()
  throttle()
  await neverBlocks()
  await seqLock()
  await nonceAndUnknownKey()
  await runContinuesSequence()
  await endToEnd()
  console.log('thread-heartbeat: ok')
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
