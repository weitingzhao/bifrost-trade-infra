# REPORT — the coordinator's module dashboard retired; module progress is read in the Console (R5:5.1-6) · 2026-11-01

Plan step **R5:5.1-6**: retire the coordinator's Claude dashboard for module progress. The design
(`DESIGN-module-progress-2026-10-31.md`, lines 3–5) set the Console view to replace that dashboard
once live; step R5:5.1-7 (added 11-01, title ending "和 Claude 进度页对齐") added the module detail
page for it. This report records the retirement, which has already happened, and what the Console
shows and does not show in its place.

## Retired (done before this report was handed in)

At 2026-11-01 09:18Z the coordinator gave its dashboard (the Claude artifact "模块进展视图进度",
private to the Owner's claude.ai account) one final update; it is not updated after that. The page's
summary now reads:

> 本页已于 11-01 03:18 CST 退役，不再更新。模块进展请看 Console：https://ops.bifrost.lan/#work?section=plan&root=R5&node=R5%3A5.1

## What replaces it

`https://ops.bifrost.lan/#work?section=plan&root=R5&node=R5%3A5.1` on the PROD Console (the Work
home without `root=R5` opens R4, where 5.1 has no row; on a module row the link to the detail is
labelled "Open module 5.1" for assistive technology and shows "5.1"). It ships in platform
`3e7b8e48` (R5:5.1-7, landed on request 244, released to PROD by request 245; PipelineRun
`bifrost-deliver-platform-prod-2a68f4fa2f3285d5-1` Succeeded at 09:08:27Z).

Read on PROD at 09:10Z for module 5.1:

| Dashboard part (hand-kept) | Console module detail (computed) | As read at 09:10Z |
|---|---|---|
| Countdown "N steps left" | Steps to go, from the controller's step states | "1 step to go · of 7 · 6 done" |
| What waits on the Owner | Your actions found: "Owner steps not done, plus what Needs you now counts; cards without evidence here are not counted (see Needs you)." | "0" |
| Now / next | Now (step in progress), Next in plan order | Now: none · Next: 5.1-6 |
| Step table with notes | Steps in plan order: state, latest own task, latest check of it | 7 rows; 5.1-5 and 5.1-7 "Review pass" |
| Log | Recent activity: plan events of the root's latest 20, the runtime's latest 20 ended tasks and checks, questions and requests | 5.1-7 and 5.1-3 "In progress → Done · done_rule" |

## What the Console does not show (the dashboard did)

- **Phases that are not plan steps.** The dashboard had 15 rows (research, design, reviews,
  landings, STG and PROD releases); the Console counts the module's 7 plan steps.
- **Free-text notes and an estimate.** The dashboard carried the coordinator's notes and an ETA;
  the Console's ETA cell shows "Unknown" with the line "Capacity and duration observations are not
  available"; the plan-view sets it so for now (`api/internal/agentrt/store/planviewsnapshot.go:187`).
- **Every card for the module.** A card is listed only with direct evidence (its task, a done rule
  naming it, or a plan change in the recent window); the page says a card of the module can be
  missing.
- One defect seen at 09:10Z: Recent activity shows "Main reconciled: landed `<nil>`". The text is
  written by platform-api (`api/internal/agentrt/store/landing_reconcile.go`, `appendMainRecord`,
  format string `"Main reconciled: %v %v"` filled with the record's kind and outcome; event 28285
  has no outcome); the Console shows it as written. It is not yet in `TECH_DEBT.md`.

## How to check

- The 09:10Z numbers: MCP `get_plan root=R5` — the 5.1 steps' `state_event`: 5.1-1, 5.1-2 and
  5.1-4 done at the import (04:42:38Z), 5.1-5 at 08:25:28Z (event 28219), 5.1-3 at 08:57:32Z
  (28400), 5.1-7 at 09:01:57Z (28412); 6 of 7 done before 09:10Z, 5.1-6 planned.
- The release: `kubectl -n cicd get pipelinerun bifrost-deliver-platform-prod-2a68f4fa2f3285d5-1`
  (read-only identity) — Succeeded, completionTime 09:08:27Z; MCP `get_request 245` names that run
  and revision `3e7b8e48`.
- The page: after this report lands, R5:5.1-6 becomes done by its rule and the address above shows
  module 5.1 with all steps done instead of "1 step to go".
- The retirement: the dashboard is private to the Owner's account; the Owner sees the quoted text
  on it, and its summary and steps data sets both carry `updated.at` 2026-11-01T09:18:00Z.
