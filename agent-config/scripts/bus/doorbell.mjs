#!/usr/bin/env node
// Doorbell: wait on the bus for the event a seat is waiting for, then exit.
//
// A seat that ends its turn while it waits on something (a card decided, a CI
// run finished, a commit on main, an alert in its namespace) runs this as a
// background command. When the event arrives the command exits, and the app
// wakes the seat with the command's output; nobody has to look in on it.
// (2026-11-16: the lanes stopped and were nudged by the coordinator and the
// duty seat every 30 minutes; the events they waited on were already on the
// bus.)
//
//   node scripts/bus/doorbell.mjs --types ci.run.finished --match bifrost-ci-platform --timeout 3600
//   node scripts/bus/doorbell.mjs --types git.main.advanced,ci.verdict.changed --match 4277484d
//   --server bifrost-platform-stg   (another platform entry of .mcp.json; default bifrost-platform)
//
// It speaks to the platform through the project's MCP server process (the
// bifrost-platform entry of .mcp.json), which holds its own credentials; this
// script never reads a token. Run it from the workspace root, or set
// BIFROST_WORKSPACE.
//
// --seat <name> --waits-dir <dir>: while it waits, the doorbell keeps
// <dir>/<name>.json ({seat, types, match, since, until, pid}) and removes it on
// exit, so whoever looks in on the seats (the duty seat's check) sees that
// this one is armed and does not push it.
//
// Output: one line "DOORBELL <type> <subject> <cursor>" and exit 0 when an
// event arrives; "DOORBELL timeout ... --after <cursor>" and exit 2 when the
// time runs out (re-arm with --after to miss nothing); exit 1 on an error.
import { readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const args = process.argv.slice(2)
const opt = (name, dflt) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && i + 1 < args.length ? args[i + 1] : dflt
}
const types = opt('types', '')
const match = opt('match', '')
const timeout = Number(opt('timeout', '3600'))
let after = opt('after', '')
const label = opt('client', 'doorbell').slice(0, 40)
const server = opt('server', 'bifrost-platform')
const seat = opt('seat', '')
const waitsDir = opt('waits-dir', '')
if (seat && !/^[A-Za-z0-9._-]{1,80}$/.test(seat)) {
  console.error('doorbell: --seat is 1 to 80 letters, digits, dots, dashes or underscores')
  process.exit(1)
}
if (!types || !Number.isFinite(timeout) || timeout < 0) {
  console.error('usage: doorbell.mjs --types <t1,t2> [--match <subject substring>] [--timeout <s>] [--after <cursor>] [--client <name>]')
  process.exit(1)
}

const ws = process.env.BIFROST_WORKSPACE || process.cwd()
const srv = join(ws, 'bifrost-platform', 'mcp', 'platform')
const sdk = join(srv, 'node_modules', '@modelcontextprotocol', 'sdk', 'dist', 'esm')
let cfg
try {
  cfg = JSON.parse(readFileSync(join(ws, '.mcp.json'), 'utf8')).mcpServers[server]
  if (!cfg) throw new Error(`no ${server} entry`)
} catch (e) {
  console.error(`doorbell: cannot read the ${server} entry of ${join(ws, '.mcp.json')}: ${e.message}`)
  process.exit(1)
}
const expand = (s, env) => String(s).replace(/\$\{([A-Za-z0-9_]+)(:-([^}]*))?\}/g, (_, k, __, d) => env[k] ?? d ?? '')
const env = { ...process.env, BIFROST_WORKSPACE: ws, BIFROST_MCP_NO_PRESENCE: '1' }
for (const [k, v] of Object.entries(cfg.env || {})) env[k] = expand(v, env)

const { Client } = await import(join(sdk, 'client', 'index.js'))
const { StdioClientTransport } = await import(join(sdk, 'client', 'stdio.js'))
const transport = new StdioClientTransport({ command: process.execPath, args: ['--import', 'tsx', 'src/index.ts'], cwd: srv, env, stderr: 'ignore' })
const client = new Client({ name: 'doorbell', version: '1' })
await client.connect(transport)

const deadline = Date.now() + timeout * 1000
const waitFile = seat && waitsDir ? join(waitsDir, `${seat}.json`) : ''
if (waitFile) {
  mkdirSync(waitsDir, { recursive: true })
  writeFileSync(waitFile, JSON.stringify({ seat, types, match, since: new Date().toISOString(), until: new Date(deadline).toISOString(), pid: process.pid }) + '\n')
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { rmSync(waitFile, { force: true }); process.exit(130) })
}
let failures = 0
try {
  for (;;) {
    const left = Math.floor((deadline - Date.now()) / 1000)
    if (left <= 0) {
      console.log(`DOORBELL timeout: no ${types}${match ? ` matching ${match}` : ''} in ${timeout} s; re-arm with --after ${after}`)
      process.exitCode = 2
      break
    }
    let j
    try {
      const r = await client.callTool({
        name: 'wait_for_event',
        arguments: { types, wait_seconds: Math.min(25, left), client: label, ...(match ? { match } : {}), ...(after ? { after } : {}) },
      })
      const txt = r.content?.find((x) => x.type === 'text')?.text ?? ''
      j = JSON.parse(txt)
      failures = 0
    } catch (e) {
      // A restart of the platform or a dropped call is not the event: try
      // again a few times before giving up, so the seat is not woken for it.
      if (++failures >= 5) {
        console.log(`DOORBELL error: ${e.message}; re-arm with --after ${after}`)
        process.exitCode = 1
        break
      }
      await new Promise((r) => setTimeout(r, 5000))
      continue
    }
    if (j.error) {
      console.log(`DOORBELL error: ${j.error}`)
      process.exitCode = 1
      break
    }
    if (j.next) after = j.next
    const ev = (j.events || [])[0]
    if (ev) {
      console.log(`DOORBELL ${ev.type} ${ev.subject} ${ev.cursor || after}`)
      break
    }
  }
} finally {
  if (waitFile) rmSync(waitFile, { force: true })
  await client.close()
}
