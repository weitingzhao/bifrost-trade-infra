#!/usr/bin/env node
'use strict'
/**
 * Host heartbeat (W-57). Launchd runs this once a minute. It posts the host
 * name and, for claude, cursor and codex, whether that vendor's hook wiring is
 * present and whether the reporter token is readable.
 *
 *   node host-heartbeat.js
 *
 * A missing token, a down server or a bad response still exits 0. With no
 * reporter token this script cannot report: it sends nothing, so the server
 * has no heartbeat for the host. An expected host is shown as never reported
 * only when the API's PLATFORM_AGENT_THREAD_EXPECTED_HOSTS lists it. This
 * script does not invent that row, and it does not install or load the
 * launchd job.
 *
 * Wired means a vendor's effective hook configuration has a command that is
 * exactly the supported call: the interpreter (`node` or `nodejs`), then the
 * real path of thread-heartbeat.js, then `hook <vendor>` and nothing after it.
 * A substring, an earlier token, or `hook <vendor>` later in the line is not
 * enough. Codex trust is not checked here; that needs a credential per host.
 *
 * Only files that vendor loads are read. For Cursor that is the user-level
 * hooks file, plus a project hooks file that is not reached through a symlink
 * (Cursor refuses a project hooks.json reached through a symlink below the
 * workspace root). Claude's user settings.local.json is not a file Claude
 * loads. An agent-config template is not effective config.
 *
 * Config (nothing secret is printed):
 *   PLATFORM_HEARTBEAT_URL    platform-api base (default: PROD VIP NodePort)
 *   PLATFORM_REPORTER_TOKEN   or the first line of
 *   ~/.config/bifrost/lineage-reporter.token
 *   BIFROST_WORKSPACE         workspace whose agent-config is also checked
 *   BIFROST_HEARTBEAT=off     send nothing
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const DEFAULT_URL = 'http://192.168.10.100:30876'
const ROUTE = '/api/v1/agent/hosts/heartbeat'
const VENDORS = ['claude', 'cursor', 'codex']
const SCRIPT_NAME = 'thread-heartbeat.js'

function home(...p) {
  return path.join(process.env.BIFROST_HOME_OVERRIDE || os.homedir(), ...p)
}

function tokenText() {
  if (process.env.PLATFORM_REPORTER_TOKEN) return process.env.PLATFORM_REPORTER_TOKEN.trim()
  try {
    return fs.readFileSync(home('.config', 'bifrost', 'lineage-reporter.token'), 'utf8').split('\n')[0].trim()
  } catch {
    return ''
  }
}

function tokenReadable() {
  return tokenText() !== ''
}

function baseURL() {
  return (process.env.PLATFORM_HEARTBEAT_URL || DEFAULT_URL).replace(/\/+$/, '')
}

function hostName() {
  return (os.hostname().split('.')[0] || 'unknown').replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

function effectiveConfigs(vendor) {
  const root = process.env.BIFROST_WORKSPACE || ''
  const files = []
  if (vendor === 'claude') {
    files.push(home('.claude', 'settings.json'))
    if (root) {
      files.push(path.join(root, '.claude', 'settings.json'))
      files.push(path.join(root, '.claude', 'settings.local.json'))
    }
  } else if (vendor === 'cursor') {
    files.push(home('.cursor', 'hooks.json'))
    if (root) files.push(path.join(root, '.cursor', 'hooks.json'))
  } else if (vendor === 'codex') {
    files.push(path.join(process.env.CODEX_HOME || home('.codex'), 'hooks.json'))
  }
  return files
}

function projectBase(file) {
  const dir = path.dirname(file)
  const base = path.basename(dir)
  if (base === '.claude' || base === '.cursor' || base === '.codex') return path.dirname(dir)
  return process.env.BIFROST_WORKSPACE || ''
}

function hookCommands(parsed) {
  if (!parsed || typeof parsed !== 'object' || !parsed.hooks || typeof parsed.hooks !== 'object') return []
  const commands = []
  for (const entries of Object.values(parsed.hooks)) {
    if (!Array.isArray(entries)) continue
    for (const entry of entries) {
      if (!entry || typeof entry !== 'object') continue
      if (typeof entry.command === 'string') commands.push(entry.command)
      if (Array.isArray(entry.hooks)) {
        for (const inner of entry.hooks) {
          if (inner && typeof inner.command === 'string') commands.push(inner.command)
        }
      }
    }
  }
  return commands
}

function tokenize(command) {
  const out = []
  let cur = ''
  let quote = ''
  for (let i = 0; i < command.length; i++) {
    const c = command[i]
    if (quote) {
      if (c === quote) quote = ''
      else cur += c
      continue
    }
    if (c === '"' || c === "'") {
      quote = c
      continue
    }
    if (c === '\\' && i + 1 < command.length) {
      cur += command[++i]
      continue
    }
    if (/\s/.test(c)) {
      if (cur) out.push(cur)
      cur = ''
      continue
    }
    cur += c
  }
  if (cur) out.push(cur)
  return out
}

function expandToken(token, bases) {
  return token.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)/g, (full, name, def, simple) => {
    const key = name || simple
    if (key === 'CLAUDE_PROJECT_DIR') return bases.project || ''
    if (key === 'HOME') return bases.home
    if (process.env[key]) return process.env[key]
    if (def != null) return expandToken(def, bases)
    return ''
  })
}

function heartbeatScript() {
  return path.resolve(__dirname, SCRIPT_NAME)
}

/**
 * Cursor refuses a project hooks file reached through a symlink below the
 * workspace root. The workspace root itself is not walked: a /var → /private/var
 * prefix must not look like that refusal. The user-level file is not checked here.
 */
