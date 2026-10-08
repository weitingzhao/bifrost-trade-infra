# Agent modes and forbidden actions

Authority for agent modes and forbidden actions. Moved out of
`bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts`
(LANE-W32). The lists below are the `AGENT_MODES` and `FORBIDDEN_ACTIONS`
values from that file.

## AGENT_MODES

| mode | flywheel | defaultUI | agentMay | agentMustNot |
|------|----------|-----------|----------|--------------|
| Product | A — Trade FE | bifrost-trade-frontend :5173 → bifrost-dev :30882 (D-IL1; not Prod browser) | Migrate pages, Dense UI, hooks, Legacy equivalence; follow trade-dev-inner-loop smoke pack | Change compose, prod cutover, K3s, API contracts; treat Prod refresh as UI accept; enable live trading or scale daemon for auto-trade (D10 BLOCKED until Owner unlock) |
| Ops | B — Runtime | Bifrost Ops Console :5180 → Control Room | Read spine, matrix, topology; infra YAML; K3s planning; network L0 zone-matrix + firewall audit (scripts/unifi_firewall_setup.py); L1 idempotent firewall apply per D9 Session v2 | Change trade page UI, expand FE scope; toggle Default Security Posture or disable IDS/IPS; scale daemon for live trading or remove STG daemon-scale-zero (D10) |
| Promote | A + B coupling | Rocket → Launch Rocket · Mission Control → Audit | Query release-state, deploy via start_pipeline_run, run gates, verify smoke; follow next_action guidance | Skip blockers (D1, gate), deploy PROD with different revision than STG, bypass admin role for gates; Promote rollout that enables live trading (D10 BLOCKED) |
| Research | C — OLAP | bifrost-research (dbt + engines + Research API :8795) · Ops Console Research governance (Wave 5) | Edit bifrost-research; run dbt on bifrost_golden_source analytics/research/features schemas; add Python engines; Research API read paths; K8s manifests under research NS | Write Trade DB (bifrost_dev/stg/prod); mutate raw_market.* ingest tables (Plugin owns); change Ops spine/compose for Trade cutover; enable live trading or daemon scale (D10) |

## FORBIDDEN_ACTIONS

| action | scope |
|--------|-------|
| Redis daemon control write via platform AI (POST /api/monitor/control/*) | All modes |
| ib:operator:cmd write by an agent (platform-api reconnect_all is D-IB-Heal L1) | All modes |
| Live trading enablement — scale daemon for auto-trade, remove STG daemon-scale-zero, enable live hedge/place_order, or Monitor /control/* that arms live trading (spine D10 BLOCKED until Owner explicit unlock) | All modes |
| Editing bifrost-trader-engine/ (read-only reference) | All modes |
| Default Security Posture toggle (Allow All ↔ Block All) or disable IDS/IPS on UCG | All modes |
| Bulk delete all Bifrost firewall zones / policies | All modes |
| Manual UniFi UI firewall / zone / SSID changes (use platform-api + scripts executors) | All modes |
| UniFi Integration API Key write path on UCG 10.4.57 (site UUID blocked — use Session v2 per spine D9) | Ops mode |
| Forced Agent Desk tab switch on Agent Fix start/running — use shell Operator Dock Agent slot (ambientJob + Expand dock; Recent rail adopts jobs in-dock); Agent Desk is archive only (explicit Open in Agent Desk / Archive) | Ops Console shell |
| Operator Dock embedded Agent host Update / Confirm / deploy log / smoke — Dock is L-1 pulse + deep-link only; Update SSOT = Launch Desk → Agent (AgentHostDeployPanel); Operator Plane = heartbeats / MCP / AI Fix | Ops Console shell · Operator Dock |
| In-page Commit & push / Skip / Cancel on Launch Live — approvals are Dock SSOT; Launch Live is telemetry (Agent one-line + Pipeline + Post-deploy) with Expand dock | Mission Launch · Launch Live |
| kubectl set image bypass for ib-gateway publish — use Launch Plugin lane + make install-ib-gateway only; IB Gateway manage reconnect is observe/repair not publish | Mission Launch · Launch Plugin |
| Direct kubectl / pg_dump against CNPG from Agent — use Platform API get_data_freshness / trigger_data_clone / get_data_clone_status instead | Ops mode |
| Clone or restore into bifrost_prod (source-only; targets limited to bifrost_dev / bifrost_stg) | All modes |
