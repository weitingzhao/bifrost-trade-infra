#!/usr/bin/env node
'use strict'
// node agent-config/claude/hooks/report-thread-title.test.js — exits non-zero on failure.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'title-hook-'))
process.env.BIFROST_HOME_OVERRIDE = tmp
delete process.env.PLATFORM_REPORTER_TOKEN
process.env.PLATFORM_LINEAGE_URL = 'http://platform.test/'

const { reportThreadTitle } = require('./report-thread-title.js')

const id = 'd09a336c-ef6d-4b7c-abc6-d7e907e428f4'
const transcript = path.join(tmp, 'project', `${id}.jsonl`)
fs.mkdirSync(path.dirname(transcript), { recursive: true })
const line = o => JSON.stringify(o) + '\n'

const calls = []
const okFetch = async (url, init) => {
  calls.push({ url, auth: init.headers.Authorization, body: JSON.parse(init.body) })
  return { ok: true, status: 200 }
}

async function main() {
  // no title yet, no token: nothing sent
  fs.writeFileSync(transcript, line({ type: 'user', message: { content: 'the word "type":"custom-title" inside prose' } }))
  let r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.equal(r.sent, false)
  assert.equal(r.why, 'no title yet')

  // a generated title, still no token
  fs.appendFileSync(transcript, line({ type: 'ai-title', aiTitle: 'Generated name', sessionId: id }))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.why, r.title], [false, 'no reporter token', 'Generated name'])

  // token from the file in the (overridden) home
  fs.mkdirSync(path.join(tmp, '.config', 'bifrost'), { recursive: true })
  fs.writeFileSync(path.join(tmp, '.config', 'bifrost', 'lineage-reporter.token'), 'tok-123\n')
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.equal(r.sent, true)
  assert.deepEqual(calls.at(-1), {
    url: 'http://platform.test/api/v1/lineage/transcript-title',
    auth: 'Bearer tok-123',
    body: { transcript: id, title: 'Generated name' },
  })

  // unchanged title: not sent again
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.why], [false, 'unchanged'])
  assert.equal(calls.length, 1)

  // the user renames the thread: the custom title wins and is sent
  fs.appendFileSync(transcript, line({ type: 'custom-title', customTitle: 'Renamed by Owner', sessionId: id }))
  fs.appendFileSync(transcript, line({ type: 'ai-title', aiTitle: 'A later generated name', sessionId: id }))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.title], [true, 'Renamed by Owner'])

  // a half-written line is not consumed until it is complete
  const half = line({ type: 'custom-title', customTitle: 'Second rename', sessionId: id })
  fs.appendFileSync(transcript, half.slice(0, 20))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.why], [false, 'unchanged'])
  fs.appendFileSync(transcript, half.slice(20))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.title], [true, 'Second rename'])

  // a failed request is retried on the next Stop
  const failFetch = async () => ({ ok: false, status: 503 })
  fs.appendFileSync(transcript, line({ type: 'custom-title', customTitle: 'Third', sessionId: id }))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: failFetch })
  assert.deepEqual([r.sent, r.status], [false, 503])
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.title], [true, 'Third'])

  // a network error is swallowed
  r = await reportThreadTitle({ transcript_path: transcript }, {
    fetchImpl: async () => { throw new Error('ECONNREFUSED') },
  })
  assert.equal(r.sent, false)

  // a rewritten (shorter) transcript is re-read from the start
  fs.writeFileSync(transcript, line({ type: 'ai-title', aiTitle: 'Fresh', sessionId: id }))
  r = await reportThreadTitle({ transcript_path: transcript }, { fetchImpl: okFetch })
  assert.deepEqual([r.sent, r.title], [true, 'Fresh'])

  // not a session transcript, or no payload
  assert.equal((await reportThreadTitle({ transcript_path: path.join(tmp, 'notes.jsonl') })).sent, false)
  assert.equal((await reportThreadTitle({})).sent, false)

  fs.rmSync(tmp, { recursive: true, force: true })
  console.log('report-thread-title: 11 checks passed')
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
