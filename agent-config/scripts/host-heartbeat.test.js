'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')
const test = require('node:test')

const SCRIPT = path.join(__dirname, 'host-heartbeat.js')
const HEARTBEAT = path.join(__dirname, 'thread-heartbeat.js')
const { buildReport } = require('./host-heartbeat.js')

function commandFor(vendor, script = HEARTBEAT) {
  return `node ${JSON.stringify(script)} hook ${vendor}`
}

function claudeSettings(command) {
  return JSON.stringify({ hooks: { PreToolUse: [{ hooks: [{ type: 'command', command }] }] } })
}

function cursorHooks(command) {
  return JSON.stringify({ version: 1, hooks: { preToolUse: [{ command }] } })
}
const installer = require('./install-host-heartbeat.js')

function freshHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'host-hb-'))
  const workspace = path.join(home, 'ws')
  fs.mkdirSync(workspace, { recursive: true })
  return { home, workspace }
}

function withEnv(home, workspace, extra, fn) {
  const prev = {
    BIFROST_HOME_OVERRIDE: process.env.BIFROST_HOME_OVERRIDE,
    BIFROST_WORKSPACE: process.env.BIFROST_WORKSPACE,
    PLATFORM_REPORTER_TOKEN: process.env.PLATFORM_REPORTER_TOKEN,
    CODEX_HOME: process.env.CODEX_HOME,
  }
  process.env.BIFROST_HOME_OVERRIDE = home
  process.env.BIFROST_WORKSPACE = workspace
  delete process.env.PLATFORM_REPORTER_TOKEN
  delete process.env.CODEX_HOME
  Object.assign(process.env, extra)
  try {
    return fn()
  } finally {
    for (const [k, v] of Object.entries(prev)) {
      if (v === undefined) delete process.env[k]
      else process.env[k] = v
    }
  }
}

test('a vendor with no wiring and no token is not monitored', () => {
  const { home, workspace } = freshHome()
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.claude.wired, false)
  assert.equal(report.vendors.claude.token, false)
  assert.equal(report.vendors.cursor.wired, false)
  assert.equal(report.vendors.codex.wired, false)
  assert.ok(report.host)
})

test('wiring is the hook command, and the token is the reporter file', () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.claude'), { recursive: true })
  fs.writeFileSync(path.join(home, '.claude', 'settings.json'), claudeSettings(commandFor('claude')))
  fs.mkdirSync(path.join(workspace, '.cursor'), { recursive: true })
  fs.writeFileSync(path.join(workspace, '.cursor', 'hooks.json'), cursorHooks(commandFor('cursor')))
  fs.mkdirSync(path.join(home, '.config', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(home, '.config', 'bifrost', 'lineage-reporter.token'), 'reporter-token\n')
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.claude.wired, true)
  assert.equal(report.vendors.claude.token, true)
  assert.equal(report.vendors.cursor.wired, true)
  assert.equal(report.vendors.cursor.token, true)
  assert.equal(report.vendors.codex.wired, false, 'a missing codex hooks.json is not wired')
  assert.equal(JSON.stringify(report).includes('reporter-token'), false)
})

test('a substring or a repository template is not wired', () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.claude'), { recursive: true })
  fs.writeFileSync(
    path.join(home, '.claude', 'settings.json'),
    claudeSettings('echo thread-heartbeat.js hook claude'),
  )
  fs.mkdirSync(path.join(workspace, 'agent-config', 'cursor'), { recursive: true })
  fs.writeFileSync(path.join(workspace, 'agent-config', 'cursor', 'hooks.json'), cursorHooks(commandFor('cursor')))
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.claude.wired, false, 'a command that only mentions the script is not wired')
  assert.equal(report.vendors.cursor.wired, false, 'agent-config/cursor/hooks.json is a template, not effective config')
})

test('the hook command must target this script and this vendor', () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.codex'), { recursive: true })
  fs.writeFileSync(path.join(home, '.codex', 'hooks.json'), claudeSettings(commandFor('claude')))
  fs.mkdirSync(path.join(home, '.cursor'), { recursive: true })
  fs.writeFileSync(
    path.join(home, '.cursor', 'hooks.json'),
    cursorHooks(`echo ${JSON.stringify(HEARTBEAT)} hook cursor`),
  )
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.codex.wired, false, 'hook claude does not wire codex')
  assert.equal(report.vendors.cursor.wired, false, 'echoing the real path is not running it')
  assert.equal(report.vendors.claude.wired, false, 'a codex file is not claude effective config')
})

test('echo, and hook not immediately after the script, are not wired', () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.cursor'), { recursive: true })
  fs.writeFileSync(
    path.join(home, '.cursor', 'hooks.json'),
    cursorHooks(`echo node ${JSON.stringify(HEARTBEAT)} hook cursor`),
  )
  fs.mkdirSync(path.join(home, '.claude'), { recursive: true })
  fs.writeFileSync(
    path.join(home, '.claude', 'settings.json'),
    claudeSettings(`node ${JSON.stringify(HEARTBEAT)} ignored hook claude`),
  )
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.cursor.wired, false, 'echo node <script> hook cursor only prints the line')
  assert.equal(report.vendors.claude.wired, false, 'hook claude is not the argument pair immediately after the script')
  fs.writeFileSync(
    path.join(home, '.cursor', 'hooks.json'),
    cursorHooks(`node ${JSON.stringify(HEARTBEAT)} hook cursor --extra`),
  )
  const extra = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(extra.vendors.cursor.wired, false, 'arguments after hook <vendor> are not the supported call')
})

