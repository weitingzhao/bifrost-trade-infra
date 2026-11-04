#!/usr/bin/env node
'use strict'
// node --test agent-config/scripts/source-capability-witness.test.js
//
// SourceCapabilityWitness (R5:5.5-12 S1-0, MATRIX §6): every scrubbed fixture
// under testdata/source-capability/<vendor>-<version>/ is run through the
// scripts and checked field by field. A fixture this file does not classify
// fails the test, and so does a source listed as unverified that gains a
// fixture: adding a capture means writing down what it shows.
//
// Classes (CUT §4): live = available as it happens; delayed = only after the
// end; unavailable = not available.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const h = require('./collector-test-harness.js')

for (const k of ['PLATFORM_COLLECTOR_TOKEN', 'BIFROST_HEARTBEAT_THREAD', 'BIFROST_HEARTBEAT_TITLE', 'BIFROST_WORK', 'CLAUDE_CODE_HOST_SESSION_ID']) delete process.env[k]
process.env.BIFROST_HOME_OVERRIDE = h.tmpHome('witness-unit')
const { beatFor } = require('./thread-heartbeat.js')
const collector = require('./collector-session.js')

const CLAUDE = path.join(h.FIXTURES, 'claude-2.1.302')
const CODEX = path.join(h.FIXTURES, 'codex-0.166.0-alpha.5.1')
const HB = path.join(h.HERE, 'thread-heartbeat.js')
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'))
const lines = file => fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l))

// Hook event → [reporter beat, collector beat], each [event, reason] or null.
const HOOKS = {
  SessionStart: p => [null, ['session_start', p.source]],
  UserPromptSubmit: () => [['turn_start', ''], ['turn_start', '']],
  StopFailure: () => [null, ['turn_end', '']],
  PreCompact: p => [null, ['precompact', p.trigger]],
  SessionEnd: () => [null, ['turn_end', '']],
  Notification: p => [['waiting_owner', p.notification_type], ['waiting_owner', p.notification_type]],
  InstructionsLoaded: () => [null, null],
}
// Fields each hook event carries that a script reads, with their type (MATRIX §1).
const READ_FIELDS = {
  SessionStart: { source: 'string' },
  UserPromptSubmit: { prompt: 'string', prompt_id: 'string' },
  StopFailure: { error: 'string' },
  PreCompact: { trigger: 'string' },
  SessionEnd: { reason: 'string' },
  Notification: { notification_type: 'string' },
  InstructionsLoaded: { load_reason: 'string' },
}
// Not observed by S1-0 (MATRIX §7): no fixture may exist for them until this table says what it shows.
const UNVERIFIED = ['Stop.', 'PostToolUseFailure.', 'SubagentStart.', 'SubagentStop.', 'PostCompact.', 'SessionStart.compact', 'PreCompact.auto', 'Notification.permission_prompt']

const asBeat = b => (b ? [b.event, b.reason || ''] : null)

test('every Claude hook fixture: the fields the scripts read, and the beat each mode makes of them', () => {
  const dir = path.join(CLAUDE, 'hooks')
  const names = fs.readdirSync(dir).sort()
  assert.ok(names.length >= 15)
  for (const name of names) {
    const fx = read(path.join(dir, name))
    const p = fx.payload
    assert.equal(fx._meta.cli_version, '2.1.302', name)
    assert.equal(fx._meta.scrubbed, true, name)
    for (const [k, type] of Object.entries({ session_id: 'string', transcript_path: 'string', cwd: 'string', hook_event_name: 'string' })) assert.equal(typeof p[k], type, `${name}.${k}`)
    assert.match(p.session_id, /^[0-9a-f-]{36}$/, name)
    const want = HOOKS[p.hook_event_name]
    assert.ok(want, `${name}: unclassified hook event ${p.hook_event_name}`)
    for (const [k, type] of Object.entries(READ_FIELDS[p.hook_event_name])) assert.equal(typeof p[k], type, `${name}.${k}`)
    const [reporter, wanted] = want(p)
    assert.deepEqual(asBeat(beatFor('claude', p)), reporter, `${name}: reporter mode`)
    const b = beatFor('claude', p, collector)
    assert.deepEqual(asBeat(b), wanted, `${name}: collector mode`)
    if (!b) continue
    assert.equal(b.identity.session, p.session_id, `${name}: session is the raw vendor id`)
    assert.equal(b.title, undefined, name)
    // Live: every observed hook arrives while its session runs (MATRIX §1 class column).
    assert.ok(fx._meta.observed_at, `${name}: live, stamped when it happened`)
  }
  for (const u of UNVERIFIED) assert.ok(!names.some(n => n.startsWith(u)), `${u} has a fixture now: classify it`)
})

