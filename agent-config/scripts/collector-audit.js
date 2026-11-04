#!/usr/bin/env node
'use strict'
/**
 * Collector audit (R5:5.5-12 §9; S1-5 part): read-only, local files only.
 *
 *   node collector-audit.js              launches and their gaps, as JSON
 *   node collector-audit.js --preflight  mode, platform URL, host id: exit 1 on a problem
 *
 * The denominator is the launcher's own record, not the hooks (§9, C13): a
 * launch whose `sessions` is empty is the gap `launch_without_sessions`
 * (hooks off, collector mode off, or every hook lost), whatever the hooks say.
 * For each recorded (session, epoch): the end gaps of its epochs, and its
 * registration as the single writer left it: registered, refused, or
 * pending (a linked launch whose registration has not arrived: §13 I6's
 * "waiting for registration", which the platform has no reason for yet).
 * Nothing is sent; tokens are never read back or printed.
 */
const fs = require('node:fs')
const path = require('node:path')
const collector = require('./collector-session.js')
const epochs = require('./collector-epochs.js')
const { workState } = require('./collector-launch.js')

const LAUNCH_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

function registration(mode, state) {
  if (state && state.id) return 'registered'
  if (state && state.failed) return 'refused'
  return mode === 'linked' ? 'pending' : 'none'
}

function audit() {
  const root = epochs.home('.cache', 'bifrost', 'external-work', 'launches')
  let ids = []
  try {
    ids = fs.readdirSync(root).filter(n => LAUNCH_RE.test(n)).sort()
  } catch {
    ids = []
  }
  const launches = []
  for (const id of ids) {
    const rec = readJSON(path.join(root, id, 'launch.json'))
    if (!rec) {
      launches.push({ launch_id: id, gaps: ['launch_unreadable'] })
      continue
    }
    const sessions = Array.isArray(rec.sessions) ? rec.sessions : []
    const gaps = sessions.length ? [] : ['launch_without_sessions']
    const works = sessions.map(s => {
      const st = epochs.loadEpochs(path.join(epochs.sessionDir(s.vendor, s.session) || '/nonexistent', 'epochs.json'))
      const endGaps = epochs.endGaps(st).filter(g => g.epoch === s.epoch).map(g => g.kind)
      return { vendor: s.vendor, session: s.session, epoch: s.epoch, registration: registration(rec.mode, workState(s.vendor, s.session, s.epoch)), end_gaps: endGaps }
    })
    if (rec.mode === 'linked' && works.some(w => w.registration !== 'registered')) gaps.push('work_not_registered')
    if (works.some(w => w.end_gaps.length)) gaps.push('session_end_gap')
    launches.push({ launch_id: id, mode: rec.mode, started_at: rec.started_at, sessions: sessions.length, gaps, works })
  }
  return { launches, launches_with_gaps: launches.filter(l => l.gaps.length).length }
}

function preflight() {
  const d = collector.diagnose()
  const problems = [...d.problems]
  if (d.mode === 'collector' && !process.env.PLATFORM_HEARTBEAT_URL) problems.push('url_default')
  return { ...d, url: process.env.PLATFORM_HEARTBEAT_URL ? 'configured' : 'default', problems }
}

if (require.main === module) {
  const pre = process.argv[2] === '--preflight'
  const out = pre ? preflight() : audit()
  process.stdout.write(`${JSON.stringify(out, null, 2)}\n`)
  process.exit(pre && out.problems.length ? 1 : 0)
}

module.exports = { audit, preflight }
