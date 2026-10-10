#!/usr/bin/env node
'use strict'
/**
 * Host heartbeat (W-57). Launchd runs this once a minute. It posts the host
 * name and, for claude, cursor and codex, whether that vendor's hook wiring is
 * present and whether the reporter token is readable.
 *
 *   node host-heartbeat.js
 *
 * A missing token, a down server or a bad response still exits 0. This script
 * does not install or load the launchd job.
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

function configFiles(vendor) {
  const root = process.env.BIFROST_WORKSPACE || ''
  const files = []
  if (vendor === 'claude') {
    files.push(home('.claude', 'settings.json'))
    if (root) {
      files.push(path.join(root, 'agent-config', 'claude', 'settings.json'))
      files.push(path.join(root, '.claude', 'settings.json'))
    }
  } else if (vendor === 'cursor') {
    files.push(home('.cursor', 'hooks.json'))
    if (root) {
      files.push(path.join(root, 'agent-config', 'cursor', 'hooks.json'))
      files.push(path.join(root, '.cursor', 'hooks.json'))
    }
  } else if (vendor === 'codex') {
    files.push(path.join(process.env.CODEX_HOME || home('.codex'), 'hooks.json'))
    if (root) files.push(path.join(root, 'agent-config', 'codex', 'hooks.json'))
  }
  return files
}

function scriptPresent() {
  return fs.existsSync(path.join(__dirname, SCRIPT_NAME))
}

/** Wired only when this script's sibling exists and a config runs it for this vendor. */
function wired(vendor) {
  if (!scriptPresent()) return false
  const needle = `hook ${vendor}`
  for (const file of configFiles(vendor)) {
    let text = ''
    try {
      text = fs.readFileSync(file, 'utf8')
    } catch {
      continue
    }
    if (text.includes(SCRIPT_NAME) && text.includes(needle)) return true
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

module.exports = { buildReport, wired, tokenReadable, VENDORS }
