'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')
const test = require('node:test')

const SCRIPT = path.join(__dirname, 'progress-publish.js')
const home = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-publish-'))

function expectedHost() {
  return (os.hostname().split('.')[0] || 'unknown').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

function childEnv(extra = {}) {
  const env = { ...process.env, BIFROST_HOME_OVERRIDE: home }
  delete env.PLATFORM_REPORTER_TOKEN
  delete env.BIFROST_HEARTBEAT
  return { ...env, ...extra }
}

function run(file, env) {
  return new Promise(resolve => {
    const child = spawn(process.execPath, [SCRIPT, file], {
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let out = ''
    let err = ''
    child.stdout.on('data', d => {
      out += d
    })
    child.stderr.on('data', d => {
      err += d
    })
    child.on('exit', code => resolve({ code, out, err }))
  })
}

function listen(onRequest) {
  const requests = []
  const server = http.createServer((req, res) => {
    const chunks = []
    req.on('data', c => chunks.push(c))
    req.on('end', () => {
      const body = Buffer.concat(chunks)
      requests.push({
        method: req.method,
        url: req.url,
        body,
        auth: req.headers.authorization || '',
        type: req.headers['content-type'] || '',
      })
      if (onRequest) onRequest(req, res, body)
      else {
        res.writeHead(202, { 'Content-Type': 'application/json' })
        res.end('{"ok":true}')
      }
    })
  })
  return new Promise(resolve => {
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      resolve({
        server,
        requests,
        url: `http://127.0.0.1:${addr.port}`,
        close: () => new Promise(done => server.close(() => done())),
      })
    })
  })
}

function write(dir, name, contents) {
  const file = path.join(dir, name)
  fs.writeFileSync(file, contents)
  return file
}

const HEARTBEAT_EXPORTS = [
  'EVENTS',
  'HOOK_GIVE_UP_MS',
  'WAITING_NOTIFICATIONS',
  'allocateStamp',
  'armHookDeadline',
  'baseURL',
  'beatFor',
  'clearHookDeadline',
  'hostName',
  'loadGate',
  'lockRuntime',
  'publishProgress',
  'reduceThrottle',
  'saveIssuedKey',
  'shouldSkip',
  'supersedeActive',
  'toolTimeoutSeconds',
  'withThreadLock',
]

test('nothing exported can send a request to a caller-chosen path', () => {
  const hb = require('./thread-heartbeat.js')
  assert.equal(Object.hasOwn(hb, 'token'), false)
  assert.equal(Object.hasOwn(hb, 'reporterRequest'), false)
  assert.deepEqual(Object.keys(hb).sort(), [...HEARTBEAT_EXPORTS].sort())
  assert.equal(typeof hb.publishProgress, 'function')
  assert.equal(hb.publishProgress.length, 2)
  const pub = require('./progress-publish.js')
  assert.equal(Object.hasOwn(pub, 'reporterRequest'), false)
  assert.equal(Object.hasOwn(pub, 'publishProgress'), false)
  assert.deepEqual(Object.keys(pub).sort(), ['GIVE_UP_MS', 'MAX_BYTES', 'publish', 'readDocument'])
})

function withReporter(url, token, fn) {
  const prev = {
    PLATFORM_HEARTBEAT_URL: process.env.PLATFORM_HEARTBEAT_URL,
    PLATFORM_REPORTER_TOKEN: process.env.PLATFORM_REPORTER_TOKEN,
  }
  process.env.PLATFORM_HEARTBEAT_URL = url
  process.env.PLATFORM_REPORTER_TOKEN = token
  const hb = require('./thread-heartbeat.js')
  return Promise.resolve()
    .then(() => fn(hb))
    .finally(() => {
      for (const [key, value] of Object.entries(prev)) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
    })
}

test('publishProgress sends PUT to the constant path only', async () => {
  const srv = await listen()
  try {
    await withReporter(srv.url, 'reporter-token-w62', hb =>
      hb.publishProgress(Buffer.from('{"at":1}'), 2000, 'POST', 'https://evil.example/collect'),
    )
    assert.equal(srv.requests.length, 1)
    assert.equal(srv.requests[0].method, 'PUT')
    assert.equal(srv.requests[0].url, '/api/v1/agent/progress')
    assert.equal(srv.requests[0].auth, 'Bearer reporter-token-w62')
    assert.equal(srv.requests[0].url.includes('evil.example'), false)
  } finally {
    await srv.close()
  }
})

test('a base with a path, userinfo or query still ends at the constant path', async () => {
  const srv = await listen()
  const port = new URL(srv.url).port
  const bases = [
    `http://127.0.0.1:${port}/api/v1/agent/threads/heartbeat`,
    `http://alice:s3cret@127.0.0.1:${port}/other/place?x=1`,
    `http://127.0.0.1:${port}/?q=leak#frag`,
  ]
  try {
    for (const base of bases) {
      srv.requests.length = 0
      await withReporter(base, 'reporter-token-w62', hb => hb.publishProgress(Buffer.from('{"at":1}'), 2000))
      assert.equal(srv.requests.length, 1, base)
      const req = srv.requests[0]
      assert.equal(req.method, 'PUT', base)
      assert.equal(req.url, '/api/v1/agent/progress', base)
      assert.equal(req.auth, 'Bearer reporter-token-w62', base)
      assert.equal(req.auth.includes('alice'), false)
      assert.equal(req.auth.includes('s3cret'), false)
      assert.equal(req.url.includes('?'), false, base)
      assert.equal(req.url.includes('heartbeat'), false, base)
    }
  } finally {
    await srv.close()
  }
})

test('a 302 answer is not followed', async () => {
  const leaked = []
  const sink = http.createServer((req, res) => {
    leaked.push({ url: req.url, auth: req.headers.authorization || '' })
    res.writeHead(200)
    res.end('sink')
  })
  await new Promise(resolve => sink.listen(0, '127.0.0.1', resolve))
  const sinkPort = sink.address().port
  const srv = await listen((_req, res) => {
    res.writeHead(302, { Location: `http://127.0.0.1:${sinkPort}/collect` })
    res.end()
  })
  try {
    await withReporter(srv.url, 'reporter-token-w62', hb => hb.publishProgress(Buffer.from('{"at":1}'), 2000))
    assert.equal(srv.requests.length, 1)
    assert.equal(srv.requests[0].method, 'PUT')
    assert.equal(srv.requests[0].url, '/api/v1/agent/progress')
    assert.equal(srv.requests[0].auth, 'Bearer reporter-token-w62')
    assert.equal(leaked.length, 0)
  } finally {
    await srv.close()
    await new Promise(resolve => sink.close(() => resolve()))
  }
})

test('puts the document with host and the reporter token, and prints nothing', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-ok-'))
  const file = write(dir, 'status.json', JSON.stringify({ at: 1, verdict: '都正常', level: 'run' }))
  const srv = await listen()
  try {
    const result = await run(file, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'reporter-token-w62' }))
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(result.out.includes('reporter-token-w62'), false)
    assert.equal(result.err.includes('reporter-token-w62'), false)
    assert.equal(srv.requests.length, 1)
    const req = srv.requests[0]
    assert.equal(req.method, 'PUT')
    assert.equal(req.url, '/api/v1/agent/progress')
    assert.equal(req.auth, 'Bearer reporter-token-w62')
    assert.equal(req.type, 'application/json')
    const doc = JSON.parse(req.body.toString('utf8'))
    assert.equal(doc.verdict, '都正常')
    assert.equal(doc.level, 'run')
    assert.equal(doc.at, 1)
    assert.equal(doc.host, expectedHost())
  } finally {
    await srv.close()
  }
})