test('the stray pre-resume id (§12 D5) and fork (§12 D2) are what the matrix says', () => {
  const orphan = read(path.join(CLAUDE, 'hooks', 'InstructionsLoaded.orphan-pre-resume-id.json'))
  assert.equal(beatFor('claude', orphan.payload, collector), null, 'InstructionsLoaded never allocates an epoch')
  const fork = read(path.join(CLAUDE, 'hooks', 'SessionStart.fork.json')).payload
  assert.deepEqual(Object.keys(fork).sort(), ['cwd', 'hook_event_name', 'session_id', 'source', 'transcript_path'], 'fork names no source session')
  const refused = read(path.join(CLAUDE, 'hooks', 'PreCompact.manual.refused.json'))
  assert.match(refused._meta.run_mode, /Not enough messages/, '§12 D3: PreCompact fires for a refused compaction, so compactions are attempts')
})

// Expected epoch per sequence line (null: no beat). The session is the line's own id.
const EPOCHS = {
  'interactive.bang-bash.jsonl': [1, null, 1, 1],
  'interactive.sighup.jsonl': [1, null, 1, 1, 1],
  'interactive.sigkill-then-resume.jsonl': [1, null, 1, 1, 2, null, 2, 2, 2],
  'interactive.sigterm.jsonl': [1, null, 1, 1, 1],
  'interactive.startup-clear-compact-idle-exit.jsonl': [1, null, 1, 1, 1, 1, 1, 1, null, 1, 1, 1],
  'p.compound-hook-command.jsonl': [null, 1, 1, 1, 1],
  'p.continue.jsonl': [null, 1, null, 1, 1],
  'p.fork-session.jsonl': [1, null, 1, 1],
  'p.nested-inherited-env.jsonl': [1, null, 1, 1],
  'p.no-session-persistence.jsonl': [1, null, 1, 1],
  'p.resume.jsonl': [null, 1, null, 1, 1],
  'p.startup.jsonl': [1, null, 1, 1],
  'p.stream-input.compact-clear.jsonl': [null, 1, 1, 1, 1, 1, 1, 1, null, 1],
}
const PIDS = { P1: '41001', P2: '41002', P3: '41003' }

function payloadOf(l) {
  const p = h.claudePayload(l.hook.replace(/-compound$/, ''), l.session_id)
  for (const k of ['source', 'reason', 'trigger', 'notification_type', 'error']) if (l[k] != null) p[k] = l[k]
  return p
}

