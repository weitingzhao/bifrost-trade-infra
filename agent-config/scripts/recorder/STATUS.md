# The lane recorder — retired 2026-10-22

`lane.py`, `rec.py` and the library behind them were removed on 2026-10-22 (W-31 2.3-3; the Owner's
2026-10-21 decision "2.3 的四条都照推荐 A", item 4: retire them once PROD has imported the logs).

Where the history went:

- Each of the 17 local logs (`~/agent-work/recorder-root/<work>/events.jsonl`) is a stream
  `legacy:recorder:<work>` in the agent runtime, on PROD and on STG: one event per line plus one
  `legacy_imported` marker, the hash chain checked from the first line to the last, local paths masked
  (each masked line keeps the digest of its original). 1,108 lines in all. Read them with
  `GET /api/v1/agentrt/events?stream=legacy:recorder:<work>`.
- PROD imported them through 17 Owner decision cards, the last answered 2026-10-22 23:00 UTC; STG through
  the signed card rule on 2026-10-21. Proposing the same log again answers "already imported" and writes
  nothing (checked on PROD with guard-1, 2026-10-22).
- The board's observer rounds (`recorder-root/_observer/`) were not imported; they went with the local board
  (W-31 2.5 slice 5).
- The code: `git log -- agent-config/scripts/recorder/` (the last full tree is at `edf72e0`). TD-319, its
  defect list, closed with the retirement: the code it described no longer exists.

Dispatch and step bookkeeping now live in the agent runtime (missions, tasks, attempts, the plan and its
sign-offs), shown in the Ops Console.