test('a symlinked Cursor project hooks file is not wired, and the user file is', () => {
  const { home, workspace } = freshHome()
  const realDir = path.join(home, 'real-cursor')
  fs.mkdirSync(realDir, { recursive: true })
  fs.writeFileSync(path.join(realDir, 'hooks.json'), cursorHooks(commandFor('cursor')))
  fs.mkdirSync(path.join(workspace, '.cursor'), { recursive: true })
  fs.symlinkSync(path.join(realDir, 'hooks.json'), path.join(workspace, '.cursor', 'hooks.json'))
  const linked = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(linked.vendors.cursor.wired, false, 'Cursor does not load a project hooks.json reached through a symlink')
  fs.mkdirSync(path.join(home, '.cursor'), { recursive: true })
  fs.writeFileSync(path.join(home, '.cursor', 'hooks.json'), cursorHooks(commandFor('cursor')))
  const user = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(user.vendors.cursor.wired, true, 'the user-level Cursor hooks file still counts')
})

test('another vendor\'s hook command does not count', () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.codex'), { recursive: true })
  fs.writeFileSync(path.join(home, '.codex', 'hooks.json'), claudeSettings(commandFor('claude')))
  const report = withEnv(home, workspace, {}, () => buildReport())
  assert.equal(report.vendors.codex.wired, false)
  assert.equal(report.vendors.claude.wired, false)
})

function runScript(env) {
  return new Promise(resolve => {
    const p = spawn(process.execPath, [SCRIPT], { env: { ...process.env, ...env } })
    let out = ''
    p.stdout.on('data', d => (out += d))
    p.on('exit', code => resolve({ code, out }))
  })
}

function server(status, payload) {
  const got = []
  const s = http.createServer((req, res) => {
    let b = ''
    req.on('data', d => (b += d))
    req.on('end', () => {
      got.push(JSON.parse(b || '{}'))
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(typeof payload === 'string' ? payload : JSON.stringify(payload))
    })
  })
  return new Promise(resolve => s.listen(0, '127.0.0.1', () => resolve({ s, got, url: `http://127.0.0.1:${s.address().port}` })))
}

test('no token, a down server and a bad response all exit 0', async () => {
  const { home } = freshHome()
  const none = await runScript({ BIFROST_HOME_OVERRIDE: home, PLATFORM_HEARTBEAT_URL: 'http://127.0.0.1:9' })
  assert.equal(none.code, 0)
  assert.equal(none.out, '')
  const down = await runScript({
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: 't',
    PLATFORM_HEARTBEAT_URL: 'http://127.0.0.1:9',
  })
  assert.equal(down.code, 0)
  const bad = await server(500, 'not-json')
  const got = await runScript({
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: 't',
    PLATFORM_HEARTBEAT_URL: bad.url,
  })
  assert.equal(got.code, 0)
  bad.s.close()
})

test('without a token the script sends nothing', async () => {
  const { home } = freshHome()
  const srv = await server(202, { ok: true })
  const result = await runScript({
    BIFROST_HOME_OVERRIDE: home,
    PLATFORM_REPORTER_TOKEN: '',
    PLATFORM_HEARTBEAT_URL: srv.url,
  })
  assert.equal(result.code, 0)
  await new Promise(r => setTimeout(r, 50))
  assert.equal(srv.got.length, 0)
  srv.s.close()
})

test('a successful post describes every vendor and does not send the token', async () => {
  const { home, workspace } = freshHome()
  fs.mkdirSync(path.join(home, '.claude'), { recursive: true })
  fs.writeFileSync(path.join(home, '.claude', 'settings.json'), claudeSettings(commandFor('claude')))
  const srv = await server(202, { ok: true })
  const result = await runScript({
    BIFROST_HOME_OVERRIDE: home,
    BIFROST_WORKSPACE: workspace,
    PLATFORM_REPORTER_TOKEN: 'reporter-token',
    PLATFORM_HEARTBEAT_URL: srv.url,
  })
  assert.equal(result.code, 0)
  await new Promise(r => setTimeout(r, 50))
  assert.equal(srv.got.length, 1)
  assert.equal(srv.got[0].vendors.claude.wired, true)
  assert.equal(srv.got[0].vendors.claude.token, true)
  assert.equal(srv.got[0].vendors.cursor.wired, false)
  assert.equal(srv.got[0].vendors.codex.token, true)
  assert.equal(JSON.stringify(srv.got[0]).includes('reporter-token'), false)
  srv.s.close()
})

test('the installer writes a LaunchAgent and does not load it', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'host-hb-install-'))
  const dest = installer.install({
    home,
    node: '/opt/homebrew/bin/node',
    script: '/work/agent-config/scripts/host-heartbeat.js',
  })
  assert.equal(dest, path.join(home, 'Library', 'LaunchAgents', 'com.bifrost.host-heartbeat.plist'))
  const text = fs.readFileSync(dest, 'utf8')
  assert.match(text, /<key>StartInterval<\/key>\s*<integer>60<\/integer>/)
  assert.match(text, /com\.bifrost\.host-heartbeat/)
  assert.match(text, /\/opt\/homebrew\/bin\/node/)
  assert.match(text, /host-heartbeat\.js/)
  assert.equal(text.includes('launchctl'), false)
  assert.equal(fs.readFileSync(path.join(__dirname, 'install-host-heartbeat.js'), 'utf8').includes('child_process'), false)
  const escaped = installer.renderPlist({ node: '/usr/bin/node', script: '/tmp/a&b.js' })
  assert.match(escaped, /\/tmp\/a&amp;b\.js/)
})
