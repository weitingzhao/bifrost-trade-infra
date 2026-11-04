#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/collector-mutation.test.js
//
// Mutation check over the S1-4 code: each mutant below is one plausible
// mistake in collector-session.js or in the collector branches of the hook
// scripts. It is written into a copy of the scripts, and the one test named
// for it must then fail. An unmutated copy must pass every named test first,
// so a kill is the mutant's doing, not the copy's.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const h = require('./collector-test-harness.js')

const FILES = ['thread-heartbeat.js', 'collector-session.js', 'collector-epochs.js', 'host-heartbeat.js', 'progress-publish.js', 'collector-test-harness.js',
  'collector-session.test.js', 'collector-hooks.test.js', 'collector-noop.test.js', 'source-capability-witness.test.js']
const U = 'collector-session.test.js'
const K = 'collector-hooks.test.js'
const N = 'collector-noop.test.js'

// [name, file, from, to, test file, test name pattern]
const MUTANTS = [
  ['resume reuses the counter', 'collector-epochs.js', 'st.max += 1', 'st.max = 1', U, '^the epoch counter never goes back'],
  ['an older process repeating its start opens an epoch (M4)', 'collector-epochs.js', '    if (byPid && !pidReused(byPid, ev)) {', '    if (byPid && isOpen(byPid)) {', U, '^M4 round 2: a process that ran over a minute'],
  ['a reused pid is never noticed', 'collector-epochs.js', '  return Boolean(now) && now !== e.pid_started', '  return false', U, '^a pid the system reused'],
  ['a missing start time counts as reuse', 'collector-epochs.js', '  return Boolean(now) && now !== e.pid_started', '  return now !== e.pid_started', U, '^without a start time on either side'],
  ['a late end is sent', 'collector-epochs.js', '    if (!isOpen(e)) {\n      st.dropped_ends += 1', '    if (false) {\n      st.dropped_ends += 1', U, '^a late SessionEnd across a resume'],
  ['fork is refused', 'collector-session.js', "'compact', 'fork'])", "'compact'])", U, '^the event table'],
  ['no context reads as whole context', 'collector-session.js', "if (!root && !node) return bind('unlinked', 'no_context')", 'if (!root && !node) return null', U, '^client_bind'],
  ['StopFailure is not wired', 'collector-session.js', ", StopFailure: 'turn_end' }", ' }', U, '^the event table'],
  ['the env host id is called a file', 'collector-session.js', "return { host: env, source: 'env', invalid: false }", "return { host: env, source: 'file', invalid: false }", U, '^host id'],
  ['an unacked end is not sent again', 'collector-epochs.js', "    out.push({ epoch: e.epoch, thread: e.end.thread || e.thread || '' })", '    void 0', U, '^a resume sends again'],
  ['an end is sent without the lock (M1)', 'collector-epochs.js', "    if (ev.kind === 'end') {\n      // No end goes out", "    if (false) {\n      // No end goes out", U, '^M1: an end that cannot take the epoch lock'],
  ['a kept end is never folded in (M1)', 'collector-epochs.js', '    const folded = foldPending(st, dir)', '    const folded = []', U, '^M1: an end that cannot take the epoch lock'],
  ['an end without a pid closes the current epoch (M2)', 'collector-epochs.js', '    } else if (!e) {\n      st.dropped_ends += 1\n', '    } else if (!e && ev.pid === 0) {\n      e = current\n    } else if (!e) {\n      st.dropped_ends += 1\n', U, '^M2: an end whose process cannot be told apart'],
  ['a replay is tried once only (M3)', 'collector-epochs.js', 'if (!e.end || e.end.acked_at || count(e.end.replay_attempts) >= MAX_REPLAY_ATTEMPTS) continue', 'if (!e.end || e.end.acked_at || count(e.end.replay_attempts) >= 1) continue', U, '^M3: a failed replay is tried again'],
  ['a pick spends an attempt (round 2)', 'collector-epochs.js', "    out.push({ epoch: e.epoch, thread: e.end.thread || e.thread || '' })", "    e.end.replay_attempts = count(e.end.replay_attempts) + 1\n    out.push({ epoch: e.epoch, thread: e.end.thread || e.thread || '' })", U, '^round 2: picking a replay costs no attempt'],
  ['a resend is never counted', 'thread-heartbeat.js', '      if (!collector.countReplay(beat._end, deps)) continue\n', '', K, '^round 2: resumes that cannot take the thread lock'],
  ['an unseen process supersedes a live one', 'collector-epochs.js', "  if (ev.pid > 0 || !current) return open('first_event', '', false)", "  if (ev.pid > 0 || !current) return open('first_event', '', true)", U, '^a first event from a process never seen'],
  ['an answer under a busy lock is lost', 'collector-epochs.js', '    deferRecord(sessionDir(end.vendor, end.session), 0, answer, new Date(now))', '    void answer', U, '^an answer that cannot take the epoch lock'],
  ['the parent pid stands in for CLAUDE_PID', 'collector-epochs.js', "const raw = String(env.CLAUDE_PID || '').trim()", 'const raw = String(process.ppid)', K, '^two resumes in the same second'],
  ['an end is never marked', 'collector-epochs.js', 'if (r.end) body._end =', 'if (false) body._end =', K, '^startup, prompt, failed turn, end'],
  ['a refused end leaves no gap', 'collector-epochs.js', "  st.gaps.push({ kind: 'end_unacked', epoch: e.epoch, at })", '  void 0', K, '^the end intent is persisted'],
  ['an unknown epoch keeps its session', 'collector-epochs.js', '    delete id.session\n', '', K, '^lock contention'],
  ['the local end record goes on the wire', 'thread-heartbeat.js', '  delete out._end\n', '', K, '^startup, prompt, failed turn, end'],
  ['a collector reads the env title', 'thread-heartbeat.js', "let title = collector ? '' : (process.env.BIFROST_HEARTBEAT_TITLE || '').trim()", "let title = (process.env.BIFROST_HEARTBEAT_TITLE || '').trim()", K, '^collector mode never sends a title'],
  ['heartbeats use the reporter token', 'thread-heartbeat.js', '  if (!body || !body.identity) return token()', '  return token()', K, '^credentials by purpose'],
  ['the epoch lock waits the whole budget', 'thread-heartbeat.js', '  if (capMs > 0) deadline = Math.min(deadline, lockRuntime.now() + capMs)', '', K, '^lock contention'],
  ['a dropped end is sent anyway', 'thread-heartbeat.js', '  if (r.drop) return false', '  if (r.drop) r.replay = []', K, '^a late SessionEnd across a resume'],
  ['the host beat keeps the reporter token', 'host-heartbeat.js', '  if (collector) return collector.collectorToken()\n', '', K, '^credentials by purpose'],
  ['reporter mode sends a local field', 'thread-heartbeat.js', '  delete out.tool_use_id\n', '', N, '^tool, wait, compaction'],
  ['reporter mode sends the session events', 'thread-heartbeat.js', ': EVENTS[vendor]\n', ": require('./collector-session.js').eventMap(vendor, EVENTS)\n", N, '^every Claude hook fixture, one after another'],
]

