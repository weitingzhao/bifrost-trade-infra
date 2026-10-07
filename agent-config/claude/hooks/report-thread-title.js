'use strict'
/**
 * Report this session's title to the Ops Platform (TD-197).
 *
 * Claude Code appends a `custom-title` record to the session transcript when the
 * user renames the thread, and an `ai-title` record when it names one itself.
 * Commit Lineage names threads by transcript id, so the session reports its own
 * current title (custom wins over generated) — from any machine, without the
 * workstation syncer in the local platform-api (which stays as backfill for
 * threads renamed while idle).
 *
 * Cheap on every Stop: only bytes appended since the last read are scanned
 * (offset kept in ~/.cache/bifrost/lineage-titles.json), and the title is sent
 * only when it changed since the last successful report.
 *
 * Config (nothing secret lives in the repo):
 *   PLATFORM_LINEAGE_URL      platform-api base (default: PROD NodePort)
 *   PLATFORM_REPORTER_TOKEN   reporter-role token, or the first line of
 *   ~/.config/bifrost/lineage-reporter.token   (chmod 600)
 * No token → nothing is sent. Every failure is swallowed: a hook never blocks a session.
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const DEFAULT_URL = 'http://192.168.10.73:30876' // bifrost-platform-prod platform-api NodePort
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const CHUNK = 4 * 1024 * 1024

function home(...p) {
  return path.join(process.env.BIFROST_HOME_OVERRIDE || os.homedir(), ...p)
}

function readState(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return {}
  }
}

function writeState(file, state) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    const tmp = `${file}.${process.pid}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(state))
    fs.renameSync(tmp, file)
  } catch {
    // a lost offset only means a re-scan next time
  }
}

function token() {
  if (process.env.PLATFORM_REPORTER_TOKEN) return process.env.PLATFORM_REPORTER_TOKEN.trim()
  try {
    return fs.readFileSync(home('.config', 'bifrost', 'lineage-reporter.token'), 'utf8').split('\n')[0].trim()
  } catch {
    return ''
  }
}

/**
 * Scan transcript bytes from `st.offset` to the last complete line and update
 * st.custom / st.ai / st.offset. Returns the current title ('' if none yet).
 */
function scan(file, st) {
  let size
  try {
    size = fs.statSync(file).size
  } catch {
    return ''
  }
  if (!(st.offset >= 0) || st.offset > size) Object.assign(st, { offset: 0, custom: '', ai: '' })
  const fd = fs.openSync(file, 'r')
  try {
    let pos = st.offset
    let carry = ''
    const buf = Buffer.alloc(CHUNK)
    while (pos < size) {
      const n = fs.readSync(fd, buf, 0, Math.min(CHUNK, size - pos), pos)
      if (n <= 0) break
      pos += n
      const text = carry + buf.toString('utf8', 0, n)
      const lines = text.split('\n')
      carry = lines.pop() // incomplete tail: kept for the next chunk or the next run
      for (const line of lines) {
        const custom = line.includes('"type":"custom-title"')
        if (!custom && !line.includes('"type":"ai-title"')) continue
        try {
          const rec = JSON.parse(line)
          if (custom && rec.customTitle) st.custom = rec.customTitle
          else if (rec.aiTitle) st.ai = rec.aiTitle
        } catch {
          // a line that is not JSON is not a title record
        }
      }
    }
    st.offset = pos - Buffer.byteLength(carry, 'utf8')
  } finally {
    fs.closeSync(fd)
  }
  return st.custom || st.ai || ''
}

async function reportThreadTitle(payload, { fetchImpl = fetch, timeoutMs = 3000 } = {}) {
  const transcriptPath = payload && payload.transcript_path
  if (!transcriptPath) return { sent: false, why: 'no transcript_path' }
  const id = path.basename(transcriptPath, '.jsonl')
  if (!UUID.test(id)) return { sent: false, why: 'not a session transcript' }

  const stateFile = home('.cache', 'bifrost', 'lineage-titles.json')
  const state = readState(stateFile)
  const st = state[id] || {}
  const title = scan(transcriptPath, st)
  state[id] = st
  if (!title || title === st.reported) {
    writeState(stateFile, state)
    return { sent: false, why: title ? 'unchanged' : 'no title yet', title }
  }
  const tok = token()
  if (!tok) {
    writeState(stateFile, state)
    return { sent: false, why: 'no reporter token', title }
  }
  const base = (process.env.PLATFORM_LINEAGE_URL || DEFAULT_URL).replace(/\/+$/, '')
  try {
    const res = await fetchImpl(`${base}/api/v1/lineage/transcript-title`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
      body: JSON.stringify({ transcript: id, title }),
      signal: AbortSignal.timeout(timeoutMs),
    })
    if (res.ok) st.reported = title
    writeState(stateFile, state)
    return { sent: res.ok, status: res.status, title }
  } catch (err) {
    writeState(stateFile, state)
    return { sent: false, why: err.message, title }
  }
}

module.exports = { reportThreadTitle, scan }
