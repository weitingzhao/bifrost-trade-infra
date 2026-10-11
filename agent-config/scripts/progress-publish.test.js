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

test('the reporter token is not exported', () => {
  const hb = require('./thread-heartbeat.js')
  assert.equal(Object.hasOwn(hb, 'token'), false)
  assert.equal(typeof hb.reporterRequest, 'function')
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
