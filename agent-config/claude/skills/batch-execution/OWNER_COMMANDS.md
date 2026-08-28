# Owner Commands — Batch Execution

Standardized Owner phrases for the Agent Briefing → Cursor IDE → Delivery Board closed loop.

## Command table

| Owner says | Mode | Agent action |
|------------|------|--------------|
| **方案** / **plan** / **出方案** | Prepare | Read blueprint + API state; output Batch Execution Plan; **no code changes** |
| **执行** / **批量执行** / **batch execute** | Execute | Confirm plan (or re-Prepare if stale); run Execute loop for all pending phases |
| **验收** / **sign off** / **accept** | Accept | Global QA + Batch Execution Report; trigger `submit_post_completion`; await Owner review |
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
| Phase sign-off | Owner (admin) via Console Delivery Board or API |
| Post-completion approve | Owner (admin) — `approve_post_completion_item` |
| Operate queue injection | Only after Owner approves pending_review items |

## Briefing → IDE launch

Primary path: **Launch IDE Agent** on Briefing page (SDK via `POST /api/v1/programs/launch`).

Fallback: **Copy session pack** into new Cursor chat.

## Example session

```
Owner: 方案 trade-ib-migration
Agent: [Batch Execution Plan — 12 phases, verify cmds, risks]

Owner: 批量执行
Agent: [Phase TIBM0 subagent → verify → report_phase_progress → ... → Global QA → Report]

Owner: 验收
Agent: [Batch Execution Report + submit_post_completion]

Owner: [Console] Approve operate queue items
```

## Language

- Owner ↔ Agent dialogue: **中文**
- UI labels, API fields, reports in Console: **English**
