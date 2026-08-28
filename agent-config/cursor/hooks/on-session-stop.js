#!/usr/bin/env node
/**
 * Cursor session stop hook — POST session metadata to platform-api.
 * Env: PLATFORM_API_URL (default http://127.0.0.1:8780), PLATFORM_OPERATOR_TOKEN
 */
const fs = require('node:fs')

async function main() {
  const input = fs.readFileSync(0, 'utf8')
  let payload = {}
  try {
    payload = JSON.parse(input || '{}')
  } catch {
    payload = { raw: input }
  }

  const base = process.env.PLATFORM_API_URL || 'http://127.0.0.1:8780'
  const token = process.env.PLATFORM_OPERATOR_TOKEN || ''
  const body = {
    program_id: process.env.BIFROST_PROGRAM_ID || payload.program_id || 'briefing',
    phase_id: payload.phase_id || process.env.BIFROST_PHASE_ID || '',
    cursor_agent_id: payload.agent_id || payload.cursor_agent_id || '',
    summary: payload.summary || 'session stop hook',
    track: payload.track || '',
    lane: payload.lane || '',
    intent: payload.intent || '',
    duration_ms: payload.duration_ms || 0,
  }

  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  try {
    const res = await fetch(`${base}/api/v1/programs/session-stop`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      process.stderr.write(`[on-session-stop] HTTP ${res.status}: ${text}\n`)
    }
  } catch (err) {
    process.stderr.write(`[on-session-stop] ${err.message}\n`)
  }
}

main()
