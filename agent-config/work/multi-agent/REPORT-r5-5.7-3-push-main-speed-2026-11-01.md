# REPORT — infra push-main runs its tests side by side (R5:5.7-3) · 2026-11-01

Plan step **R5:5.7-3** (done by the Owner's sign-off): infra's push to main no longer waits ~14 minutes for its
tests. This report records what landed and what was measured, for the sign-off.

## What is on infra main

Three commits, pushed by the Owner with `scripts/release/push-main.sh` on 2026-11-01:

| Commit | What |
|---|---|
| `21e765e` | push-main runs infra's test files side by side (`scripts/release/push_main_tests.py`: one process per test file, a large one in parts, up to 8 at a time by default, slowest first by the last run's times), and runs the landing scripts' own tests when a push changes `agent-config/scripts/landing/`; three slow existing tests wait less |
| `ff7a3fc` | a test stopped at its deadline no longer crashes the runner (it only ever refused a push, never let one through) |
| `b1c139f` | fix for a failure the first real run found (below) |

## Measured (push-main's own output, the same three test directories: `scripts/release`, `scripts/agentrt`, `scripts/agent-host`)

| Run (CST) | Runner | Result | Test time |
|---|---|---|---|
| 11:17, commit `cc2996a` | before 5.7-3: one pytest process | 1124 passed, 1 skipped | 836 s |
| ~12:09, commit `ff7a3fc` | 5.7-3 | 72 of 73 runs passed — refused the push | 228 s |
| ~12:59, commit `b1c139f` | 5.7-3 | 73 of 73 runs passed — pushed (with `fb8142e`, an R5:5.5 registry commit) | 189 s |

The step's target was "under 5 minutes": 189 s.

## The failure the first run found, and its fix

The ~12:09 run failed one case of `scripts/agent-host/test_probe_gitea_protection.py`. Cause: 5.7-3 had added a
`sitecustomize` that caps the probe's sleeps at 10 ms, rewritten for every case of a test with the path of that case's
transport shim; the paths have one length, so a rewrite within the same second kept the file's size and mtime and
Python reused the previous case's cached bytecode, which ran a shim already deleted (`site` turns that error into a
warning, so the probe ran with no fixture). It can show only where Python writes bytecode: reproduced with bytecode written, never without; the coordinator's tool
environment sets `PYTHONDONTWRITEBYTECODE`, and its runs passed. That the Owner's run wrote bytecode is the most
likely reading, not checked. `b1c139f` keeps the text constant,
passes the shim's path in `PROBE_TEST_FAST_SLEEP_CHAIN`, and fails the probe (its Python exits 97) if the shim cannot
run.
Checked with bytecode written: the affected cases 3/3 runs (13 subtests failed before), the whole file 44 passed, the
three directories through `push_main_tests.py` 73/73.

## Where it applies

The workspace's shared infra checkout was fast-forwarded to `b1c139f` after the push (push-main leaves a shared
checkout that holds other sessions' edits as it is, and said so), so every `push-main.sh` run of an infra commit from
it now uses the side-by-side runner. Platform pushes are unchanged (their
fast tests are `go vet` and the touched packages, as before).

## How to check

- `git log --oneline 803d04b..b1c139f -- scripts/release/push_main_tests.py scripts/release/push-main.sh
  scripts/agent-host/test_probe_gitea_protection.py` on infra main lists the three commits.
- Any later `push-main.sh` run of an infra commit prints `N of N test runs passed (… files) in S s, J at a time` (J is
  up to 8 by default; `PUSH_MAIN_TEST_JOBS` or `--jobs` changes it).
- `python3 -m pytest -q scripts/release/test_push_main.py` covers the runner: test files run side by side, a large
  file runs in parts with each test once, and each exit code is read on its own.
