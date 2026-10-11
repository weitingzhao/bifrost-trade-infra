# Codex 复核 96 — TD-313 最终版（分支 `w31/td-313`，到 `e01b02a`）

2026-10-11 17:47 CDT · 只读

统筹方处理：没有必须改的；1 处应该改的和 2 处次要的，比上一次少，按规则自动加一轮（第 4 轮，只改测试，`1e33ce7`）。键的清单不管值（超时改成 1 秒、换镜像、内存上限 64Mi 都不被发现）→ 整个 `test-console` 任务和它依赖的 `clone`、`clone-ui` 两个任务在测试里写成字面量，逐值相等；统筹方用五种改动逐个试过，测试都会失败。门禁的证明不在 platform 主线上做 → 改在临时分支上做红、绿两笔，按提交号手动起 CI。复核认可：CPU 的请求等于上限是对的修法；8 分钟超时目前够；摘要匹配。第 4 轮只动测试，统筹方核对后合并（infra `aeb96c7`），没有再送复核。集群在 Owner 应用这份文件之前仍跑旧定义。

---

VERDICT: fix first

Review 91 的四项：
- P2 执行条件/错误策略：已关闭。`scripts/release/test_console_gate.py:258` 要求唯一任务、单一步骤、键白名单和固定 `runAfter`，拒绝 `when`、`onError`。
- P2 提前退出/关闭严格模式：已关闭。`scripts/release/test_console_gate.py:284` 比较完整脚本，已有提前退出和恒假条件反例。
- P2 安装回退：已关闭。`k8s/cicd/tekton/pipeline-ci-platform.yaml:151`、`:157` 都直接执行 `npm ci --no-audit --no-fund`，保留 stderr。
- P3 应用后核对不足：部分关闭。`../REPORT.md:171` 已要求比较完整 live `.spec`；尚无应用后的证据，仍须核对红/绿 PipelineRun 捕获的规格。

新发现：
- P2 — `scripts/release/test_console_gate.py:88`、`:282`：白名单只限制键名，未锁定影响执行的值。最小复现：内存中把 `timeout` 改为 `1s`，14 个门禁测试仍全绿，freeze 摘要也不变，但正常任务必然超时。替换镜像、设置工作区 `subPath`、把内存限额改为 `64Mi` 或请求改为 `1Ti`，门禁测试也全绿；后三类 taskSpec 修改会被现有摘要检测。最小修复：断言 timeout、image、两层 workspace 映射及资源规格，并补反例；有意调整时同步修改断言供审阅。
- P3 — `scripts/release/test_console_gate.py:250`：未验证克隆依赖和目标。最小复现：删除 `clone-ui`，或把 `clone` 的 revision 改成固定 `main`，14 个测试仍全绿；前者使 DAG 无效，后者可能验证错误提交。最小修复：检查依赖任务存在，并锁定克隆 URL、revision 参数和输出目录。
- P3 — `../REPORT.md:177`：红灯证明计划直接污染 platform main。最小复现：红提交尚未恢复时启动按 main 克隆的交付。最小修复：在 Gitea 可读取的临时分支上制作红/绿提交，手动按各自 SHA 运行 CI；`trigger-trade-ci.yaml:275` 只自动接收 main，流水线 `pipeline-ci-platform.yaml:22` 和克隆任务支持分支/SHA。

CPU request=limit=2 是合理修复：提高忙节点上的 CPU 份额，但不等于独占 CPU 或墙钟保证。2 CPU 仍可能因容量不足而 Pending，且 `local-path` PVC 会限制落点；所述节点余量尚无阻断证据，我未查询集群。
内存无需机械改成 request=limit：所述峰值约 0.9GiB，当前 1Gi request、4Gi limit 暂无不足证据；仍属 Burstable，保留压力下的驱逐风险。
8 分钟相对所述最慢 179 秒约为 2.68 倍，剩余约 301 秒供调度、拉镜像和波动，当前可接受；材料中的容器测量未由本轮独立重跑。

`finally` 和参数默认值变化未被此测试覆盖，可留给完整流水线审阅；Pipeline 顶层 `when` 不是这里的合法执行条件。两份 YAML 文档会被 `safe_load` 拒绝。
同步修改 CANONICAL 与 YAML 是预期更新路径；审阅必须同时看脚本、断言和摘要，重复一层可同步修改的快照不能替代审阅。
独立检查：14 个门禁测试、21 个 freeze 测试通过；摘要为 `58a8f0063b86ea62dc6ffab5920207e7cedcd6f40d78b3797cf0aef5f71af39b`，匹配登记。
差异仅指定三文件，分别 231、139、494 行，无超过 800 行的变更文件；未发现 P1。全程只读，无 HTTP、平台/集群调用或凭据读取。

应用后证明：Owner 从合并后的 main 沿用客户端 apply；比较完整 live `.spec`，再按临时分支红/绿 SHA 运行同一流水线，核对捕获规格、克隆 SHA、红灯止于 Vitest 且 build 未开始、绿灯完整成功；若仍用 main，红绿之间不得发布、提升环境或启动按 main 构建的交付。
END OF REPORT
