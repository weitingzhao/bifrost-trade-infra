'use strict'
/**
 * Report what the Owner says in this session to the Ops Platform (Owner 2026-11-25 in the legislation thread, choosing
 * automatic collection: 「我觉得B好，需要自动收集」).
 *
 * On every Stop the transcript is read from where the last run stopped (offset kept in ~/.cache/bifrost/owner-said.json).
 * A record is the Owner's own words when it is a user record whose origin.kind is "human": a peer session's message
 * (origin.kind "peer", isMeta), a summary's continuation (no origin), a tool result and a side chain are not his. The
 * text is his typed text: string content, or the text parts of a list, with the host's <system-reminder> blocks cut.
 * Each message goes once (the platform keys it by the record's uuid), to POST /api/v1/agentrt/owner-said, where the
 * legislation line classifies it (LAW-1 s7). Anything shaped like a secret is replaced before it leaves the machine
 * (redact: CORE-1 2, passwords and secrets are never read or quoted): a private key block, a provider token, a bearer
 * token, the value after password / token / secret / api key, and a base64 run of 40 or more characters; hex runs
 * (commit ids, digests) stay.
 *
 * Config (nothing secret lives in the repo):
 *   PLATFORM_LINEAGE_URL      platform-api base (default: PROD NodePort)
 *   PLATFORM_REPORTER_TOKEN   reporter-role token, or the first line of ~/.config/bifrost/lineage-reporter.token
 * No token → nothing is sent. Every failure is swallowed: a hook never blocks a session.
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const DEFAULT_URL = 'http://192.168.10.73:30876' // bifrost-platform-prod platform-api NodePort
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const LOCAL = /^local_[0-9a-f-]{8,64}$/
const CHUNK = 4 * 1024 * 1024
const BATCH = 200

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
    // a lost offset only means a re-read next time; the platform records a message once
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

const SECRETS = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)/g, '[redacted: private key]'],
  [/\b(sk|rk|pk)-[A-Za-z0-9_-]{16,}/g, '[redacted: token]'],
  [/\bgh[pousr]_[A-Za-z0-9]{16,}/g, '[redacted: token]'],
  [/\b(Bearer)\s+[A-Za-z0-9._~+/-]{16,}=*/gi, '$1 [redacted]'],
  [/\b(password|passwd|pwd|token|secret|api[_-]?key)(\s*[:=：]\s*)\S{6,}/gi, '$1$2[redacted]'],
  [/(^|[^A-Za-z0-9+/:])([A-Za-z0-9+/]{40,}={0,2})(?![A-Za-z0-9+/])/g, (m, pre, run) => (keyLike(run) ? `${pre}[redacted: long string]` : m)],
]

/** A run of 40 or more base64 characters is taken for a key when it mixes digits, capitals and small letters and is
 *  not a path (two or more slashes), a hex digest or a Gerrit Change-Id (I and 40 hex). */
function keyLike(run) {
  if (/^I?[0-9a-f]+$/.test(run) || (run.match(/\//g) || []).length > 1) return false
  return /[0-9]/.test(run) && /[A-Z]/.test(run) && /[a-z]/.test(run)
}

/** text with anything shaped like a secret replaced. */
function redact(text) {
  let out = text
  for (const [re, to] of SECRETS) out = out.replace(re, to)
  return out
}

/** The Owner's typed text of a user record, or '' when the record is not his. */
function ownerText(rec) {
  if (!rec || rec.type !== 'user' || rec.isMeta || rec.isSidechain) return ''
  if (!rec.origin || rec.origin.kind !== 'human') return ''
  const c = rec.message && rec.message.content
  let text = ''
  if (typeof c === 'string') text = c
  else if (Array.isArray(c)) text = c.filter((p) => p && p.type === 'text' && typeof p.text === 'string').map((p) => p.text).join('\n')
  return redact(text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '').trim())
}

/** The Owner's messages appended since st.offset; advances st.offset to the last complete line. */
function scan(file, st) {
  const out = []
  let size
  try {
    size = fs.statSync(file).size
  } catch {
    return out
  }
  if (!(st.offset >= 0) || st.offset > size) st.offset = 0
  const fd = fs.openSync(file, 'r')
  try {
    let pos = st.offset
    let carry = ''
    const buf = Buffer.alloc(CHUNK)
    while (pos < size) {
      const n = fs.readSync(fd, buf, 0, Math.min(CHUNK, size - pos), pos)
      if (n <= 0) break
      pos += n
      const lines = (carry + buf.toString('utf8', 0, n)).split('\n')
      carry = lines.pop()
      for (const line of lines) {
        if (!line.includes('"type":"user"') || !line.includes('"human"')) continue
        try {
          const rec = JSON.parse(line)
          const text = ownerText(rec)
          if (text && UUID.test(rec.uuid || '') && rec.timestamp) out.push({ message_id: rec.uuid, said_at: rec.timestamp, text })
        } catch {
          // a line that is not JSON is not a message
        }
      }
    }
    st.offset = pos - Buffer.byteLength(carry, 'utf8')
  } finally {
    fs.closeSync(fd)
  }
  return out
}

async function reportOwnerSaid(payload, { fetchImpl = fetch, timeoutMs = 5000, env = process.env } = {}) {
  const transcriptPath = payload && payload.transcript_path
  if (!transcriptPath) return { sent: 0, why: 'no transcript_path' }
  const id = path.basename(transcriptPath, '.jsonl')
  if (!UUID.test(id)) return { sent: 0, why: 'not a session transcript' }
  const stateFile = home('.cache', 'bifrost', 'owner-said.json')
  const state = readState(stateFile)
  const st = state[id] || {}
  const before = st.offset
  const said = scan(transcriptPath, st)
  if (said.length === 0) {
    state[id] = st
    writeState(stateFile, state)
    return { sent: 0, why: 'nothing new' }
  }
  const tok = token()
  if (!tok) return { sent: 0, why: 'no reporter token' } // offset not kept: read again once a token is there
  const thread = LOCAL.test(env.CLAUDE_CODE_HOST_SESSION_ID || '') ? env.CLAUDE_CODE_HOST_SESSION_ID : undefined
  const host = (os.hostname().split('.')[0] || '').replace(/[^A-Za-z0-9._-]/g, '').slice(0, 64) || undefined
  const base = (env.PLATFORM_LINEAGE_URL || DEFAULT_URL).replace(/\/+$/, '')
  let sent = 0
  for (let i = 0; i < said.length; i += BATCH) {
    const messages = said.slice(i, i + BATCH).map((m) => ({ ...m, transcript: id, thread, host }))
    try {
      const res = await fetchImpl(`${base}/api/v1/agentrt/owner-said`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
        body: JSON.stringify({ messages }),
        signal: AbortSignal.timeout(timeoutMs),
      })
      if (!res.ok) {
        st.offset = before // keep the old offset: these are read again next time
        state[id] = st
        writeState(stateFile, state)
        return { sent, status: res.status }
      }
      sent += messages.length
    } catch (err) {
      st.offset = before
      state[id] = st
      writeState(stateFile, state)
      return { sent, why: err.message }
    }
  }
  state[id] = st
  writeState(stateFile, state)
  return { sent }
}

module.exports = { reportOwnerSaid, scan, ownerText, redact }
