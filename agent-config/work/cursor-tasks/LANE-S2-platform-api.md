# LANE-S2 — platform-api 控制面修复（bifrost-platform `api/` + 少量 infra）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-S2.md`。分支：platform `cursor/s2-platform`、infra `cursor/s2-infra`（起点各自 origin/main）。
与 LANE-S1 同仓不同目录；如需改 `api/internal/remediation` 的客户端（S1 的 TD-207 也会改），以 S1 为准，S2 不碰。

| 顺序 | 项 | 要做的 | 注意 |
|---|---|---|---|
| 1 | **TD-222** | D10 扩容防护：Trade 各 namespace 的 daemon Deployment，任何 replicas 增加（requested > current）在 spine D10 ≠ UNLOCKED 时都拒绝；D10 状态读 ops-context（与 preflight 同源） | 防线：Go 测试覆盖 0→1、1→2、2→3 与缩容放行 |
| 2 | **TD-131** | `repair_cnpg_wal_store` 不再删失败的 Backup CR；另加一个只清 30 天前失败 Backup 的清理 | 新增的 Kubernetes 调用要在 infra `k8s/platform-rbac` 加规则（`scripts/gen_platform_rbac.py` 重生成 + `make check-platform-rbac`），放 infra 分支 |
| 3 | **TD-109** | PROD 读的 ops-context 改为构建或交付时从 platform 仓库 `config/ops-context.yaml` 生成，删掉 infra 里的旧副本；或加同步步骤 + CI parity 检查（二选一，报告写理由） | infra 的 k8s 改动只推分支 |
