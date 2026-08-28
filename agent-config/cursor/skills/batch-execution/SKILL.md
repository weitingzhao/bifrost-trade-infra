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

1. Read `.cursor/rules/phase-execution.mdc` — batch mode overrides rule 10 (auto-advance).
2. Read program blueprint: `bifrost-platform/config/programs/{program-id}.yaml`.
3. Read Owner commands: `.cursor/skills/batch-execution/OWNER_COMMANDS.md`.
4. Fetch program context via MCP `get_program_context` (fallback: `GET /api/v1/programs/{id}`).

## Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Prepare** | Owner says 方案 / plan | Read blueprint + PROGRESS; output phase plan + risks; **do not execute** |
| **Execute** | Owner says 执行 / 批量执行 | Run Prepare checks, then Execute loop |
| **Accept** | Owner says 验收 | Run Global QA + Batch Execution Report; await Owner sign-off |

## Prepare Phase

1. Load program YAML + API state (`get_program_context`).
2. List phases: `pending` → `done` order; respect `depends_on`.
3. For each pending phase, note `verify_cmd`, `acceptance`, `sign_off`.
4. Output **Batch Execution Plan** (phase list, verify commands, estimated scope).
5. Wait for Owner **「批量执行」** unless already in batch mode.

## Execute Loop

For each pending phase (sequential unless `depends_on` allows parallel — default sequential):

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ Task        │ ──► │ Phase work   │ ──► │ verify_cmd  │ ──► │ MCP progress │
│ subagent    │     │ (scope only) │     │ (2 retries) │     │ + sign-off   │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
```

### Per-phase steps

1. **Launch Task subagent** (`subagent_type: generalPurpose` or domain-appropriate) with:
   - Phase `prompt_template` rendered from blueprint
   - Skill path from program YAML
   - Scope constraint: current phase only
2. **Self-check** when subagent returns:
   - Run `verify_cmd` from blueprint (if set)
   - On failure: retry phase work up to **2 times**; then **PAUSE** and report to Owner
3. **Report progress** (Wave 3 MCP — required when platform-api reachable):
   - `report_phase_progress` → `POST /api/v1/programs/{id}/phases/{pid}/progress`
   - Body: `{ "status": "done"|"failed", "summary": "...", "verify_passed": true|false }`
   - **Fallback** (offline / MCP unavailable): append to in-chat Phase completion report only
4. **Owner sign-off** (API-backed programs):
   - After verify pass, mark phase ready; in batch mode auto-request sign-off via API if Owner pre-authorized batch
   - Otherwise pause for Owner sign-off per phase when `sign_off.required: true`
5. **Auto-advance** to next phase unless stop condition (see below).

### Stop conditions (pause batch)

- `verify_cmd` failed after 2 retries
- Architecture-level decision needed (new RPC, schema, dependency — see phase-execution rule 5)
- Uncovered requirement not in blueprint acceptance criteria
- Owner interrupt

## Global QA (after all phases)

1. Run program-level verification from blueprint / skill (if defined).
2. Cross-check: no scope creep, no live-trading paths enabled (D10 freeze).
3. Type-check / test matrix per repo touched:
   - Go: `go test ./...`
   - TS: `npm run lint && npm run build`
   - Python: `make lint && make test`
4. Call `submit_post_completion` MCP tool (or `POST /api/v1/programs/{id}/complete`) with:
   - `new_capabilities`, `new_risks`, `operate_queue_items` from blueprint `post_completion`
   - Items enter **`pending_review`** — Owner must approve before Operate queue injection

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

### Post-completion (pending Owner review)
- New capabilities: ...
- New risks: ...
- Operate queue items (pending_review): ...

### Verification
- Commands run + results

### E2E suggestions
- ...

### Follow-ups
- ...
```

## MCP Integration (Wave 3)

| Tool | Route | When |
|------|-------|------|
| `get_program_context` | `GET /api/v1/programs/{id}` | Start of Prepare + each phase |
| `report_phase_progress` | `POST .../phases/{pid}/progress` | After each phase verify |
| `submit_post_completion` | `POST .../complete` | End of Global QA |
| `approve_post_completion_item` | `POST .../post-completion/{itemId}/approve` | Owner only — moves item to Operate queue |

MCP server: `user-bifrost-platform` (platform-api proxy). If MCP auth fails, use Copy/Paste fallback for session pack only — progress reporting falls back to in-chat reports.

## Session hooks

On agent session stop, `.cursor/hooks/on-session-stop.js` POSTs session metadata to platform-api (program id, phase, duration). Ensure `PLATFORM_API_URL` and operator token are configured locally.

## Discipline

- Minimize scope per phase — no drive-by refactors
- UI strings English; Owner chat 中文
- Do not enable live trading (D10)
- Update `PROGRESS.md` when program spans infra docs
