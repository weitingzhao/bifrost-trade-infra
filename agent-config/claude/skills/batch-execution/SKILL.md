---
name: batch-execution
description: >-
  Owner-triggered batch execution protocol — orchestrate all program phases via
  subagents with global QA and a structured Batch Execution Report. Use when Owner
  says 批量执行, batch execute, or confirms batch mode for a delivery program.
---

# Batch Execution Protocol

Owner says **「批量执行」** once → Agent orchestrates all remaining phases, global QA, and a final report without pausing between phases (unless a stop condition fires).

## Prerequisites

1. Read `.claude/skills/phase-execution/SKILL.md` — batch mode overrides rule 10 (auto-advance).
2. Read the program's own doc (PROGRESS.md or plan doc in its repo — the program skill names it). Program YAML
   under `bifrost-platform/config/programs/` and the `/api/v1/programs` API were deleted with Build Desk on
   2026-10-06; an old blueprint is in git history:
   `git -C bifrost-platform show 1a3327e:config/programs/<active|completed>/<id>.yaml`.
3. Read Owner commands: `.claude/skills/batch-execution/OWNER_COMMANDS.md`.

## Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Prepare** | Owner says 方案 / plan | Read the program doc + PROGRESS; output phase plan + risks; **do not execute** |
| **Execute** | Owner says 执行 / 批量执行 | Run Prepare checks, then Execute loop |
| **Accept** | Owner says 验收 | Run Global QA + Batch Execution Report; await Owner sign-off |

## Prepare Phase

1. Load the program doc (phases, order, dependencies, verify commands, acceptance, Owner decisions).
2. List phases: pending → done order; respect dependencies.
3. For each pending phase, note its verify command, acceptance criteria and whether the Owner signs it off.
4. Output **Batch Execution Plan** (phase list, verify commands, estimated scope).
5. Wait for Owner **「批量执行」** unless already in batch mode.

## Execute Loop

Work goes by **block, not by step** (Owner 2026-11-14，LAW-7): a block is a piece one agent can take from code to
live on its own. The orchestrator cuts the pending phases into blocks; phases that only make sense together are
one block. One agent does a whole block (write, test, land, release, check) and is judged on the result.
Blocks run in order unless the program doc says they are independent.

### Per-block steps

1. **Launch one subagent per block via the `Agent` tool** — `subagent_type` = the Bifrost mode agent matching
   the block (`bifrost-product` / `bifrost-ops` / `bifrost-promote` / `bifrost-research`, defined in
   `.claude/agents/`), falling back to `general-purpose`. Pass the goal, the boundaries and what to hand back
   (from the program doc), and the program skill path. Do not pass steps.
2. **Check the result** when the subagent returns: run the verify command of each phase in the block (if the
   program doc names one). A failure goes back to the same agent to fix; pause only on a stop condition below.
3. **Record progress** in the program doc (phase ✅, date, change summary — phase-execution rule 8) and in the
   in-chat Phase report. There is no Console or MCP progress API: Build Desk (`/api/v1/programs`,
   `report_phase_progress`, `create_session`) was deleted on 2026-10-06.
4. **Owner sign-off**: phases the Owner signs off pause after verify passes unless the Owner pre-authorized the
   batch; the Owner confirms in the conversation and the sign-off is written into the program doc.
5. **Auto-advance** to the next block unless stop condition (see below).

### Stop conditions (pause batch)

- Crossing a safety boundary, something that cannot be taken back, something the Owner must do by hand, or a
  refusal by the permission classifier or a guard (Owner 2026-11-14; the same list as phase-execution，LAW-5)
- Architecture-level decision needed (new RPC, schema, dependency — see phase-execution rule 5)
- Owner interrupt

Any other failure the agent diagnoses and fixes itself, and says so in one line of the report.

## Global QA (after all phases)

1. Run program-level verification from the program doc / skill (if defined).
2. Cross-check: no scope creep, no live-trading paths enabled (D10 freeze).
3. Type-check / test matrix per repo touched:
   - Go: `go test ./...`
   - TS: `npm run lint && npm run build`
   - Python: `make lint && make test`
4. Post-completion: list new capabilities, new risks and proposed follow-up work in the report. Follow-up work
   that should land in the Ops Desk operate queue is a proposal only — nothing is enqueued without the Owner's
   approval in the conversation.

## Batch Execution Report

Output after Global QA (also structure for Owner 验收):

```markdown
## Batch Execution Report — {program-id}

### Summary
- Phases executed: N / M
- Failures the agents fixed themselves: ...
- Stop conditions hit: none | ...

### Per-phase results
| Phase | Status | Verify | Notes |
|-------|--------|--------|-------|

### Post-completion (for Owner review)
- New capabilities: ...
- New risks: ...
- Proposed follow-up / operate queue items: ...

### Verification
- Commands run + results

### Where to see it in Ops
- page, what to look at; "nothing" if there is nothing

### Cost
- tokens, time

### From the agents who did it
- what was smooth, what blocked, what to add or delete
```

## Discipline

- Minimize scope per block — no drive-by refactors
- UI strings English; Owner chat 中文
- Do not enable live trading (D10)
- Keep the program doc current — it is the only progress record
