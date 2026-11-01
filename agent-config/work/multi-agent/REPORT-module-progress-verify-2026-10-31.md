# REPORT — R5 steps advance by rule on PROD (R5:5.1-5) · 2026-10-31, round 2 on 11-01

Plan step **R5:5.1-5**: "steps advance by evidence on PROD — at least one R5 step becomes done
by a `step_*` rule". This report cites a completion that **already happened on another step**,
R5:5.2-2. It does not use its own hand-in or landing as evidence (round 1 failed review for that:
a deliverable cannot prove its own completion).

## Evidence: R5:5.2-2 became done by its rule

Step R5:5.2-2 (Console release lanes view, mission M-253) carries this done rule:

    all[ step_tasks{state:"accepted"}, step_landed{}, step_stg_settled{} ]

The chain on PROD (times UTC, 2026-11-01). Rows marked *controller* are runtime events on the step;
the B5 row is a Tekton PipelineRun.

| Source | At | What |
|---|---|---|
| controller event 27675 | 07:00:28 | delivery task `t_01M6AVJZTGXA1N6DXHHMC6ZC7B` verifying → accepted, reason `review passed` (round 3; the Owner granted it on question `q_33e7689194e5b47d`, see controller events 27452/27453) |
| controller event 27759 | 07:22:24 | note: accepted result `c6e79c7b5ab3` is on platform main as `987cf72cf630` (the landing was approved on request 243) |
| PipelineRun `stgrel-4-1-987cf72c` (`cicd`) | 07:40:24–07:44:03 | B5 release to STG: build, agentrt-migrate, promote-images, gitops-sync, rollout all Succeeded |
| **controller event 27869** | **07:48:28** | **`plan_node_state_changed` active → done, cause `done_rule`, actor `controller`** |

The controller writes cause `done_rule` only when the step's rule evaluates True
(`api/internal/agentrt/store/facts.go`), and `all` needs every atom True
(`api/internal/agentrt/plan/rule.go`); so the step's tasks were accepted, its work was on main and
B5 had settled it on STG when the step closed. The cause is not `done_rule_manual`, and no sign-off
event is among the step's events the node read returns.

## How to check (read-only)

- MCP `get_plan node=R5:5.2-2`: `state: done`, `state_event.event_id: 27869`,
  `state_event.body.cause: done_rule`, `done_rule_json` as above, `task_counts {accepted: 7}`.
  The node read returns the step's latest 50 events; 27675, 27759 and 27869 are among them on
  11-01. Older events are on their streams: plan events on
  `GET /api/v1/agentrt/events?stream=plan:R5`, task events on `stream=mission:M-253`.
- HTTP: `GET /api/v1/agentrt/plan/R5:5.2-2` on the PROD platform-api (agentrt read role).
- Pipeline: `kubectl -n cicd get pipelinerun stgrel-4-1-987cf72c` (read-only identity).
- The build that evaluated the rule: the image digests of
  `kubectl -n bifrost-platform-prod get deploy platform-api platform-workers -o yaml` equal the
  `digest` result of TaskRun `stgrel-3-1-6ff7b6fe-build-platform-api` in `cicd`
  (`sha256:0e8b801a…`); `kubectl -n bifrost-platform-prod get pods -o custom-columns=NAME:.metadata.name,START:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount`
  shows the platform-api and platform-workers Pods started before 07:48:28 with no restarts
  (05:28:12Z and 04:12:18Z on 11-01; valid until those Pods are replaced).
- Approvals and questions: `get_request 243` (landing of 987cf72), `get_question q_33e7689194e5b47d`
  (round 3); `get_request 240`, `241`, `242` and `get_question 52` for the items below.

## What is on PROD

- platform `6ff7b6fe` on PROD by request 242 (10-31 23:12 CDT): the three step evidence atoms
  (M-249, request 241) and the Console module rows (M-248, `100fc5c6`, request 240). platform main
  is now `987cf72c`, which changes only the Console; PROD api and workers still run the
  `6ff7b6fe` build that evaluated the rule.
- Plan root R5 imported on the Owner's answer to question 52 (10-31 23:42 CDT); ledger
  `CUT-r5-modules-2026-10-31.md`.

## Not covered here

- R5:5.1-5 becomes done only when this report is accepted and lands (its rule is
  `all[step_tasks accepted, step_landed]`); this report does not claim that.
- `step_deployed` does not exist; PROD-only steps use the Owner's sign-off.
- The Console rendering of these rows was not viewed by the coordinator; the module detail page
  step R5:5.1-7 is planned on PROD, not started there.
