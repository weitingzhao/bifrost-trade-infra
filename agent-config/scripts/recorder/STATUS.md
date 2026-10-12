# The lane recorder, slice 1 — NOT trusted, NOT wired

This directory is on `main` by the Owner's decision of 2026-10-12 ("主线选 ②", W-66): after six implementation
rounds the slice was merged as untrusted code instead of opening further rounds.

**Nothing may read its output for a decision** — no board, no Console page, no pipeline, no agent — until
`TD-319` in `agent-config/TECH_DEBT.md` is closed. A consumer added before that may only show the output beside
the hand-maintained one, marked as a shadow.

Known wrong (review 113; each has a test marked `xfail(strict=True)` that will fail the day it is fixed without
removing the mark):

1. A log that is exactly at its limit and is followed by a torn tail records no `limit_log` break.
2. `record_created` takes `since` too late when a continuously found record has an observation whose condition is
   Unknown in between.
3. `next_not_sent` takes `since` from the declaration when the wait it depends on is settled in another log.

Also open: single-point mutants that no test catches (see `REPORT-7`/`REPORT-8` of the lane and TD-319).

How it gets trusted: the three fixed and independently reviewed; survivors at zero under the checker's
definition; seven days running beside the hand-maintained board with no unexplained difference.
