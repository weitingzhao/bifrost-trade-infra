# DESIGN — Console module progress view (post-transition module 1) · 2026-10-31

Owner ask (10-31): one row per module in the PROD Console, steps that move on real runtime
evidence, a "N steps to go" countdown, every cell links to its record. Built on Design v3.6
(`design/ops/WorkPage`, `ItemDetail`). Replaces the coordinator's Claude dashboard once live.

## Findings (PROD 10-31, platform origin/main 9f4c873e)

- The controller already advances steps by done rule (Facts → Close → Activate → Rules,
  `controller.go:711-723`); state changes only via `SetStepState` with an event chain.
- R4 never moves because nothing feeds it: 0 tasks carry an R4 `plan_node_id`
  (432/438 accepted tasks are off_plan), 43 steps have the empty rule `{}`, 15 have
  `external_verified` bindings that read Unknown, external work is registered on items
  not steps (`planbindings.go:63-65` needs `n.Node == b.Step`).
- The rule grammar has no aggregate atom: `task_accepted` names a task id in advance; nothing
  reads landing, B5 settlement or a deployment for "the step's own work".
- PROD `plan-standing` v1 grants `done_rules` and `active_on_lease`: the FIRST done rule of a
  step not done is decided without an Owner card when it names only the step's own tasks or
  the Owner's sign-off and does not hold yet (`planchange.go:168-200`).
- Console Work → Plan (`WorkPlanView`, `PlanTree.tsx`) shows one text line per item and raw
  step states in a folded `<details>`; no stage bar, no countdown, no evidence links.

## Decisions (coordinator, on recommendation; audit after)

D1 **Option A**: evidence attaches to steps; the controller advances them. Rejected: B (a second,
   read-only progress number beside controller state) and C (coordinator self-report).

D2 **A step is a deliverable.** Its own tasks (`task.plan_node_id = step`) are the evidence.
   Trust is the same as `task_accepted` today (a task needs independent review to be accepted);
   no `step.mission_id` gate, because `rebind_step` is an Owner card per step. Accepted risk:
   a proposer could hang a trivial task on a step — mitigated by D3 requiring landing and STG.

D3 **Four new atoms** (closed grammar, `plan/rule.go`; facts in `store/facts.go` `stepFacts`):
   - `step_tasks {state:"accepted", min:1}` — at least `min` of the step's own tasks in `state`.
   - `step_landed {}` — the step has ≥1 accepted task whose work lands, and every landing
     operation of the step's accepted tasks is landed on main. False when none or any failed.
   - `step_stg_settled {}` — every landed operation of the step's tasks is a member of a B5
     batch that settled verified. Unknown while a batch is open; False when none / failed.
   - `step_deployed {env:"prod"}` — the env's observed deployment contains every landed commit
     of the step (same deployment read as `deployment_verified`). Unknown when unobserved.
   Three-valued like every atom; Unknown never makes a step done. All four name only the step's
   own facts, so `standingRule` accepts them as a first rule (no Owner card).

D4 **No new tables, no new API fields.** plan-view already carries per-step state, tasks and
   `tasks[].delivery`; the Console computes "steps to go" = total − done − dropped. The closed
   snapshot schema (`planSnapshotSchema.ts`) stays unchanged.

D5 **Producers tag the step.** Hand-ins and dispatches pass `plan_node_id` (step id) on
   `propose_tasks`; external work registers on the step. Untagged work stays off_plan as today.

D6 **Console module rows** (v3.6 WorkPage): per item — id, lane, title; a segmented bar, one cell
   per step in plan order (done = solid, active = hatched, planned = hollow, dropped = omitted);
   "N steps to go" (English UI copy); "Waits on" from dependency edges; each cell opens its step:
   state, done rule in words, and links (task → `#work?goal=&task=`, landing op, approval
   `#approvals?id=`, question `#questions?id=`). Items sorted by mainline order. Files only under
   `console/src/pages/shell/agents/**` (not `console/src/api/**`).

D7 **Registration.** A new root R5 "Post-transition modules" by one plan import (one Owner card),
   imported AFTER the atoms run on PROD so finished steps import as `[x]`; then each open step's
   first rule is set under standing. Ledger: `CUT-r5-modules-2026-10-31.md`. Order (Owner 10-31):
   5.1 = this module, 5.2 = release lanes per application, 5.3 = unattended PROD (W-56),
   5.4 = S5 (content checker).

## Lanes (parallel)

- A core (`api/internal/agentrt/plan`, `store`): D3 + `standingRule` + tests (PG, `-race`,
  `AGENTRT_TEST_REQUIRED=1`). Core landing → Owner approves the core landing card.
- B console (`console/src/pages/shell/agents/**`): D6 against the real PROD fixture
  `plan-view-pv2-prod-r4.json` plus a fixture with advanced steps. Landing by rule.
- C coordinator: D5 wiring (handin wrapper / dispatch), the R5 ledger, step rules after release.

## Order

A + B + C in parallel → independent review → land A (Owner card) and B → B5 auto-STG → PROD
release (Owner card) → R5 import (Owner card) → set first rules (standing) → watch steps move
on PROD → retire the Claude dashboard.

## Outcome (10-31)

- D3 shipped as three atoms: `step_tasks` (state "accepted" only), `step_landed`, `step_stg_settled`.
  `step_deployed` was left out (no ancestry reader inside the evaluation transaction); PROD steps
  use the Owner's sign-off. Review 630 (Codex): 1 blocking, 1 should-fix, both fixed before landing.
- D6 landed as platform `100fc5c6` (#240, size and presentation guardrails), D3 as `6ff7b6fe` (#241);
  both on PROD 23:12 (#242).
- D5: `handin.sh --plan-node` is infra `cc3891f`, waiting for the next Owner push of infra scripts.

## Not verified yet (at design time)

- Whether landing op → task and B5 member → op links are readable inside `stepFacts`'s tx
  (lane A confirms; if not, the atom reads the folded note the same way `/landing/missions` does).
- Whether "contains landed commit" for `step_deployed` needs git ancestry in the controller; if
  it does and no reader exists, `step_deployed` is deferred and PROD steps use `owner_signoff`.
- The plan import ledger format for step rules (C confirms before writing R5).
