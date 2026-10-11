VERDICT: fix first

范围：仅审查 `caa4d30..1841f69`；全程只读，无平台或集群调用。

五项复核：

- 已关闭：apply 整体豁免已删除；`freeze-check` 为根，`run` 依赖它（`k8s/cicd/tekton/apply-manifest/pipeline.yaml:38`）。
- 已关闭：`onError: continue` 复现同时报非法检查和写任务缺少支配；`when`、重试、`finally` 也被拒绝（`scripts/release/freeze_chain.py:190`）。
- 已关闭：已定位的兄弟流水线现在接受同样检查；flex-query 缺口默认失败（`scripts/check-release-chain.py:180`）。
- 已关闭：同名只读内联任务运行 `git push` 的复现被拒绝；内联声明绑定流水线、任务和摘要（`scripts/release/freeze_chain.py:143`）。
- 已关闭：缺 CA 复现退出码 1，首行是 `拒绝：读不到冻结状态（missing CA），按冻结处理`，无 traceback（`scripts/release/freeze_decision.py:195`）。

新增问题：

- **P1 — 文档指定的解冻路径不能恢复 apply。** `docs/RELEASE.md:173` 指向 `release.sh unfreeze`，但现有 platform `api/internal/releasepolicy/write.go:115` 写入 `unfreeze.txt`、`unfreeze.sig`，且没有 `seq`；新检查器实际返回 `unknown field unfreeze.sig`。本次给 apply 加闸门后，它也不能修复该对象。必须明确兼容前置条件或提供 Owner 专用恢复路径。
- **P2 — 故障恢复及中断续装未写完整。** `docs/RELEASE.md:164` 只规定首次安装。冻结对象缺失、损坏，或检查 Task／程序 ConfigMap 损坏时，只能由 Owner 带外修复，但没有恢复步骤。安装在第 1／2 步或第 3 步中途停止，旧流水线及旧 apply 仍可能未受保护；不能声称任意中断点都已安全。应写明暂停入口、续装验收及保留当前冻结状态的要求。
- **P2 — 已知缺口可覆盖后来替换的同名任务。** `scripts/release/freeze_chain.py:354` 只比较 `message`，忽略条目的 `repo/pipeline/task/date` 字段。新增不同任务的缺口不会被放过，但把原 `kaniko` 换成执行 `git push` 的任务，报错仍相同，实测仍归入 known。需绑定被豁免任务的具体定义；日期目前只是文字（`scripts/release/freeze_known_gaps.json:5`）。
- **P3 — CI 描述不准确。** `docs/RELEASE.md:175` 说“CI 不用这个旗标”，但仓库未发现 CI、Makefile 或发布脚本调用该检查器；台账也标为 manual（`agent-config/RATCHETS.md:71`）。合并会使手工检查默认变红，不会新增自动 CI 红灯，应明确表述。

验证：29 项无需写盘的测试通过；另以内存模拟完成缺 CA、同名任务替换及现有解冻输出复现。未运行需要写盘的测试。

END OF REPORT