test('reads the reporter token from the lineage token file and does not print it', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-file-token-'))
  const tokenHome = path.join(dir, 'home')
  fs.mkdirSync(path.join(tokenHome, '.config', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(tokenHome, '.config', 'bifrost', 'lineage-reporter.token'), 'file-token-w62\nsecond-line\n')
  const file = write(dir, 'status.json', '{"at":2}')
  const srv = await listen()
  try {
    const result = await run(
      file,
      childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, BIFROST_HOME_OVERRIDE: tokenHome }),
    )
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(result.out.includes('file-token-w62'), false)
    assert.equal(result.err.includes('file-token-w62'), false)
    assert.equal(srv.requests.length, 1)
    assert.equal(srv.requests[0].auth, 'Bearer file-token-w62')
  } finally {
    await srv.close()
  }
})

test('no token sends no request', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-notoken-'))
  const file = write(dir, 'status.json', '{"at":1}')
  const srv = await listen()
  try {
    const result = await run(file, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url }))
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(srv.requests.length, 0)
  } finally {
    await srv.close()
  }
})

test('a missing file sends no request', async () => {
  const srv = await listen()
  try {
    const missing = path.join(os.tmpdir(), 'progress-missing', 'no-such-status.json')
    const result = await run(missing, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(srv.requests.length, 0)
  } finally {
    await srv.close()
  }
})

test('an unreadable file sends no request', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-unreadable-'))
  const file = write(dir, 'status.json', '{"at":1}')
  fs.chmodSync(file, 0)
  let readable = true
  try {
    fs.readFileSync(file)
  } catch {
    readable = false
  }
  assert.equal(readable, false)
  const srv = await listen()
  try {
    const result = await run(file, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(srv.requests.length, 0)
  } finally {
    fs.chmodSync(file, 0o644)
    await srv.close()
  }
})

test('a file that is not JSON sends no request', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-badjson-'))
  const file = write(dir, 'status.json', '{')
  const srv = await listen()
  try {
    const result = await run(file, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(srv.requests.length, 0)
  } finally {
    await srv.close()
  }
})

test('a file over 256 KiB sends no request, and exactly 256 KiB does', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-size-'))
  const prefix = '{"at":1,"v":"'
  const suffix = '"}'
  const room = 256 * 1024 - Buffer.byteLength(prefix) - Buffer.byteLength(suffix)
  const exact = write(dir, 'exact.json', prefix + 'a'.repeat(room) + suffix)
  assert.equal(fs.statSync(exact).size, 256 * 1024)
  const over = write(dir, 'over.json', prefix + 'a'.repeat(room + 1) + suffix)
  assert.ok(fs.statSync(over).size > 256 * 1024)
  const srv = await listen()
  try {
    const tooBig = await run(over, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    assert.equal(tooBig.code, 0)
    assert.equal(tooBig.out, '')
    assert.equal(tooBig.err, '')
    assert.equal(srv.requests.length, 0)
    const fit = await run(exact, childEnv({ PLATFORM_HEARTBEAT_URL: srv.url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    assert.equal(fit.code, 0)
    assert.equal(fit.out, '')
    assert.equal(srv.requests.length, 1)
    const doc = JSON.parse(srv.requests[0].body.toString('utf8'))
    assert.equal(doc.at, 1)
    assert.equal(doc.host, expectedHost())
  } finally {
    await srv.close()
  }
})

test('gives up after 5 seconds and still prints nothing', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'progress-hang-'))
  const file = write(dir, 'status.json', '{"at":1}')
  const requests = []
  const server = http.createServer(req => {
    requests.push(req.url)
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const addr = server.address()
  const url = `http://127.0.0.1:${addr.port}`
  const start = Date.now()
  try {
    const result = await run(file, childEnv({ PLATFORM_HEARTBEAT_URL: url, PLATFORM_REPORTER_TOKEN: 'tok' }))
    const elapsed = Date.now() - start
    assert.equal(result.code, 0)
    assert.equal(result.out, '')
    assert.equal(result.err, '')
    assert.equal(result.out.includes('tok'), false)
    assert.ok(requests.length >= 1)
    assert.ok(elapsed >= 4500 && elapsed < 8000, `elapsed ${elapsed}`)
  } finally {
    await new Promise(resolve => server.close(() => resolve()))
  }
})
