# Claude work registration (TD-446)

`register-claude-work.py` records an existing Claude session in Work → Plan.
It launches no process, including Claude or Git. Registration grants no execution
permission; `Submitted` records a result and never completes a plan step.

**Coordinator's open-session step:** register the Claude work against its real
plan node, retain its state directory, send a heartbeat every 30 seconds while
the session is active, then submit its report (or explicitly abandon it).

Use `--session local_accccb4e-dispatch` with the coordinator's reporter token.
This is the registrant's session, not the newly opened Claude conversation ID.
As documented in `~/agent-work/dispatch.sh`, this dispatch session belongs to
the reporter token; the coordinator's own conversation session belongs to the
MCP operator token. A runtime session belongs to the first token that wrote
with it. Do not substitute an operator-owned session. Give each work attempt
a unique run key; keep the session, key, URL and state directory on retries.

## Coordinator example

Run from the infra checkout. This example targets **STG API :30878** through
the VIP; :30879 is its Console. The port is declared in
`k8s/base-platform/manifest.yaml` and the STG URLs in
`k8s/overlays/platform-stg/config/clusters.yaml`.
Use an existing database plan-node ID for `node` (the example comes from TD-446),
and ensure the reporter credential is configured for this environment.
For an authorized PROD registration use API :30876, a new run key and a separate
state directory. Do not repoint an existing state directory to another server.

```sh
infra=$(pwd)
run_dir="$HOME/agent-work/claude-td446-stg"
node='R4:4.9-9'
mkdir -p "$run_dir"
cat > "$run_dir/desc.json" <<'JSON'
{
  "v": 1,
  "kind": "agentrt.external_work/v1",
  "task": "验证 Claude 会话登记、心跳与回报",
  "executor": "claude",
  "provider": "anthropic",
  "repo": "bifrost-trade-infra",
  "branch": "w31/td446-claude-work",
  "acceptance_refs": ["TD-446"],
  "estimate_minutes": [5, 15]
}
JSON

# Only the caller reads the file. The CLI reads this environment variable only.
set +x
claude_work() {
  BIFROST_DISPATCH_TOKEN="$(cat "$HOME/.config/bifrost/lineage-reporter.token")" \
    python3 "$infra/scripts/agent-host/register-claude-work.py" "$@"
}
claude_work register \
  --url http://192.168.10.100:30878 \
  --session local_accccb4e-dispatch --run-key claude-td446-stg-1 \
  --root R4 --node "$node" --description "$run_dir/desc.json" \
  --state-dir "$run_dir/state"

# One call per heartbeat; repeat every 30 seconds only while work is active.
claude_work heartbeat --state-dir "$run_dir/state"

# After the session has written its actual REPORT.md:
claude_work submit --state-dir "$run_dir/state" --report "$run_dir/REPORT.md"
```

Check STG Console `http://192.168.10.100:30879/#work?section=plan&root=R4`
for Live work within one minute, then Finished today after submission.
These commands are a manual acceptance procedure; the offline tests do not
contact STG or PROD. A 401/403 fails closed: check the reporter credential and
session ownership, then retry the same command after resolving the cause.

`submit` sends the SHA-256 of the absolute report path and of the report bytes,
`exit_code` (default `0`), and `commit_shas` (default `[]`). Report content and
its path are never uploaded. Use `--exit-code 1` for a failed session, and
repeat `--commit-sha <full-lowercase-SHA>` for each known commit (at most 100).
The caller supplies these facts; this CLI neither infers success nor runs Git.
The report must exist. CLI success exits `0`, even when reporting a nonzero
session exit code; an unsuccessful command exits `1` (`2` for argument errors).

To explicitly end work without a report:

```sh
claude_work abandon --state-dir "$run_dir/state"
```

This sends the server's `cancelled` event. It does not kill or inspect Claude.
The Codex wrapper submits nonzero exits when it has a durable exit receipt;
an uncertain lost child stays Unconfirmed. Likewise, do not abandon a Claude
session merely because its heartbeat stopped: reconcile with the session first.

## Recovery and tests

Each state directory holds one run and a process lock. Repeating `register`
after a successful registration does not upload/register again or send a second
`started`. If the registration reply was lost, it resends the same idempotency
key. Pending events are written atomically before POST and replayed unchanged
before reading the server's sequence. An incomplete registration requires the
original `register` command; any subsequent command can replay an event.
Submitted/cancelled runs cannot restart. Repeating an identical submit/abandon
does not post another terminal event. Heartbeat exits with an error for a
terminal run, so the coordinator should stop its loop.

Do not edit/delete state or retry a failed submission with a changed report,
exit code or commit list; restore the original inputs and repeat it. A new
attempt needs a new key and directory. Description bytes, root, node, URL and
session are immutable for a run. The CLI imports `dispatch-codex.py` beside it
for the HTTP client (redirects refused), atomic state and durable event journal;
keep both files together. The token is never stored in state or accepted as an
argument. No token file is read by Python.

```sh
python3 -m pytest -q scripts/agent-host/
ruff check scripts/agent-host/dispatch-codex.py \
  scripts/agent-host/register-claude-work.py \
  scripts/agent-host/tests/test_register_claude_work.py

# Supplemental validation if loopback bind is denied by a sandbox:
BIFROST_TEST_HTTP=memory python3 -m pytest -q \
  scripts/agent-host/tests/test_register_claude_work.py
```

The default tests use a loopback fake HTTP server. Explicit `memory` mode runs
the same HTTP handler and urllib response/error/redirect chain entirely in
memory. It supplements, rather than replaces, the unchanged Codex wrapper
tests and the normal loopback tests. Neither mode runs Claude or uses a real
credential; the Claude tests fail if the CLI launches a subprocess.
