# Observed Codex dispatch (PV1, Work 594)

`dispatch-codex.py` registers external work before launching `codex exec`.
Registration is visibility only: it grants no execution permission and a
submitted report never completes a plan step.

For an existing Claude session, use [register-claude-work.py](register-claude-work.README.md).
Coordinator open-session step (TD-446): register the work, retain its state,
heartbeat every 30 seconds while active, and submit the report when it returns.

The platform must run the corresponding PV1 HTTP routes. The wrapper fails
closed if upload, registration, recovery read, or the initial event fails.
It sends a heartbeat every 30 seconds. Missing server heartbeats for more than
60 seconds appear as `Unconfirmed`; the record remains visible.

## Description and invocation

Prepare a JSON description with exactly these fields. The task can be Chinese;
use a repository name, not a local filesystem path, for `repo`.

```json
{
  "v": 1,
  "kind": "agentrt.external_work/v1",
  "task": "实现并验证计划摘要",
  "executor": "codex",
  "provider": "openai",
  "repo": "bifrost-platform",
  "branch": "w31/pv1",
  "acceptance_refs": ["PV1"],
  "estimate_minutes": [30, 60]
}
```

Provide an existing reporter/operator token through `BIFROST_DISPATCH_TOKEN`.
Do not put a token on the command line, in the description, or in source control.
The session identifies the registrant, and must stay the same when resuming.
`--node` is the real database plan node ID, not an offline logical label.

```sh
python3 scripts/agent-host/dispatch-codex.py \
  --url http://127.0.0.1:8780 \
  --session local_example --run-key work-example \
  --root R4 --node R4:4.5-1 \
  --description /tmp/external-work.json \
  --report /tmp/example-work/REPORT.md \
  --state-dir /tmp/dispatch-state \
  --repo /tmp/example-work \
  -- 'Read BRIEF.md and carry out the authorized work.'
```

All arguments after `--` go to `codex exec`. They are never uploaded. The API
payloads contain only the description artifact and fixed registration/event
fields; the supervisor removes the dispatch token before starting Codex.
On exit the wrapper submits the SHA-256 of the absolute report path, the
report content digest when a report exists, up to 100 commits since the initial
HEAD, and the exit code. Report contents are not uploaded. `Submitted` includes
failed executions; it is not a success assertion.

## Crash recovery

Re-run the same invocation and retain the state directory. The registration
has the same actor/run identity, pending events replay with the same key and
sequence, and a GET of the registration retrieves its current sequence. A
process lock prevents simultaneous wrappers. A detached supervisor holds a
separate lock from before launch through its durable exit receipt, so killing
the wrapper does not launch a second Codex process on recovery.

A disappeared supervisor without an exit receipt remains unconfirmed and
requires reconciliation. The wrapper deliberately does not guess an exit code
or automatically relaunch uncertain work. A changed registration, report path,
or checkout under the same key is refused. For a new attempt use a new run key.
Do not remove another run's state or locks.

## Tests

```sh
python3 -m pytest -q scripts/agent-host/tests/test_dispatch_codex.py
ruff check scripts/agent-host/dispatch-codex.py scripts/agent-host/tests/test_dispatch_codex.py
```

The tests use a loopback fake HTTP server and a fake Codex executable. They
cover registration failure, heartbeats, payload privacy, failed submission
replay, changed registration rejection, and killing/resuming a live wrapper.
They neither contact the platform nor run the real Codex CLI.

## Collector mode (R5:5.5-12 S1-5)

With a collector token configured (`PLATFORM_COLLECTOR_TOKEN`, or the first
line of `~/.config/bifrost/collector.token`) the wrapper registers with it
instead of `BIFROST_DISPATCH_TOKEN`: vendor `codex`, session = the run key
(1–128 of `[A-Za-z0-9._:-]`), epoch 1, run key `codex:<run key>:1`; every event
names that identity, the server writes the host, and `registered_at` is kept
in `state.json`. Its local state and lock are keyed by that identity, not by
`--session`, so two callers cannot both launch one work. The file stays
self-contained: it is copied and run alone, in either mode.

In both modes the child gets no credential: every variable whose name holds
TOKEN, SECRET, PASSWORD or CREDENTIAL, and every `PLATFORM_*`, `AGENTRT_*`,
`HANDIN_*` and `BIFROST_DISPATCH_*` variable, is removed. A denylist, not an
allowlist: Codex needs the rest of the caller's environment (its own
`OPENAI_*`/`CODEX_*` settings, locale, proxies), which no list can foresee.

Without a collector token, `tests/test_collector_s15_noop.py` runs the wrapper
copied alone into an empty directory, as the coordinator does, next to the
46d1a32 one: the same requests (bytes), stdout, stderr, exit code and
`state.json`, for a whole run, `--help` and a refused registration. Intended
differences: the child's environment above, and `codex.json` in the run
directory. Crash and resume paths are not compared.

**Reconcile.** A run whose supervisor vanished without `exit.json` stays
Running. The supervisor records the real Codex process (`codex.json`: pid and
start time) and passes it `child.lock`, so the lock lasts as long as Codex.
`reconcile` ends the run as cancelled, with the token it was registered with,
only when no wrapper holds it, nothing holds `child.lock`, there is no exit
receipt and the recorded Codex is provably gone (no process under its pid, or
another start time). A run whose Codex cannot be told (an older wrapper's, or
one whose supervisor died while starting Codex) stays Unconfirmed. A second
reconcile sends nothing:

```sh
python3 scripts/agent-host/dispatch-codex.py reconcile --url … \
  --session local_example --run-key work-example --state-dir /tmp/dispatch-state
```

**For the Owner: the Codex session id (§12 D8).** Both keep `epoch` the
wrapper's own count; Codex hook rows stay `unsupported` until their fields are
verified.

| | A: session = run key (now) | B: session = `thread.started.thread_id` |
|---|---|---|
| when known | before launch: registration still precedes the child | ~0.2 s after launch, from `exec --json` on the child's stdout |
| needs | nothing new | the wrapper owning stdout and parsing JSONL; registration after launch (the fail-closed "register first" order is lost, or a second identity step is needed; the identity is immutable) |
| resume | a new run key is a new work | `exec resume` keeps the id: the wrapper must count epochs itself (D10) |
| Codex hook rows | never matched to the work | could match one by one if the hook's `session_id` is the thread id (unverified), after the server stops treating Codex rows as unsupported |

Recommended: A until Codex hook fields are measured.
