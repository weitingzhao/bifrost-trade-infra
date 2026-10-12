# The lane recorder, slice 1 — NOT trusted, NOT wired

This directory is on `main` by the Owner's decision of 2026-10-12 ("主线选 ②", W-66): after six implementation
rounds the slice was merged as untrusted code instead of opening further rounds.

**Nothing may read its output for a decision** — no board, no Console page, no pipeline, no agent — until
`TD-319` in `agent-config/TECH_DEBT.md` is closed. A consumer added before that may only show the output beside
the hand-maintained one, marked as a shadow.

State on 2026-10-12, after the thin first slice (the Owner resumed this work to replace the coordinator's
hand-kept progress board; usable first, not polished):

- The command line works end to end: `open`, `close`, `declare`, `start`, `finish`, `note`, `owner-open`,
  `owner-ready`, `owner-close`, `fold`, `run`, `observe`. Review 130 used it for real (about 38 runs, 45 folds)
  and found no false statement in the folded document.
- Review 113's three wrong answers are fixed; their tests no longer carry `xfail`.
- How to use `run` today: stop a wrapped job only with TERM to the wrapper (never `kill -9`, never a group
  kill — the child would live on unrecorded); run `observe` before `fold` (a dead wrapper otherwise shows as
  running for up to three minutes). The child's output goes to two files in its run directory; the wrapper says
  where on standard error before the child starts.
- Known and left for later (review 130): descriptors above 2 are closed for the child; only TERM, INT and HUP are
  forwarded; one failed heartbeat write stops the bookkeeping of that run; the half of `observe` that reads the
  platform is not built.

How it gets trusted: the three fixed and independently reviewed; survivors at zero under the checker's
definition; seven days running beside the hand-maintained board with no unexplained difference.

The one permitted reader during the shadow week is the comparer described in
`agent-config/work/multi-agent/PLAN-recorder-shadow-run-2026-10-12.md`; its output goes to a difference log, never to a page.

`lane.py` is the coordinator's entry: `start` dispatches detached runs; `record` records non-process steps.
Use its `owner-open`, `owner-close`, `stop`, and `status` commands; the trust and shadow restrictions above still apply.
