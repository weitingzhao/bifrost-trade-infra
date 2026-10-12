VERDICT: fix first
A SEQUENCE FOR (a)–(e): not found
RULES THAT ONLY LACK A TEST: 1

（复核 134，Claude 的子代理，只看 platform `10448b9`；由统筹方按交回的全文存盘。证据在 `~/agent-work/claude-review-134/`。）

一问的答案：(a)(b)(c)(d) 没找到。(e) 只有三条 CI 流水线自己的规则变了，都是任务书要的：修订号必须是整 SHA；发布窗口方面，今天只要有人开着窗口，CI 这类不在仓库表里的流水线会被拒（`release_window.go:162-166`），现在不再受窗口影响（`:212`）。其余 16 条流水线的窗口和整 SHA 规则没变。

**P1（合并后平台 CI 会变红）** `run_contract_test.go:79-121`、`run_refusal_test.go:260-315`：两条「非 CI 不变」测试用邻居目录 infra 检出里的 Pipeline 定义去构造 run，再和固定的 golden 比。golden 是按 infra `ab9a593` 生成的，那时 `pipeline-deliver-platform-prod.yaml` 还没有 check-source。护栏 ② 的 infra 分支合进 infra 主线之后，每一次 `bifrost-ci-platform`（它克隆 infra 的 main）都在 `go test ./...` 失败：`platformTaskRunSpecs` 看到 check-source 就多加一条身份，和 golden 不等。实测：换上 `w31/guard-2` 的那个文件，`TestNonCIRunsUnchangedFromMain` 和 `TestNonCICreatedRunsUnchangedFromMain/bifrost-deliver-platform-prod/{empty,tagged}` 失败。以后 infra 改这 13 条流水线声明的参数或注解也一样。最小修法：这两条测试不读 infra 检出，把用到的 Pipeline 声明冻结成 testdata 夹具；防线和等价测试照旧读 infra。
**P2-test** 规则 8 对 deliver / build 流水线没有测试：把 `service.go:320` 改成「带 revision 的流水线跳过检查」，整个包照样全过。`run_refusal_test.go:211` 的名单只有 unknown、bifrost-ci-platform、bifrost-smoke。修法：名单里加一条 deliver（带窗口和节点夹具）。
**P3**：等价测试只比 params、workspaces、taskRunTemplate 和 repo 标签（`run_contract_test.go:213-246`），给触发器模板加 `timeouts` 测试照过——改成比整个 spec。邻居目录没有 infra 检出又没有 CI 环境变量时，11 个新测试里 9 个静默跳过。CI 调用里顶层 `tag` 被静默忽略；顶层 revision 和 params.revision 同时给且不同时，run 测的是 params 那个，启动回调记的是顶层那个（`handler.go:104-110`）——两者不同就拒绝。`ref_preflight.go:86-88`：python 的预检响应里 `repos`、`missing` 是 null。规则 8 只管两类，Tekton 启动时还会拒的另外几类不在内，现在都不会发生。

六点：1. golden 确实出自 main：在 main `2726c47` 的副本上跑 golden 的 28 个调用，逐字节相同；另把 16 条非 CI 流水线的 12,960 个调用在 main 和分支上各跑一遍，12,904 条相同，50 条是规则 8 的新拒绝，6 条是原有的不确定报错。2. 规则 1–8 全部 met。3. 三条种错都被杀死；CI 里「检出缺失就失败」只靠源文件路径以 `/workspace/` 开头成立（读出来的，本机模拟不了）；`test-api` 不等 `clone-infra`，晚到是误红不是误绿。4. 有构造分支的 13 条没有新拒绝；新被拒的三条今天建出来也会被 Tekton 拒（`bifrost-clone-frontend-smoke`、`bifrost-build-research-pine`、经这个动作起的 `bifrost-apply-manifest`）。5. 没有办法让成功的 CI run 的 revision 是 X 而测的是别的。事实：CI 测的是「X 加运行当时的 ui main 和 infra main」；同一提交可以重跑任意多次，一次成功就算数；「X 有 CI」不再意味着 X 上过 main（镜像里任何分支的提交都能跑）。6. 合并前：两条 golden 测试改用冻结夹具；规则 8 加一条 deliver 的拒绝测试。

测试运行：go test 10 次，一次一个。

---

## 确认轮（同一位复核方，2026-10-12，对象 `git diff 10448b9 6d53730`）

VERDICT: safe to merge。P1 closed：冻结的声明和 infra `ab9a593` 的 12 条流水线逐条相同（只少 4 个参数的 description，构造逻辑不读它）；infra 检出在 `667b758` 时整包 65 个通过、0 跳过，检出不在时 58 个通过、7 个跳过。P2-test closed：重种的错被 `TestDeliverPipelineDeclarationRefusals` 杀死。整个 spec 的等价、自相矛盾的 revision 和 CI 的 tag 被拒、预检响应都已做；16 条非 CI 流水线的 12,960 个调用和上一轮结果逐条相同。没做完的一处（P3）：四条 CI 的拒绝测试仍从 infra 检出取 Pipeline 对象，检出不在时静默跳过。上正式环境之前要知道的：CI 启动是 B 级、不经审批、不看窗口，镜像里任何分支的提交都能跑；防线和等价测试有意跟着 infra 主线走——infra 改触发器或这些流水线的声明时要先合 infra、再合平台，否则平台 CI 会红到平台跟上为止。

统筹方的处理：合并前在合并后的树上跑整个 API 的测试，`internal/server` 里三条审批测试失败（假流水线没有 spec，被「声明读不出就拒绝」拦住）——实现者、统筹方第一次验收、复核都只跑了 delivery 一个包。补了夹具（只改测试），整套通过后合并：platform `26a10b5`。

END OF REPORT
