# LANE-R1 — 发布链：CI 卡发布、镜像同步、发布窗口、IB 镜像构建（bifrost-trade-infra 为主）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-R1.md`。分支：infra `cursor/r1-infra`（Tekton / k8s 改动只推分支），涉及 research / plugin 的放各自 `cursor/r1-<简称>`。

| 顺序 | 项 | 要做的 | 注意 |
|---|---|---|---|
| 1 | **TD-162** | `release.sh window` 覆盖 research 与插件（同一个窗口文件，`what` 写仓库）；deliver-research / build 流水线与 platform-api 的 start_pipeline_run 在窗口被别人持有时拒绝 | platform-api 那部分放 platform 分支 `cursor/r1-platform`，与 LANE-S2 不冲突的文件 |
| 2 | **TD-155** | GitHub 推送后 Gitea 镜像要及时同步：push-mirror/webhook，或 release.sh 与 deliver 流水线先同步镜像再等该 SHA 的 CI | |
| 3 | **TD-95** | deliver-research 与 build-research-dagster 在 build 前对克隆的 SHA 跑 lint-test（ruff + pytest + code-health），或要求该 SHA 有 Succeeded 的 ci-* run；拒绝非 40 位 revision | |
| 4 | **TD-122** | IB Gateway 镜像改走 Tekton 构建到集群 registry（照抄 flex-query 的 pipeline-build.yaml），按 digest 钉，健康 hash 里带 git SHA | 和 LANE-T 的 TD-104 都碰健康 hash：本项只加 SHA 字段，时间戳归 LANE-T |
| 5 | **TD-121**（infra 部分） | Secret 轮换后重启所有挂载它的 research Deployment（照 infra holder_deployments() 推导列表），加 checksum 注解或 reloader | research 侧改动见 LANE-R2 |

Tekton 对象 apply 到集群是 Owner 步骤（会请示），本道只推分支。
