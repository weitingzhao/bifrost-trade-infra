# Trade socket Deployments — RETIRED (Wave 14G-F)

IB socket edges retired to Platform IB Gateway (`data/redis-ib`).
Polygon Options WS retired to Market Data Plugin (`polygon-ws-ingestor` → `redis-massive`).

- Compose: only `--profile legacy-ib` (dev/prod)
- CI: no `bifrost-socket` image build
- Cluster: no IB socket STS/Deployments; RBAC/NetworkPolicy leftovers purged from Trade NS
- Repo: `bifrost-trade-socket/ARCHIVED.md`

Archived Trade `massive-ws` manifest: `k8s/legacy/massive-ws-manifest.yaml`.
Remaining files here (`ib-socket-rbac.yaml`) are **not** included in kustomize — do not re-apply.
