---
name: research-loop-automation
description: >-
  Research Loop Automation — one lens registry, Exhibit for every lens, harness with a
  real two-model judge and outcome-rule hypothesis resolution, Analyze 12 → 5 hubs,
  Copilot reading runs and composing one daily digest, unattended auto-accept on a
  leash. Use when executing program research-loop-automation phases (A1–D4) or when the
  Owner says Loop automation / lens registry / Analyze hubs / daily digest / persona models.
parity-id: research-loop-automation-v1
---

# Research Loop Automation (Waves A–D)

## Program

- **id:** `research-loop-automation`
- **Blueprint:** `bifrost-platform/config/programs/active/research-loop-automation.yaml`
- **Plan (phase detail, files, acceptance):** `bifrost-research/docs/plans/RESEARCH_LOOP_AUTOMATION_PLAN.md`
- **Repos:** `bifrost-research` · `bifrost-trade-frontend` · Console Trust level only in `bifrost-platform`
- **D10:** BLOCKED — research drafts and advisory verdicts only; `order_intent` and `policy_suggestion` never auto-accept
- **Out of scope:** P0 hygiene (research DDL apply, Dagster image alignment) — another session owns the Massive plugin upgrade; options trades tape (subscription)

## Owner decisions (locked 2026-09-06)

1. **D-RLA-1** Analyze nav 12 → 5: Vol regime · Dealer levels · Scenario model · Flow · Option Discovery; Contract Greeks under Data; old routes redirect
2. **D-RLA-2** Unattended leash: research drafts auto-accept under gates; hypotheses auto-resolve by outcome rule when unambiguous; one daily digest replaces per-candidate cards
3. **D-RLA-3** LLM budget on the Cron; **DeepSeek and OpenAI judge in parallel**, per-provider daily caps, auto-accept needs agreement
4. **D-RLA-4** Flow stays a placeholder that states the subscription reason (trades / quotes 403 on the current Massive plan); OI proxy behind a labelled section

Defaults: bands hot ≥ 80 · cold ≤ 20 · lean 60–80 / 20–40 · models `deepseek-chat,gpt-4o-mini` · caps 2.0 USD per provider · plan `deepseek-chat` json 60 s → `gpt-4o-mini` → heuristic · resolution horizon 20 sessions, ±3% excess vs SPY.

## Phases

| ID | Title | Repo | depends_on | Sign-off |
|----|-------|------|------------|----------|
| A1 | Lens registry (`lenses/registry.py`, `GET /research/lenses`, MCP `research.lenses.list`) | research | — | api |
| A2 | Exhibit for every lens (verdict · track_record · similar) | research | A1 | api |
| A3 | Signal Decay lens expansion + similar-regime hygiene | research | A1 | api |
| A4 | Analysis defects (brief sign · opportunity scope · gamma zone · VRP 30d · tape caveat) | research | — | api |
| A5 | Pages read the registry (verdict strip track record, Signal Decay 60d) | frontend | A1–A4 | **Owner** |
| B1 | LLM plan repair (chat model · json · provider chain) | research | — | api |
| B2 | Two-model Persona judgement + caps (+ FE chips) | research + frontend | — | **Owner** |
| B3 | Hypothesis auto-resolution (`resolution_json`, EOD applies rule) | research + frontend | — | **Owner** |
| B4 | Every objective runs; evidence per symbol | research | B1 | api |
| C1 | Analyze hubs 12 → 5 + redirects | frontend | A5 | **Owner** |
| C2 | Per-lens analytical depth | research + frontend | A5, C1 | api |
| C3 | Daily Brief on exhibits | research + frontend | A2, C1 | api |
| D1 | Copilot reads a run (`research.loop.get_run` …) | research + frontend | B2 | api |
| D2 | One daily digest | research + frontend | A2, B3 | api |
| D3 | Unattended on a leash (Trust L0 + gates + weekly rule proposal) | research (+ Console) | B2, B3, D2 | **Owner** |
| D4 | Copilot verdicts back on the pages | frontend + research | D2, C1 | api |

Parallel: A1 → (A2 ∥ A3 ∥ A4) → A5 · B1 ∥ B2 ∥ B3 → B4 · C after A5 · D after B.

## Verify

```bash
cd bifrost-research && make lint && make test && make test-mcp && make check-code-health
cd bifrost-trade-frontend && npm run lint && npm run test:run && npm run build && npm run check:legacy-css && npm run check:code-health
bash scripts/check-agent-config-parity.sh
```

Acceptance on DEV: Vite `:5173` against `192.168.10.73:30882` (D-IL1). Cron facts: `kubectl logs -n research job/research-harness-<id>` (KUBECONFIG `~/.kube/bifrost-k3s.yaml`).

## Release pins (each phase bumps what it touches — image → registry tag → manifest)

| Change | Pin |
|--------|-----|
| API / engines | `k8s/api/deployment.yaml` |
| MCP tools | `k8s/mcp/deployment.yaml` (**research-mcp**, not api) |
| Harness Cron (plan, persona, entry) | `k8s/engines/cronjob-harness.yaml` |
| Dagster aux assets (EOD, digest, outcomes, weekly policy) | `k8s/orchestration/dagster.yaml` (`-dagster` tag) |

Procedure: `.claude/skills/research-release/SKILL.md` (Cursor: `.cursor/skills/research-release/SKILL.md`).

## Key files

- Lenses: `bifrost-research/src/bifrost_research/lenses/registry.py` · consumers `engines/signal_hit/build.py` · `engines/scan/build.py` · `engines/alert_scan/entry.py` · `api/similar_regime.py` · `api/exhibit.py`
- Harness: `copilot/harness/{plan_llm,planning,persona_eval,batch_orchestrate,entry,policy_schema,suggestion}.py` · `copilot/agents/{eod_review,daily_digest}.py` · `copilot/rate_limit.py`
- Copilot: `copilot/agents/graph.py` (specialist tool filters) · `mcp/tools/{exhibit,lenses,write_loop}.py` · instructions under `copilot/agents/instructions/`
- Frontend: `src/lib/lensVerdict.ts` · `src/hooks/useLensRegistry.ts` · `components/research/{AnalyzeVerdictStrip,SimilarRegimeCard,CompositeRegimeRibbon}.tsx` · `pages/research/analyze/{hub,volRegime,dealerLevels,scenario,flow}/` · `components/research/harness/*` · `lib/router.tsx` · `layout/navConfig.ts`

## Discipline

- Follow `phase-execution` (self-check per unit; Phase report; no auto next Phase unless batch mode)
- Code-health ratchets: no file over 800 lines (zero headroom), duplicate module-scope names ≤ 3, flat pages ≤ 33
- Frontend: Dense UI primitives, `check:legacy-css`, module placement pages → shared only
- Schema changes in this program are the two approved by the decisions above: `research.ai_action_log (provider, cost_usd)` and `research.hypothesis.resolution_json`; anything else is architecture-level → ask