function reachedThroughSymlink(file, root) {
  let cur = path.resolve(file)
  const stop = root ? path.resolve(root) : path.dirname(cur)
  while (cur !== stop) {
    let st
    try {
      st = fs.lstatSync(cur)
    } catch {
      return true
    }
    if (st.isSymbolicLink()) return true
    const parent = path.dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  return false
}

function configCounts(vendor, file) {
  if (vendor !== 'cursor') return true
  if (path.resolve(file) === path.resolve(home('.cursor', 'hooks.json'))) return true
  return !reachedThroughSymlink(file, projectBase(file))
}

function commandWires(command, vendor, bases) {
  const tokens = tokenize(command).map(t => expandToken(t, bases))
  // Interpreter, real script path, then `hook <vendor>` immediately, and no further arguments.
  if (tokens.length !== 4) return false
  const interp = path.basename(tokens[0])
  if (interp !== 'node' && interp !== 'nodejs') return false
  if (path.basename(tokens[1]) !== SCRIPT_NAME) return false
  if (tokens[2] !== 'hook' || tokens[3] !== vendor) return false
  const script = tokens[1]
  const resolved = path.isAbsolute(script) ? script : path.resolve(bases.project || '', script)
  try {
    return fs.realpathSync(heartbeatScript()) === fs.realpathSync(resolved)
  } catch {
    return false
  }
}

/** Wired only when an effective config runs this script for this vendor, by real path. */
function wired(vendor) {
  const basesHome = home()
  for (const file of effectiveConfigs(vendor)) {
    if (!configCounts(vendor, file)) continue
    let parsed
    try {
      parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
    } catch {
      continue
    }
    const bases = { home: basesHome, project: projectBase(file) }
    for (const command of hookCommands(parsed)) {
      if (commandWires(command, vendor, bases)) return true
    }
  }
  return false
}

function buildReport() {
  const token = tokenReadable()
  const vendors = {}
  for (const vendor of VENDORS) vendors[vendor] = { wired: wired(vendor), token }
  return { host: hostName(), vendors }
}

async function post(body) {
  const tok = tokenText()
  if (!tok || process.env.BIFROST_HEARTBEAT === 'off') return { sent: false }
  const res = await fetch(`${baseURL()}${ROUTE}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  })
  return { sent: res.ok, status: res.status }
}

async function main() {
  try {
    await post(buildReport())
  } catch {
    // a missed host beat is the server's to notice
  }
  return 0
}

if (require.main === module) {
  process.on('uncaughtException', () => process.exit(0))
  process.on('unhandledRejection', () => process.exit(0))
  main().then(
    code => process.exit(code),
    () => process.exit(0),
  )
}

module.exports = { buildReport, wired, tokenReadable, commandWires, VENDORS }
