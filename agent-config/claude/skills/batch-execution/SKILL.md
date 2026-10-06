---
name: batch-execution
description: >-
  Owner-triggered batch execution protocol — orchestrate all program phases via
  subagents with global QA and a structured Batch Execution Report. Use when Owner
  says 批量执行, batch execute, or confirms batch mode for a delivery program.
parity-id: batch-execution-v1
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

For each pending phase (sequential unless the program doc says phases are independent — default sequential):

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌────────────────┐
│ Subagent    │ ──► │ Phase work   │ ──► │ Verify      │ ──► │ Program doc +  │
│             │     │ (scope only) │     │ (2 retries) │     │ phase report   │
└─────────────┘     └──────────────┘     └─────────────┘     └────────────────┘
```

### Per-phase steps

1. **Launch a subagent via the `Agent` tool** — `subagent_type` = the Bifrost mode agent matching the phase
   (`bifrost-product` / `bifrost-ops` / `bifrost-promote` / `bifrost-research`, defined in `.claude/agents/`),
   falling back to `general-purpose`. Pass:
   - The phase goal, scope and acceptance from the program doc
   - The program skill path
   - Scope constraint: current phase only
2. **Self-check** when the subagent returns:
   - Run the phase's verify command (if the program doc names one) plus the repo gates (phase-execution rule 4)
   - On failure: retry phase work up to **2 times**; then **PAUSE** and report to Owner
3. **Record progress** in the program doc (phase ✅, date, change summary — phase-execution rule 8) and in the
   in-chat Phase report. There is no Console or MCP progress API: Build Desk (`/api/v1/programs`,
   `report_phase_progress`, `create_session`) was deleted on 2026-10-06.
4. **Owner sign-off**: phases the Owner signs off pause after verify passes unless the Owner pre-authorized the
   batch; the Owner confirms in the conversation and the sign-off is written into the program doc.
5. **Auto-advance** to next phase unless stop condition (see below).

### Stop conditions (pause batch)

- Verify failed after 2 retries
- Architecture-level decision needed (new RPC, schema, dependency — see phase-execution rule 5)
- Uncovered requirement not in the program doc's acceptance criteria
- Owner interrupt

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
- Verify failures (retried): ...
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

### E2E suggestions
- ...

### Follow-ups
- ...
```

## Discipline

- Minimize scope per phase — no drive-by refactors
- UI strings English; Owner chat 中文
- Do not enable live trading (D10)
- Keep the program doc current — it is the only progress record
