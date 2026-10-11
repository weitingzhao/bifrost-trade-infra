VERDICT: fix first

审查范围：`origin/main...HEAD` 的三个提交。全程只读，未访问集群、平台、registry 或凭据文件。现有 16 个闸门／CI 测试通过；离线反例仍能误放行。

以下路径均相对于当前仓库。

- **P1 — 请求参数可执行 shell。** `task-release-gate-platform.yaml:89–90` 将 `revision/uiRevision` 直接替换进脚本文本；双引号不能阻止替换后的 `$()`、反引号或引号闭合。其他参数也有同类问题（`:61、120、143`）。应通过环境变量传参，再校验。
- **P1 — 请求者能选择闸门实现和取消观察时间。** `task-release-gate-platform.yaml:118–143` 执行请求者指定的 `infraRevision` 中的 Python；`giteaBase` 也可改，且会携带 Git 凭据。`release_gate.py:246–255` 接受零观察时间，已复现刚完成即通过。执行代码、仓库地址和最低观察时间应由受信任策略固定。
- **P1 — 晋升摘要没有绑定到通过闸门的提交。** `pipeline-promote-platform-prod.yaml:47–53、75–148` 只把两个 SHA 用于输出结果，后续重新读取当前 STG Pod。期间 STG 若换版，会晋升未经本次 CI／观察时间核验的镜像；API、Console 分别读取还可能取得不同发布的组合。应在闸门中核验并输出与两个 SHA 绑定的不可变摘要。
- **P1 — 旧成功 CI 掩盖后续失败或运行中的重跑。** `release_gate.py:108–115` 只要历史上存在成功就放行。已复现同一 SHA 最新 CI 失败仍返回 `pass`。应选择最新的匹配 CI，再判断终态。
- **P1 — 上一版不是可靠的成套快照。** `pipeline-promote-platform-prod.yaml:210–213` 先完成 API 改标签，再处理 Console；中断会留下半套新 `prod`。更严重的是 `registry_retag.py:69–73` 在某个镜像摘要未变化时跳过保存，使其 `prod-prev` 留在更早版本，而另一镜像保存当前版本。应先保存两份当前摘要及发布身份，再迁移，并提供中断恢复。
- **P1 — 部署仍依赖可变 `:prod`，缺少流水线内互斥。** 上述改标签步骤与 `task-deliver-platform.yaml:22–24` 的逐个重启之间，另一晋升／回滚可改动标签，破坏本次部署和回滚快照。应将 Deployment 固定到本次摘要，并对成套发布操作实施可靠互斥。

- **P2 — ServiceAccount 放错对象。** 两条新文件都是 `kind: Pipeline`，却设置 `spec.taskRunTemplate`（晋升 `:20–21`，回滚 `:17–18`）；这是标准 Tekton `PipelineRun` 字段，不能据此保证任务使用 `tekton-deliver`。应在实际创建的 PipelineRun 设置身份，并离线校验 schema。
- **P2 — “最新 STG”排序可掩盖更新尝试。** `release_gate.py:217–221` 优先使用开始时间，按字符串比较，缺时间戳则用空串。已复现较早创建但较晚开始的成功覆盖更新的运行中尝试，以及较新记录缺时间戳仍放行。应明确按创建时间排序，解析时间并拒绝不完整记录。
- **P2 — Pipeline 标签可冒充实际执行身份。** `ci_gate.py:46–52` 优先相信标签，未核对 `pipelineRef`；已复现实际引用其他 Pipeline、标签写成平台 CI 的记录被接受。应拒绝身份矛盾，核验真实 Pipeline 引用及仓库来源。
- **P2 — 核对不覆盖“每个 PROD Pod”和副本完整性。** `registry_retag.py:90–108` 跳过终止中的 Pod，也不核对期望副本数、Deployment generation 或 Pod Ready 条件。已复现只有一个 Console Pod也返回摘要。不同摘要或未就绪的非终止 Pod会拒绝，但尚不能证明两个 Console 副本及全部运行实例一致。
- **P2 — CI 未完成时没有等待。** `task-release-gate-platform.yaml:137–143` 仅调用一次，退出码 2 直接失败；与计划中的“等到超时再拒绝”不符。应有限轮询，并给 Git、健康检查和 API 查询设置明确超时。

已核对的其他行为：

- Registry 单 manifest／index 的复制保留原字节和媒体类型；每个仓库先保存旧标签再移动新标签（`registry_retag.py:71–73、132–159`）。
- 回滚先检查两个 `prod-prev` 存在，缺任一份则在修改前失败（`pipeline-rollback-platform-prod.yaml:95–100`）。若已等于 `prod`，改标签为空操作；第二次回滚不会撤销第一次，仍会执行重启流程。
- 完整 SHA 比较拒绝前缀、空串；大小写归一化。CI 的 `revision=main` 即使实际克隆了目标 SHA，也不被识别；完整 SHA 的分支 CI 则未要求 main 来源。
- API 查询失败、无有效 Git 解析结果和常见坏 JSON不会直接放行；部分记录被忽略的问题见上。
- 新 RBAC 仅授予所列命名空间内 PipelineRun／TaskRun／Deployment／Pod 的 `get/list/watch`，只绑定 `cicd/tekton-deliver`，无新增写权限。
- 现有 Task／Pipeline 清单未修改；共享 `ci_gate.py:21–25` 扩大了接受的 CI Pipeline 集合，是计划明确要求的现有行为变更。

应用前必须逐项验证的集群假设：

- Tekton CRD schema、实际 PipelineRun 的 ServiceAccount、结果传递及超时；账号存在，具备查询、PROD rollout 和 Argo patch 所需权限。
- Pod 能访问 Gitea、STG 两个健康端点、Kubernetes API、Alpine 软件源，以及无需凭据的 Registry GET／PUT。
- 集群内 Registry 与 `.73:30500` 指向同一存储；支持四种媒体类型，带标签的 manifest／index 及其引用不会被 GC。
- 三个 Deployment 的标签选择器、容器名和期望副本数准确；workers 确实与 API 使用相同摘要；节点报告的 `imageID` 是可查询的 manifest 摘要，而非配置摘要或另一层 index 摘要。
- PROD 三处镜像引用及 `Always` 拉取策略实际生效；节点架构、Registry 拉取配置与镜像兼容。
- PipelineRun／TaskRun 保留时间和完整性足够；API 时间与任务节点时钟同步；STG 发布记录确实对应运行产物。
- 发布窗口覆盖新旧晋升、回滚及直接改标签入口；Argo 自动同步不会在核对后改动运行版本，最终同步后的状态也能得到验证。