#!/usr/bin/env node
'use strict'
/**
 * Publish the local progress board (W-62).
 *
 * Interim bridge (DESIGN §20.4): the coordinating thread already computes
 * status.json; this posts that document. Later the runtime computes it from
 * events.
 *
 *   node progress-publish.js <path to status.json>
 *
 * Adds host (the short hostname) and PUTs it with the reporter token, found
 * the same way as thread-heartbeat.js. Always exits 0. Prints nothing. Gives
 * up after 5 seconds. No token, or a file that is missing, unreadable, not
 * JSON, or over 256 KiB: no request.
 */
const fs = require('node:fs')
const { publishProgress, hostName } = require('./thread-heartbeat.js')

const MAX_BYTES = 256 * 1024
const GIVE_UP_MS = 5000

function readDocument(file) {
  let raw
  try {
    const st = fs.statSync(file)
    if (!st.isFile() || st.size > MAX_BYTES) return null
    raw = fs.readFileSync(file)
  } catch {
    return null
  }
  if (raw.length > MAX_BYTES) return null
  let doc
  try {
    doc = JSON.parse(raw.toString('utf8'))
  } catch {
    return null
  }
  if (doc == null || typeof doc !== 'object' || Array.isArray(doc)) return null
  doc.host = hostName()
  return Buffer.from(JSON.stringify(doc))
}

async function publish(file) {
  const body = readDocument(file)
  if (body == null) return
  await publishProgress(body, GIVE_UP_MS)
}

function main(argv) {
  const file = argv[0]
  if (!file) return Promise.resolve()
  const timer = setTimeout(() => process.exit(0), GIVE_UP_MS)
  timer.unref()
  return publish(file)
}

if (require.main === module) {
  process.on('uncaughtException', () => process.exit(0))
  process.on('unhandledRejection', () => process.exit(0))
  main(process.argv.slice(2)).then(
    () => process.exit(0),
    () => process.exit(0),
  )
}

module.exports = { publish, readDocument, MAX_BYTES, GIVE_UP_MS }
