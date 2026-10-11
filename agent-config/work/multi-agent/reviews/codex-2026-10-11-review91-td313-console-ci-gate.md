# Codex 复核 91 — TD-313：Console 的 lint、测试、构建进 CI 门禁（分支 `w31/td-313`，到 `31366b3`）

2026-10-11 17:26 CDT · 只读

统筹方处理：没有必须改的，3 处应该改的和 1 处次要的，按规则自动加一轮（第 3 轮）。防改弱的检查能被绕过（关掉严格模式、提前退出、恒假的 `when`、`onError: continue`）→ 改成整段脚本与测试里的规范文本相等、任务和步骤的键按清单；`npm ci` 失败后悄悄 `npm install` → 去掉回退（统筹方在 CI 的镜像里量过，`npm ci` 今天是成功的）；应用后的核对要比完整的 `.spec` → 归统筹方，用逐字段比较的只读脚本。复核独立确认：四条命令的顺序、退出码、摘要、超时。

---

VERDICT: fix first

P2 — `scripts/release/test_console_gate.py:181`：棘轮未检查任务/步骤的执行条件与错误策略。最小复现：给步骤加 `onError: continue`，或给任务加恒假的 `when`；内存验证均被接受，检查失败或完全跳过仍可能得到绿灯。最小修复：要求唯一的 `test-console`、无 `when`、任务和步骤均无 continue、`runAfter` 保持 `[clone, clone-ui]`，并添加对应反例。

P2 — `scripts/release/test_console_gate.py:66`：只记录首次检查前曾启用严格模式，无法保证命令实际执行。最小复现：在 `set -euo pipefail` 后加 `set +e`；棘轮返回空列表，shell 替身让两条 npx 检查返回 7，整个实际脚本仍退出 0；插入 `exit 0` 或恒假条件同样通过。最小修复：固定允许的脚本结构，拒绝提前退出、严格模式关闭和包裹检查的条件控制，并补反例。

P2 — `k8s/cicd/tekton/pipeline-ci-platform.yaml:158`（既有问题）：`npm ci` 的失败被 `npm install` 接管。最小复现：修改依赖声明但不更新锁文件；ci 拒绝后，install 可以修复锁文件，后续检查验证的是临时解析出的依赖。最小修复：改成直接 `npm ci`，保留 stderr，让安装失败阻断步骤。

P3 — `../REPORT.md:164`：应用后只检查 timeout、首步名称和脚本，不能证明没有 `when`、continue、额外步骤或资源变化。最小复现：添加 `onError: continue`，该命令的输出不变。最小修复：读取完整 `.spec` 与本地 YAML 比较，并核对红/绿 PipelineRun 捕获的 `pipelineSpec`。

独立验证：新增 9 个测试通过；freeze 检查无违规；摘要重算为 `d366f911e97cb3c6294e575e0a2fb64cc8ac8f71c6bff0895a94e4e1e9f1f853`，匹配登记。
删除/改名任务、增加第二步、直接移到外部脚本已会使棘轮失败；这些无需新增保护。
当前四条命令顺序正确，退出码未被吞；ESLint 只阻断 errors、允许 warnings，符合任务书。Vitest 从 Console 目录加载 jsdom 配置，`run` 为非 watch，worker 已固定为 2。
8 分钟包含 TaskRun 的调度及拉镜像等待；材料中最慢完整步骤 157 秒，三倍 471 秒仍取整为 8 分钟，原注释应改用这一组数字。忙节点、冷镜像与容器峰值内存尚未独立验证；4Gi 暂无不足证据。
`QuestionSendLifecycle.test.tsx`、`useMissionSnapshot.test.tsx` 使用真实计时的 `waitFor`，繁忙节点仍有超时风险；网络已 mock。`queueEta.test.ts` 依赖英文日期标签，存在 locale 可移植性风险，未发现当前 pod 必然误红。
构建仅生成工作区产物；npm 另写容器缓存并访问 registry，没有发布或集群写入，登记为 `read_only_inline` 合理。
PWA 期望值从 3 改为 4 是有效红灯证明；还须确认失败发生在 Vitest、build 未执行，恢复后的下一笔完整流水线成功。
差异仅三个文件，分别 232、139、281 行，无超过 800 行的变更文件；未发现 P1。未访问集群、HTTP API 或凭据，未改文件。

Owner：修复后先合入 infra main，再从合并提交执行 `kubectl apply -f k8s/cicd/tekton/pipeline-ci-platform.yaml`，核对完整规格并做红/绿证明；仅在字段管理者仍为客户端 apply 时沿用此命令，TD-309 后续迁移必须使用包含本次修改的最新清单。
END OF REPORT
