'use strict'
// Shared by the collector-mode tests (R5:5.5-12 S1-4). Not a test file itself.
// Every hook runs in a fresh process with an environment built from nothing,
// so the session this suite runs in (its CLAUDE_PID, sidebar id, tokens) never
// reaches the scripts. Requests go to a local fake server only.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')

// The real directory: run through the workspace's symlinked scripts/, `..` must still be agent-config.
const HERE = fs.realpathSync(__dirname)
const ISSUED_KEY = 'cd'.repeat(32)
const REPORTER = 'reporter-test-token'
const COLLECTOR = 'collector-test-token'
const FIXTURES = path.join(HERE, 'testdata', 'source-capability')

function tmpHome(tag) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `collector-${tag}-`))
}

// Loaded into every script process with NODE_OPTIONS=--require. It fixes the
// OS host name; with COLLECTOR_TEST_SEED it makes randomness deterministic
// (sha256 of seed, argv, n) for byte-for-byte comparisons; with
// COLLECTOR_TEST_MARKS a detached sender marks its start and its exit, so a
// test knows when every detached beat has been answered.
const PRELOAD = `
const crypto = require('node:crypto')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
os.hostname = () => 'TestHost.local'
const marks = process.env.COLLECTOR_TEST_MARKS
if (marks && process.argv.includes('--send')) {
  fs.mkdirSync(marks, { recursive: true })
  fs.writeFileSync(path.join(marks, 'start-' + process.pid), '')
  process.on('exit', () => fs.writeFileSync(path.join(marks, 'done-' + process.pid), ''))
}
if (process.env.COLLECTOR_TEST_SEED !== undefined) {
const seed = process.env.COLLECTOR_TEST_SEED + '|' + process.argv.slice(2).filter(a => !a.endsWith('.json')).join(' ')
let n = 0
crypto.randomBytes = (size, cb) => {
  const out = Buffer.alloc(size)
  for (let i = 0; i < size; i += 32) crypto.createHash('sha256').update(seed + ':' + (n++)).digest().copy(out, i)
  if (cb) { process.nextTick(cb, null, out); return undefined }
  return out
}
crypto.randomUUID = () => {
  const b = crypto.randomBytes(16)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = b.toString('hex')
  return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20)
}
}
`

let preload = ''
function preloadPath() {
  if (preload) return preload
  preload = path.join(tmpHome('preload'), 'preload.js')
  fs.writeFileSync(preload, PRELOAD)
  return preload
}

/** An environment from nothing: only what the test names, plus the preload. */
function cleanEnv(home, url, extra = {}) {
  const env = { PATH: process.env.PATH, BIFROST_HOME_OVERRIDE: home, PLATFORM_HEARTBEAT_URL: url,
    NODE_OPTIONS: `--require ${preloadPath()}`, COLLECTOR_TEST_MARKS: path.join(home, '.marks') }
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== null) env[k] = String(v)
  return env
}

function collectorEnv(home, url, extra = {}) {
  return cleanEnv(home, url, { PLATFORM_COLLECTOR_TOKEN: COLLECTOR, PLATFORM_REPORTER_TOKEN: REPORTER, BIFROST_HOST_ID: 'h1', ...extra })
}

/**
 * A fake platform-api. Each request is recorded with its raw body. respond(req)
 * may return { status, body } or 'hang' (accept and never answer).
 */
function fakeServer(respond) {
  const got = []
  const held = []
  let inflight = 0
  const s = http.createServer((req, res) => {
    inflight++
    let raw = ''
    req.on('data', d => (raw += d))
    req.on('end', () => {
      const rec = { method: req.method, url: req.url, auth: req.headers.authorization || '', type: req.headers['content-type'] || '', raw }
      try {
        rec.body = JSON.parse(raw || '{}')
      } catch {
        rec.body = null
      }
      got.push(rec)
      const answer = respond ? respond(rec, got.length) : null
      if (answer === 'hang') {
        held.push(res)
        inflight--
        return
      }
      const { status = 202, body = { ok: true, thread_key: ISSUED_KEY } } = answer || {}
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(body))
      inflight--
    })
  })
  return new Promise(resolve =>
    s.listen(0, '127.0.0.1', () =>
      resolve({
        got,
        get inflight() {
          return inflight
        },
        url: `http://127.0.0.1:${s.address().port}`,
        close() {
          for (const res of held) res.destroy()
          s.closeAllConnections()
          s.close()
        },
      }),
    ),
  )
}

