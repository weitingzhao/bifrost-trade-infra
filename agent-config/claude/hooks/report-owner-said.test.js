#!/usr/bin/env node
'use strict'
// node agent-config/claude/hooks/report-owner-said.test.js — exits non-zero on failure.
// Origin: 2026-11-25, the Owner chose automatic collection of what he says (「我觉得B好，需要自动收集」): only his own
// typed messages go (origin.kind human), each once, and a failed post is read again next time.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'owner-said-hook-'))
process.env.BIFROST_HOME_OVERRIDE = tmp
process.env.PLATFORM_REPORTER_TOKEN = 'tok'
process.env.PLATFORM_LINEAGE_URL = 'http://platform.test/'

const { reportOwnerSaid } = require('./report-owner-said.js')

const id = 'd09a336c-ef6d-4b7c-abc6-d7e907e428f4'
const transcript = path.join(tmp, 'project', `${id}.jsonl`)
fs.mkdirSync(path.dirname(transcript), { recursive: true })
const line = (o) => JSON.stringify(o) + '\n'
const u = (n) => `11111111-1111-4111-8111-${String(n).padStart(12, '0')}`

const calls = []
let fail = false
const fetchImpl = async (url, init) => {
  calls.push({ url, auth: init.headers.Authorization, body: JSON.parse(init.body) })
  return fail ? { ok: false, status: 503 } : { ok: true, status: 200 }
}
const env = { ...process.env, CLAUDE_CODE_HOST_SESSION_ID: 'local_6ab1ad67-09a8-4522-9b4a-a03125b10b2c' }

async function main() {
  fs.writeFileSync(
    transcript,
    line({ type: 'user', uuid: u(1), timestamp: '2026-11-25T13:00:00Z', origin: { kind: 'human' }, message: { content: '我觉得B好，需要自动收集' } }) +
      // a peer session's message: not his
      line({ type: 'user', uuid: u(2), timestamp: '2026-11-25T13:01:00Z', isMeta: true, origin: { kind: 'peer', from: 'local_x' }, message: { content: 'Another Claude session sent a message' } }) +
      // a summary's continuation: no origin
      line({ type: 'user', uuid: u(3), timestamp: '2026-11-25T13:02:00Z', message: { content: 'This session is being continued' } }) +
      // his message as parts, with the host's reminder cut
      line({ type: 'user', uuid: u(4), timestamp: '2026-11-25T13:03:00Z', origin: { kind: 'human' }, message: { content: [{ type: 'text', text: '<system-reminder>\nLinked sessions\n</system-reminder>' }, { type: 'text', text: '继续推' }] } }) +
      // a tool result: not his
      line({ type: 'user', uuid: u(5), timestamp: '2026-11-25T13:04:00Z', origin: { kind: 'human' }, message: { content: [{ type: 'tool_result', content: 'x' }] } }),
  )
  let r = await reportOwnerSaid({ transcript_path: transcript }, { fetchImpl, env })
  assert.equal(r.sent, 2)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, 'http://platform.test/api/v1/agentrt/owner-said')
  assert.equal(calls[0].auth, 'Bearer tok')
  assert.deepEqual(calls[0].body.messages.map((m) => [m.message_id, m.text, m.transcript, m.thread]), [
    [u(1), '我觉得B好，需要自动收集', id, env.CLAUDE_CODE_HOST_SESSION_ID],
    [u(4), '继续推', id, env.CLAUDE_CODE_HOST_SESSION_ID],
  ])

  // nothing new: nothing sent
  r = await reportOwnerSaid({ transcript_path: transcript }, { fetchImpl, env })
  assert.equal(r.sent, 0)
  assert.equal(calls.length, 1)

  // a new message whose post fails is read again next time (positive control of "nothing new")
  fs.appendFileSync(transcript, line({ type: 'user', uuid: u(6), timestamp: '2026-11-25T13:05:00Z', origin: { kind: 'human' }, message: { content: '批了' } }))
  fail = true
  r = await reportOwnerSaid({ transcript_path: transcript }, { fetchImpl, env })
  assert.equal(r.sent, 0)
  fail = false
  r = await reportOwnerSaid({ transcript_path: transcript }, { fetchImpl, env })
  assert.equal(r.sent, 1)
  assert.equal(calls.at(-1).body.messages[0].text, '批了')

  // a half-written last line waits for its end
  fs.appendFileSync(transcript, '{"type":"user","uuid":"' + u(7) + '","origin":{"kind":"human"')
  r = await reportOwnerSaid({ transcript_path: transcript }, { fetchImpl, env })
  assert.equal(r.sent, 0)
  console.log('report-owner-said: ok')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
