# gpu-server (RTX 4090) inference host: expected state

What the compute line has put on the 4090 host (`ubt-ai-4090`, node `gpu-server`), so a reinstall
can be brought back to it. Every change here went in by an Owner-approved host-tier node-run card;
the card numbers are the record. The contract other lines use is in
`agent-config/charters/6-compute.md` §2 (4090 inference row).

## Services

| Unit | State | Since | Why |
|---|---|---|---|
| `bifrost-strata-iq3.service` | enabled, running | #702 (Codex 01a1b638) | Strata inference, the only workload on the host |
| `bifrost-strata-lan.socket` / `.service` (files here) | enabled | #721, 2026-11-24 | 192.168.10.60:8082 → 127.0.0.1:8082, only .50 and .52 |
| `bifrost-harness-gateway.service`, `bifrost-harness-native.service` | disabled, stopped | #728, 2026-11-24 | the OpenCode/DeepSeek shells moved to the Mac minis; 4090 does inference only |

No systemd drop-in under `bifrost-strata-iq3.service.d/` (the Q4 A/B drop-in from #737 was removed by #738).

## Strata launch profile

`/home/vision/.local/state/strata/launch/iq3_s-32k.json` (the name is historical). Expected:

- model `qwen3.8-flash-next-iq3_s` (IQ3_S, about 84 GB on disk), port 8082
- `--max-context 131072` in both `args` and `args_written` (#738); `--kv int8`; `--expert-cache auto`
- backup of the original 32K file: `iq3_s-32k.json.before-64k-20261124`

The Q4 profile `ud-q4_k_xl-32k.json` (UD-Q4_K_XL, about 111 GB) has `--max-context 131072` and
`port` 8082 since #737 (backup `ud-q4_k_xl-32k.json.before-ctx-20261124`). It is not in use: when
#737 switched to it the engine loaded but nothing answered on 8082; the engine port is probably not
the `port` key (not verified). Read the engine's real port before switching again.

## Measured (2026-11-24, from the Mac minis, workshop; one-off readings)

| Context | tok/s | expert-cache hit | long prompt first token |
|---|---|---|---|
| 64K | 135 | 0.91 | 54K tokens: 11 s |
| 128K | 120–135 | 0.87–0.91 | 121K tokens: 25 s |
| 256K | 112 | 0.81–0.86 | 250K tokens: 59 s, mid-document recall correct |

Real harness sessions peaked at 30–45K tokens. About 15 KB of KV per token (0.5 GB of expert cache per +32K).

## Power

Wake: platform `wake_compute_node` (WOL job). Poweroff: platform `poweroff_compute_node` (tier D) or the
Console Command page; it checks the host is idle first. Nothing powers the 4090 off automatically when idle
(the old 01 service that tried, and always failed, was retired by #708).
