#!/usr/bin/env node
'use strict'
/**
 * Write the host-heartbeat launchd plist into the user's LaunchAgents.
 * The plist environment sets BIFROST_WORKSPACE to this checkout's workspace.
 * It does not bootstrap or start the job.
 *
 *   node install-host-heartbeat.js
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { findWorkspace } = require('./host-heartbeat.js')

const LABEL = 'com.bifrost.host-heartbeat'

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderPlist({ node, script, workspace }) {
  const template = fs.readFileSync(path.join(__dirname, 'com.bifrost.host-heartbeat.plist'), 'utf8')
  return template
    .replaceAll('__NODE__', xmlEscape(node))
    .replaceAll('__SCRIPT__', xmlEscape(script))
    .replaceAll('__WORKSPACE__', xmlEscape(workspace))
}

/** Write the plist and return its path. Does not call launchctl. */
function install({ home, node, script, workspace }) {
  const root = workspace || process.env.BIFROST_WORKSPACE || findWorkspace(__dirname)
  const destDir = path.join(home, 'Library', 'LaunchAgents')
  fs.mkdirSync(destDir, { recursive: true, mode: 0o755 })
  const dest = path.join(destDir, `${LABEL}.plist`)
  const body = renderPlist({ node, script, workspace: root })
  const tmp = `${dest}.${process.pid}.tmp`
  fs.writeFileSync(tmp, body, { mode: 0o644 })
  fs.renameSync(tmp, dest)
  fs.chmodSync(dest, 0o644)
  return dest
}

if (require.main === module) {
  const home = process.env.BIFROST_HOME_OVERRIDE || os.homedir()
  const dest = install({
    home,
    node: process.execPath,
    script: path.join(__dirname, 'host-heartbeat.js'),
    workspace: process.env.BIFROST_WORKSPACE || findWorkspace(__dirname),
  })
  process.stdout.write(
    `wrote ${dest}\n` +
      'The job is not loaded. To load it yourself:\n' +
      `  launchctl bootstrap gui/$(id -u) ${dest}\n`,
  )
}

module.exports = { install, renderPlist, LABEL }
