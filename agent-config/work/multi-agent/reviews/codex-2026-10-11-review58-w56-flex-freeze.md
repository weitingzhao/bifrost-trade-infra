# Codex 复核 58 — W-56 B 片收尾：flex-query 构建流水线接上冻结检查（flex-query `915b8f1`，infra `b965639`）

2026-10-11 08:22 CDT · 只读 · 分支 `w31/w56-flex-freeze`（两个仓库）

统筹方的处置：可以合并，已合并（flex-query 主线 `bf6c61c`；infra 见本提交）。复核提的应用前条件我只读核对了：集群里最近一次 flex-query 构建跑在 `cicd/default` 下，在授权名单里；没有 Argo 应用同步插件仓库；集群里还没有那个 Task。已写进 `docs/RELEASE.md`。没有应用到集群。

---

VERDICT: safe to merge

未发现这两个提交引入的 P1/P2。

- 流水线：`freeze-check → release-window → clone-plugin / clone-core → kaniko`，所有副作用任务均被检查支配；没有 `finally`、`when`、重试或失败后继续的绕行。
- Task 引用与 infra 接法一致：同在 `cicd`，名称为 `bifrost-release-freeze-check`；Task 无必填参数或 workspace，接线完整。
- 检查器：flex-query 已使用相同规则。旧图夹具仍报告 `kaniko is not dominated`，默认和 `--allow-known-gaps` 都退出 1；相关回归测试通过。
- 缺少兄弟仓库时明确退出 1，不跳过。对要求完整检查的 manual 棘轮，这是正确行为；可用 `FLEX_QUERY_ROOT` 指定检出位置。
- 文档：正确区分仓库修复与实际应用，要求先装 Task／程序 ConfigMap，再装 Pipeline；反序会留下无法解析的引用，构建失败。已启动的 PipelineRun 不会中途插入检查。
- **应用前条件**：[RBAC](k8s/cicd/tekton/rbac-release-window.yaml:23) 授权 `cicd/default`、`cicd/tekton-deliver` 读取冻结 ConfigMap。仅凭这两个仓库无法确定 flex-query 实际运行身份；应用前需核对 PipelineRun 的身份及 Task 级覆盖、实际 `get` 权限和令牌挂载。若使用其他未获授权身份，检查会按冻结处理并拒绝构建。
- 验证：正常检查退出 0，YAML 解析通过，专项测试 22 项通过；完整筛选测试 36 项通过，3 项因只读沙箱禁止临时文件写入而失败，未复现“39 全通过”。
- 未修改文件，未访问集群、平台或凭据。

END OF REPORT