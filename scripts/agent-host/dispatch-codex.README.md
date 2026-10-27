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
