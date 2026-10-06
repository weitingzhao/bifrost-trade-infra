# Owner Commands — Batch Execution

Standardized Owner phrases for running a phased program in the conversation. Progress lives in the program's
own doc (PROGRESS.md / plan doc); the Ops Console no longer tracks programs (Build Desk deleted 2026-10-06).

## Command table

| Owner says | Mode | Agent action |
|------------|------|--------------|
| **方案** / **plan** / **出方案** | Prepare | Read the program doc + PROGRESS; output Batch Execution Plan; **no code changes** |
| **执行** / **批量执行** / **batch execute** | Execute | Confirm plan (or re-Prepare if stale); run Execute loop for all pending phases |
| **验收** / **sign off** / **accept** | Accept | Global QA + Batch Execution Report; await Owner review |
| **继续** | Resume | Continue from last paused phase (batch mode still active) |
| **停** / **pause** | Pause | Stop after current phase; report status |
| **单阶段 {phase-id}** | Single | Execute one phase only (exits batch auto-advance for that run) |

## Batch mode confirmation

Owner confirms batch mode when saying **「批量执行」** or **「执行」** after reviewing the plan.

In batch mode:
- Agent **auto-advances** between phases (phase-execution rule 10 exception)
- Pauses only on: verify failure after 2 retries, architecture decision, uncovered requirement, or explicit **停**

## Sign-off authority

| Action | Role |
|--------|------|
| Phase sign-off | Owner, in the conversation — recorded in the program doc |
| Post-completion follow-ups | Owner approves each proposed item before any of it is enqueued |
| Operate queue injection | Only after Owner approval |

## Example session

```
Owner: 方案 trade-iv-radar
Agent: [Batch Execution Plan — phases, verify cmds, risks]

Owner: 批量执行
Agent: [Phase 1 Task subagent → verify → program doc ✅ → ... → Global QA → Report]

Owner: 验收
Agent: [Batch Execution Report + proposed follow-ups]
```

## Language

- Owner ↔ Agent dialogue: **中文**
- UI labels, API fields, reports in Console: **English**