function copyTree(tag) {
  const root = h.tmpHome(`mutant-${tag}`)
  const scripts = path.join(root, 'agent-config', 'scripts')
  fs.mkdirSync(scripts, { recursive: true })
  for (const f of FILES) fs.copyFileSync(path.join(h.HERE, f), path.join(scripts, f))
  fs.symlinkSync(path.join(h.HERE, 'testdata'), path.join(scripts, 'testdata'))
  for (const [dir, f] of [['claude', 'settings.json'], ['cursor', 'hooks.json']]) {
    fs.mkdirSync(path.join(root, 'agent-config', dir), { recursive: true })
    fs.copyFileSync(path.join(h.HERE, '..', dir, f), path.join(root, 'agent-config', dir, f))
  }
  return scripts
}

function runTests(scripts, file, pattern) {
  const env = { PATH: process.env.PATH, COLLECTOR_BASELINE_REPO: h.HERE }
  const args = ['--test', '--test-concurrency=1', '--test-reporter=spec']
  if (pattern) args.push(`--test-name-pattern=${pattern}`)
  return h.runNode([...args, path.join(scripts, file)], { env })
}

async function pool(items, limit, fn) {
  const out = []
  let next = 0
  await Promise.all(Array.from({ length: limit }, async () => {
    while (next < items.length) {
      const i = next++
      out[i] = await fn(items[i], i)
    }
  }))
  return out
}

test('every mutant is killed by the test named for it', async () => {
  const clean = copyTree('clean')
  for (const file of [U, K, N]) {
    const patterns = [...new Set(MUTANTS.filter(m => m[4] === file).map(m => m[5]))].join('|')
    const r = await runTests(clean, file, patterns)
    assert.equal(r.code, 0, `the unmutated copy fails ${file}:\n${r.out.slice(-3000)}`)
  }
  const results = await pool(MUTANTS, 3, async ([name, file, from, to, testFile, pattern], i) => {
    const scripts = copyTree(`m${i}`)
    const target = path.join(scripts, file)
    const src = fs.readFileSync(target, 'utf8')
    assert.equal(src.split(from).length - 1, 1, `mutant "${name}": its anchor must occur once in ${file}`)
    fs.writeFileSync(target, src.replace(from, to))
    const r = await runTests(scripts, testFile, pattern)
    return { name, killed: r.code !== 0, ran: /ℹ tests [1-9]/.test(r.out) }
  })
  for (const r of results) assert.ok(r.ran, `mutant "${r.name}": its named test did not run`)
  assert.deepEqual(results.filter(r => !r.killed).map(r => r.name), [], 'surviving mutants')
})