function runNode(args, { env, stdin = '' }) {
  return new Promise(resolve => {
    const started = Date.now()
    const p = spawn(process.execPath, args, { env, stdio: ['pipe', 'pipe', 'pipe'] })
    let out = ''
    let err = ''
    p.stdout.on('data', d => (out += d))
    p.stderr.on('data', d => (err += d))
    p.on('exit', code => resolve({ code, out, err, ms: Date.now() - started }))
    p.stdin.end(stdin)
  })
}

function runHook(script, vendor, payload, env) {
  return runNode([script, 'hook', vendor], { env, stdin: JSON.stringify(payload) })
}

async function waitFor(fn, ms = 6000) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (fn()) return true
    await new Promise(r => setTimeout(r, 25))
  }
  return Boolean(fn())
}

function outboxEmpty(home) {
  try {
    return fs.readdirSync(path.join(home, '.cache', 'bifrost', 'heartbeat-out')).length === 0
  } catch {
    return true
  }
}

/** Every detached sender that started has exited (see PRELOAD). */
function sendersDone(home) {
  let names = []
  try {
    names = fs.readdirSync(path.join(home, '.marks'))
  } catch {
    return true
  }
  const done = new Set(names.filter(n => n.startsWith('done-')).map(n => n.slice(5)))
  return names.filter(n => n.startsWith('start-')).every(n => done.has(n.slice(6)))
}

/** Wait until the server has `count` requests and every detached sender is done, then for quiet. */
async function settle(srv, home, count, quietMs = 100) {
  await waitFor(() => srv.got.length >= count && outboxEmpty(home) && sendersDone(home) && srv.inflight === 0, 10000)
  let seen = -1
  while (seen !== srv.got.length) {
    seen = srv.got.length
    await new Promise(r => setTimeout(r, quietMs))
  }
}

function epochsFile(home, vendor, session) {
  return path.join(home, '.cache', 'bifrost', 'external-work', vendor, session, 'epochs.json')
}

function readEpochs(home, vendor, session) {
  try {
    return JSON.parse(fs.readFileSync(epochsFile(home, vendor, session), 'utf8'))
  } catch {
    return null
  }
}

function claudePayload(event, session, extra = {}) {
  return { session_id: session, transcript_path: `<home>/.claude/projects/<p>/${session}.jsonl`, cwd: '<project>', hook_event_name: event, ...extra }
}

/** Heartbeat requests only, as [event, reason, session, epoch]. */
function beats(srv) {
  return srv.got.filter(r => r.url === '/api/v1/agent/threads/heartbeat').map(r => [r.body.event, r.body.reason || '', r.body.session || '', r.body.epoch || 0])
}

function noTitle(srv) {
  for (const r of srv.got) {
    for (const k of Object.keys(r.body || {})) assert.notEqual(k.toLowerCase(), 'title', `a collector request named a title: ${r.raw}`)
  }
}

/** Hold an flock on `file` from another process until the returned function is called. */
function holdLock(file) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const ready = `${file}.held`
  const p = spawn('/usr/bin/perl', ['-e', 'use Fcntl qw(:flock); open my $f, ">>", $ARGV[0] or die; flock($f, LOCK_EX) or die; open my $r, ">", $ARGV[1]; close $r; 1 while sysread(STDIN, my $b, 4096);', file, ready], { stdio: ['pipe', 'ignore', 'ignore'] })
  return waitFor(() => fs.existsSync(ready), 3000).then(ok => {
    assert.ok(ok, 'the lock holder did not start')
    return () => {
      p.stdin.end()
      p.kill('SIGKILL')
    }
  })
}

module.exports = {
  HERE,
  FIXTURES,
  ISSUED_KEY,
  REPORTER,
  COLLECTOR,
  tmpHome,
  preloadPath,
  cleanEnv,
  collectorEnv,
  fakeServer,
  runNode,
  runHook,
  waitFor,
  settle,
  outboxEmpty,
  epochsFile,
  readEpochs,
  claudePayload,
  beats,
  noTitle,
  holdLock,
}
