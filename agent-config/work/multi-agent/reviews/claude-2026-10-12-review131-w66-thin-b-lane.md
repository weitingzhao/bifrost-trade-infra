VERDICT: fix first
A FALSE STATUS OR A CHANGED COMMAND: found
RULES THAT ONLY LACK A TEST: 2

(Review 131 by a Claude subagent, commit 48eb76d; it used lane.py from the command line about 80 times. Stored by the coordinator from what the reviewer returned; evidence in ~/agent-work/claude-review-131/.)

With a valid kind and names and quotes within the limits everything was right: the real pattern (sh -c 'sleep 20; …; echo "exit=$?" > job.done') starts, survives a kill -9 of the caller and its process group, stop ends only that step with TERM, four simultaneous starts lose no entry. (c) and (d): nothing found.

MUST FIX before real use:
- P1-1 lane.py:111-122, :161-174 — when the recorder refuses to record the run (a name longer than 80 characters; a kind outside implement / verify / review / merge / other, e.g. `fix`, `ci`, `release`), `start` still exits 0 with a step id, the job runs, and `status` shows nothing. Fix: before starting, reject a kind outside the list and a name / who longer than 80 characters or with control characters; when the wrapper's output says `start not recorded`, the JSON gets `"recorded": false` and the exit code is 3; `status` prints a line for a work whose fold has unrecorded runs.
- P1-2 lane.py:125-135 — `record` with a quote longer than 200 characters or with a newline: declare and start are written, finish fails, the step shows as running for ever and lane has no command to settle it. Fix: clean the quote before the first write (first line, no control characters, cut to 200); if start or finish still fails, print the id of the step left behind.
- P2-1 lane.py:168-174 — a dead step keeps counting elapsed time and shows OVER for ever. Fix: no OVER for a dead step; show the fold's `since`.

CAN WAIT: P2-2 after an exit 3 the entry is keyed `pending:<pid>`: status loses `usual`, stop by step id says the wrapper is gone; P2-3 a wrapper that dies before starting anything also yields exit 3; P2-4 three simultaneous starts of a work not yet open: two fail to open and do not start; P2-5 a corrupt lanes.json breaks status and stop, and the file is truncated before it is rewritten; P2-6 status does not show results (a failed job looks like a finished one); two missing tests; P3 items (the text status shows no ids; a mistyped work name creates a work; no command to settle a dead step; lanes.json only grows; lane.py dodges a static check of test_round3.py:568 with io.StringIO).

Usage until the rest is fixed: kinds only implement / verify / review / merge / other; one line of quote; open a new work with one start before starting more; read results from `rec.py fold`, not from `status`.
END OF REPORT

Coordinator follow-up (2026-10-12): the three must-fix items were fixed by Codex and checked by the coordinator from the command line (a rejected kind starts nothing; a long two-line quote is cleaned; a killed wrapper shows dead, never OVER); 33 tests pass. The CAN WAIT items are listed in TD-319.