test('every Claude hook sequence, run through the hook in collector mode: event, reason, session, epoch', async () => {
  const dir = path.join(CLAUDE, 'sequences')
  const names = fs.readdirSync(dir).sort()
  assert.deepEqual(names, Object.keys(EPOCHS).sort(), 'every sequence is classified')
  for (const name of names) {
    const [meta, ...steps] = lines(path.join(dir, name))
    assert.equal(meta._meta.cli_version, '2.1.302')
    assert.equal(steps.length, EPOCHS[name].length, name)
    const home = h.tmpHome('witness')
    const srv = await h.fakeServer()
    try {
      const want = []
      for (const [i, l] of steps.entries()) {
        // §12 D1: CLAUDE_PID is the CLI's pid whatever the hook command's shape; a compound
        // command's parent is a shell (ppid P2 here), its CLAUDE_PID still the CLI (P1).
        const cli = l.parent_comm === 'claude' ? PIDS[l.ppid] : PIDS.P1
        if (l.env_pid_match) assert.equal(l.env_pid_match.CLAUDE_PID, l.parent_comm === 'claude' ? 0 : 1, `${name}:${i} CLAUDE_PID is the CLI`)
        const r = await h.runHook(HB, 'claude', payloadOf(l), h.collectorEnv(home, srv.url, { CLAUDE_PID: cli }))
        assert.deepEqual([r.code, r.out], [0, ''])
        await h.settle(srv, home, srv.got.length)
        const beat = HOOKS[l.hook.replace(/-compound$/, '')](l)[1]
        assert.equal(beat === null, EPOCHS[name][i] === null, `${name}:${i} table and expectation agree`)
        if (beat) want.push([...beat, l.session_id, EPOCHS[name][i]])
      }
      assert.deepEqual(h.beats(srv), want, name)
      h.noTitle(srv)
      for (const r of srv.got) assert.equal(r.body.thread, r.body.session, `${name}: no wrapper, so the transport thread is the session`)
      // Every session that ended had its end acked; one killed without an end is a gap.
      for (const sid of new Set(steps.map(l => l.session_id))) {
        const st = h.readEpochs(home, 'claude', sid)
        const opened = steps.some(l => l.session_id === sid && HOOKS[l.hook.replace(/-compound$/, '')](l)[1])
        assert.equal(Boolean(st), opened, `${name}: ${sid} has epochs only if a wired event opened them`)
        if (!st) continue
        for (const e of st.epochs) if (e.end) assert.ok(e.end.acked_at, `${name}: epoch ${e.epoch} end acked`)
      }
      if (name === 'interactive.sigkill-then-resume.jsonl') {
        assert.deepEqual(collector.endGaps(h.readEpochs(home, 'claude', steps[0].session_id)), [{ epoch: 1, kind: 'end_missing' }], 'SIGKILL leaves epoch 1 without an end')
      }
    } finally {
      srv.close()
    }
  }
})

test('sequence facts the design rests on: transcripts, the compound hook pid, the pre-resume id', () => {
  const seq = name => lines(path.join(CLAUDE, 'sequences', name)).slice(1)
  // S2: no transcript under --no-session-persistence (unavailable); the hook stream is live.
  assert.ok(seq('p.no-session-persistence.jsonl').every(l => l.transcript_exists === false))
  // H17: a compound hook command has a shell parent; CLAUDE_PID is still the CLI.
  const compound = seq('p.compound-hook-command.jsonl').find(l => l.hook.endsWith('-compound'))
  assert.deepEqual([compound.parent_comm, compound.ppid, compound.env_pid_match.CLAUDE_PID], ['sh', 'P2', 1])
  // H2 / E1: -p --resume and --continue first send a fresh id that never starts or ends.
  for (const name of ['p.resume.jsonl', 'p.continue.jsonl']) {
    const [first, second] = seq(name)
    assert.deepEqual([first.hook, second.hook, second.source], ['InstructionsLoaded', 'SessionStart', 'resume'])
    assert.notEqual(first.session_id, second.session_id)
    assert.ok(!seq(name).some(l => l.session_id === first.session_id && l.hook !== 'InstructionsLoaded'))
  }
})

