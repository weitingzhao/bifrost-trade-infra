VERDICT: fix first

- **P1 — apply 通道被整条豁免。** [freeze_effects.json:5](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/release/freeze_effects.json:5) 与 [freeze_chain.py:111](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/release/freeze_chain.py:111) 直接跳过 `bifrost-apply-manifest`；其 `run` 在 `apply-manifest/pipeline.yaml:203` 执行集群写入，冻结检查不支配它。一次安装的启动顺序不能证明永久豁免整条写通道安全；应补保护，启动安装另行明确处理。
- **P1 — `onError: continue` 绕过棘轮。** [freeze_chain.py:116](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/release/freeze_chain.py:116) 只排除带 `when` 的冻结任务。给冻结任务加 `onError: continue`，下游 push 仍通过检查，冻结任务失败后却能继续写入。应拒绝这种冻结任务，并加入反例测试。
- **P1 — 兄弟仓库推送被漏检。** [check-release-chain.py:161](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/check-release-chain.py:161) 仅扫描本仓库冻结支配关系，虽然前面已找到 flex-query。实测指定 `FLEX_QUERY_ROOT` 后总检查退出 0；独立检查该流水线却报 `bifrost-build-flex-query: kaniko is not dominated by the freeze check`。应对已发现的兄弟流水线执行相同检查。
- **P2 — 全局只读名字可掩盖内联写任务。** [freeze_chain.py:36](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/release/freeze_chain.py:36) 按内联任务名字查全局白名单。新建名为 `lint-test`、脚本执行 `git push` 的根任务，实测零违规；`side_effect` 名单也未参与判定。应把内联只读声明绑定到具体流水线和受核对的任务规格。
- **P2 — 部分读取故障没有规定的拒绝首行。** [freeze_decision.py:189](~/agent-work/w56-slice-b/bifrost-trade-infra/scripts/release/freeze_decision.py:189) 在异常处理之外加载 CA；CA 缺失或损坏会直接抛异常。响应 UTF-8 解码错误也未捕获。任务仍失败、不会放行，但输出 traceback，违反故障拒绝格式；应统一转换为 `ReadError`。

核对结果：

- Task 使用 ServiceAccount token、CA 和 HTTPS GET，HTTP 超时 10 秒，步骤超时 20 秒；现有 RBAC 给 `default`、`tekton-deliver` 点名读取权限。挂载的程序和 schema 与测试源码逐字一致。
- 404、401/403、5xx、timeout 均退出 1，首行为 `拒绝：读不到冻结状态（404 / HTTP <code> / timeout），按冻结处理`。
- HTML、空正文、无 `data`：退出 1，首行 `拒绝：读不到冻结状态（unparsable response），按冻结处理`。
- 布尔 `frozen`：退出 1，原因 `field frozen is not a string`；大小写或空白变体：退出 1，原因 `frozen is not "true" or "false"`；未知键：退出 1，原因 `unknown field <key>`。
- 缺 `seq` 不放行；裸对象会先报 `missing field frozen_at`。完整解冻对象的非数字 `seq` 报 `field seq is not a decimal string`，均使用上述拒绝模板、退出 1。
- 合法冻结对象退出 1，首行 `拒绝：发布已冻结（<reason>，<frozen_at>）；解冻要 Owner 签名`；初始对象退出 0，首行 `未冻结：<checked_at>`。
- 十一条修改后的流水线均通过，未发现其中漏受保护的副作用任务；七份旧 fixture 全部失败。旧 platform PROD 链只有一个切点，覆盖两条镜像推送，滚动前没有第二次检查。
- 支配检查确实遍历所有根路径；未知身份默认有副作用，副作用 `finally` 被拒。带 `when` 或放在 `finally` 的冻结任务不提供保护，但没有副作用任务时也不会单独报这种非法位置。
- [RELEASE.md:151](~/agent-work/w56-slice-b/bifrost-trade-infra/docs/RELEASE.md:151) 写明先创建 `frozen="false", seq="0"`，再装 Task/程序 ConfigMap，最后替换十一条 Pipeline。缺序号会阻断新流水线；尚未替换的流水线和只读 CI 保持原行为。合并本身不等于已应用。
- 放行结果记录 `passed_cut_at`，可按 TaskRun 标签关联仍运行的 PipelineRun。在途枚举和冻结回执没有实现；`freeze_inflight.py` 的测试是行为表断言，不能当作真实 Tekton 调度演练。
- C 片扩展字段及 `seq` 已预留，完整解冻对象当前允许并打印未验签提示。序号递增、签名绑定和防重放尚未实现，属于明确延后范围。

只读离线测试：20 passed，跳过一个会写文件的测试。未写文件、未调用平台或集群、未读取凭证。
END OF REPORT