test('Claude stream-json (no script of this slice reads it): identity fields as the matrix says', () => {
  const dir = path.join(CLAUDE, 'stream-json')
  const names = fs.readdirSync(dir).sort()
  assert.deepEqual(names, ['p.continue.jsonl', 'p.no-session-persistence.jsonl', 'p.persist.jsonl', 'p.stream-input.compact-clear.jsonl'])
  for (const name of names) {
    const [meta, ...rows] = lines(path.join(dir, name))
    assert.equal(meta._meta.cli_version, '2.1.302')
    const objs = rows.map(r => r.obj)
    // Live: every line carries its session id, and the hook lines name only SessionStart or UserPromptSubmit (S1).
    assert.ok(objs.every(o => typeof o.session_id === 'string'), name)
    for (const o of objs.filter(o => o.subtype === 'hook_started')) assert.match(o.hook_name, /^(SessionStart:|UserPromptSubmit$)/, name)
    const inits = objs.filter(o => o.type === 'system' && o.subtype === 'init')
    assert.ok(inits.length >= 1, `${name}: an init line`)
    if (name === 'p.continue.jsonl') {
      // S3: the first hook_started carries the pre-resume id; readers take init's.
      assert.notEqual(objs[0].session_id, inits[0].session_id)
      assert.ok(objs.slice(2).every(o => o.session_id === inits[0].session_id))
    }
    if (name === 'p.stream-input.compact-clear.jsonl') {
      // S4: /clear is a conversation_reset, then a new init with a new id; /compact is system/status lines.
      assert.ok(objs.some(o => o.type === 'conversation_reset'))
      assert.ok(objs.some(o => o.type === 'system' && o.subtype === 'status'))
      const reset = objs.findIndex(o => o.type === 'conversation_reset')
      const before = new Set(objs.slice(0, reset).map(o => o.session_id))
      const after = new Set(objs.slice(reset + 1).map(o => o.session_id))
      assert.deepEqual([before.size, after.size], [1, 1], 'one id on each side of the reset')
      assert.notEqual([...before][0], [...after][0])
      assert.ok(objs.slice(reset + 1).some(o => o.type === 'system' && o.subtype === 'init'), 'an init with the new id follows the reset')
    }
  }
})

test('Codex exec --json (no script of this slice reads it): only the first line names the session', () => {
  const dir = path.join(CODEX, 'exec-json')
  const names = fs.readdirSync(dir).sort()
  assert.deepEqual(names, ['exec.basic.jsonl', 'exec.ephemeral.jsonl', 'exec.file-change-reasoning.jsonl', 'exec.resume-of-ephemeral.json', 'exec.resume.jsonl', 'exec.tools-success-and-failure.jsonl'])
  for (const name of names.filter(n => n.endsWith('.jsonl'))) {
    const [meta, ...rows] = lines(path.join(dir, name))
    assert.equal(meta._meta.cli_version, 'codex-cli 0.166.0-alpha.5.1')
    const objs = rows.map(r => r.obj)
    // X1, X3: thread.started is first and the only line with the id; a resume carries no marker.
    assert.deepEqual(Object.keys(objs[0]).sort(), ['thread_id', 'type'], name)
    assert.equal(objs[0].type, 'thread.started')
    assert.ok(objs.slice(1).every(o => !('thread_id' in o) && !('session_id' in o)), name)
    assert.ok(objs.some(o => o.type === 'turn.completed'), name)
  }
  const tools = lines(path.join(dir, 'exec.tools-success-and-failure.jsonl')).slice(1).map(r => r.obj)
  const done = tools.filter(o => o.type === 'item.completed' && o.item.type === 'command_execution').map(o => [o.item.status, o.item.exit_code])
  assert.ok(done.some(d => d[0] === 'failed' && d[1] === 1) && done.some(d => d[0] === 'completed' && d[1] === 0), 'X4: a failed command is status failed with its exit code')
  assert.ok(tools.filter(o => o.type === 'item.started' && o.item.type === 'command_execution').every(o => o.item.exit_code === null), 'X4: no exit code while it runs')
  const change = lines(path.join(dir, 'exec.file-change-reasoning.jsonl')).slice(1).map(r => r.obj).find(o => o.item && o.item.type === 'file_change')
  assert.ok(change && !('diff' in change.item), 'X5: a file change carries no diff')
  // X2: an ephemeral session cannot be resumed: unavailable after the fact.
  assert.deepEqual([read(path.join(dir, 'exec.resume-of-ephemeral.json')).stdout_lines, read(path.join(dir, 'exec.resume-of-ephemeral.json')).exit_code], [0, 1])
})

test('only the sources above have fixtures (Cursor and Codex hooks are unverified)', () => {
  assert.deepEqual(fs.readdirSync(h.FIXTURES).sort(), ['claude-2.1.302', 'codex-0.166.0-alpha.5.1'])
  assert.deepEqual(fs.readdirSync(CLAUDE).sort(), ['hooks', 'sequences', 'stream-json'])
  assert.deepEqual(fs.readdirSync(CODEX).sort(), ['exec-json'])
})
