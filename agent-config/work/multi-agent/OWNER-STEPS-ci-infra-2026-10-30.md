# W-31 S6 ci-infra：安装与验证操作单

当前仅交付代码与离线测试；没有访问集群、构建镜像或推送。以下由 Owner / 统筹在集成完成后执行，一次一个动作，前一步成功才继续。所有审批在 PROD 平台 `ops.bifrost.lan` 建立。不要在本机直接用 kubectl 写集群。

## 0. 先补齐依赖（统筹，本机集成 checkout）

必须先由相应 lane 合入并复核：

- platform `api/internal/agentrt/infracheck` 与 `api/cmd/infracheck`；store/agentd 调用同一生成器；标准库构建、金样、清单存在性与 `__init__.py` 拒绝测试。
- platform 唯一 quick 清单收录 `scripts/landing`（包含 pins 与 budget 测试），保留 `infraPackages` 的六个锁定版本。
- platform delivery 的 `start_pipeline_run` 接线：`pipelineRunWorkspaces` 必须为 `bifrost-ci-infra` / `bifrost-build-ci-infra-tools` 绑定名为 `source` 的工作区；revision 与全部五个 CI 参数必须传到 run。当前 `service.go` 的显式名单尚无这两项，现版本直接起 run 会缺 workspace。两个 Pipeline 已声明通用 `bifrost.io/run-arch: amd64` 注解；CI 身份、证据映射与 EnsureLandingCI 仍由 platform S6 lane 完成。
- infra 的 `agent-config/landing/doc-consumers.yaml`：按照这次最终树重新发现、逐项人工分类并记录复核。新脚本、Tekton 清单、测试、登记表自身都可能产生新命中，不能复制旧哈希或一律登记成 constraint。
- `agent-config/agentrt-rules/prod/landing-dev.yaml` 的 infra allow 六项，与签名生效规则一致。登记与规则须已在 M0。

成功：这些输入实际存在，按最终 P/M0 运行消费者检查通过。失败：保持 infra landing 关闭，不安装 check Task 占位镜像。当前 platform checkout 缺生成器；本交付没有修改 platform。

## 1. 构建前锁定（统筹，本机）

当前 `IMAGE_DIGEST` 为 `sha256:` 加 64 个零，三个 Task 所有 image 一致；它代表 **UNBUILT**，不能用于安装。Dockerfile 的基础镜像是可审计的历史 seed pin，不代表构建当天解析结果。

在集成 infra 根，一条命令解析基础镜像：

```bash
docker buildx imagetools inspect python:3.12-slim-bookworm
```

成功：保存本次输出，取得 index digest，并确认含 linux/amd64。统筹将该摘要写入 Dockerfile 的 FROM 行，同时按该镜像版本更新 TOOLS.expected；复核 Debian 三个版本仍可下载。该命令只读 registry，不构建镜像。失败：停在本步骤，不换成未锁定 tag。

Go SHA 来源：`https://go.dev/dl/?mode=json&include=all` 的 go1.25.3 linux/amd64；Python wheels 来源：各包固定版本的 PyPI JSON / 文件页。kubectl 构建时同时核对代码里的固定 SHA 与官方 `.sha256`，任何一个不符都终止。下载执行器为 `docker/ci-infra/fetch_tools.py`。

本机离线验证（在具备 pytest/PyYAML 的 Python 环境中）：

```bash
python -m pytest -q scripts/landing
```

成功：全部测试通过。quick 在每次实际运行结束时记录 `quick_seconds`，超过 120 秒只告警；不再读取历史 CI timing，也不再写未声明的 `quick-timing.json`。历史预算链路未接线，本交付采用复核 777 N-01 允许的本次实时告警方案。失败：修复并重跑。随后统筹按仓库规则逐文件提交锁的修改；Owner 按现有 push-main 流程把集成提交推入 main，记完整 SHA 为 B。此处不提供绕过既有发布窗口的推送命令。

## 2. 仅安装构建 Pipeline（统筹，PROD 平台工具）

下文 `<B>`、`<I>`、`<P>`、`<R>`、`<M0>`、`<plan-id>` 均必须替换成上一步取得的值；SHA 均为 40 位。每个 JSON 块是一条工具调用的参数。

调用 `plan_manifest`：

```json
{"repo":"bifrost-trade-infra","path":"k8s/cicd/tekton/pipeline-build-ci-infra-tools.yaml","commit":"<B>"}
```

成功：计划 ready，只有 `cicd/Pipeline/bifrost-build-ci-infra-tools`。保存安装前同名对象的 YAML（若已存在），只读 Console / 平台对象查询即可。失败：停，不继续 apply。

服务端 dry-run 如需单独运行，在 PROD 用 `request_action` 创建 `owner_run_command`，command 仅包含对 **B 导出的这一份文件** 的 `kubectl apply --dry-run=server -f <absolute-file>`；由获批的 owner/host runner 执行，不在 Agent shell 跑。成功：server dry-run 无错误；失败：修清单。此动作只校验，不实际写资源。

调用 `request_action`：

```json
{"action":"apply_manifest","params":{"plan_id":"<plan-id>"},"reason":"W-31 安装 ci-infra 工具镜像构建 Pipeline；计划与服务端校验已核对","rollback":"按第 8 步将回退内容先提交并经 push-main 进入 main，再对该提交逐文件计划和审批应用；首次安装可保持对象未使用","work_id":"W-31"}
```

成功：Owner 在 PROD 批准后动作 executed，计划对象安装成功。失败：不发起 build；必要时按第 8 步先将回退内容进入 main，再通过平台应用。构建前必须只读确认既有 `bifrost-release-freeze-check` Task 与配套 ConfigMap 可用；它拒绝或无法读取冻结状态时 build 不会执行，不能跳过或设置 continue/retry。构建 pipeline 用既有 freeze → clone → kaniko，不依赖尚未构建的 ci-infra 工具镜像。

## 3. Owner 起构建，统筹回填摘要（PROD 平台）

首次构建由 Owner 亲自发起；Agent 代执行前须取得本次构建的明确授权。该构建是 Tier B，直接调用 `start_pipeline_run`：

```json
{"name":"bifrost-build-ci-infra-tools","revision":"<B>","params":{"revision":"<B>"}}
```

成功：PipelineRun Succeeded，`image-digest=sha256:<64hex>`，构建中的 tools 阶段逐行比对通过。失败：不回填，不安装；修正构建源的版本/哈希后新提交、新运行，不能覆盖失败证据。

统筹现在把 result 原样填入 `docker/ci-infra/IMAGE_DIGEST`，替换三个 `task-ci-infra-*.yaml` 的所有 image 摘要；记录 build run 名、B、digest。**负责人是统筹；时点是本步骤构建成功并核验之后、安装 Task 之前。**

在本机集成 infra 根运行：

```bash
python scripts/landing/test_ci_infra_pins.py --ready
```

成功：exit 0；全零、缺 Task、摘要不一致均拒绝。失败：只修锁/清单对应关系，禁止跳过检查。再次运行离线测试，提交并由 Owner 推入 main，记该安装提交为 I。

## 4. 安装 resolve / clone / check / CI Pipeline / trigger（PROD 平台）

对以下五个路径按顺序执行同一套三步，每次只处理一个文件：

1. `k8s/cicd/tekton/task-ci-infra-resolve.yaml`
2. `k8s/cicd/tekton/task-ci-infra-clone.yaml`
3. `k8s/cicd/tekton/task-ci-infra-check.yaml`
4. `k8s/cicd/tekton/pipeline-ci-infra.yaml`
5. `k8s/cicd/tekton/trigger-trade-ci.yaml`

先只读保存对应旧对象；首次安装记为 absent。之后调用一条 `plan_manifest`：

```json
{"repo":"bifrost-trade-infra","path":"<本轮路径>","commit":"<I>"}
```

成功：ready 且对象/namespace 与本轮一致。然后像第 2 步一样，通过 `owner_run_command` 对 **I 导出的本轮文件** 做一次 server dry-run。最后调用一条 `request_action`：

```json
{"action":"apply_manifest","params":{"plan_id":"<本轮plan-id>"},"reason":"W-31 安装 ci-infra 当前单份清单；已核对计划与 server dry-run；工具摘要已构建验证","rollback":"按第 8 步将回退内容先进入 main，再对回退提交逐文件 plan/apply；先恢复 trigger 停止新 push 触发","work_id":"W-31"}
```

成功：Owner 批准后 executed，并只读核对实际 spec。失败：停在本文件，不处理后续文件；按第 8 步恢复。`rbac-trigger.yaml` 本交付只增注释，权限对象与基线完全相同，**不需要写 RBAC**。既有 `pipelineruns create` 已覆盖 ci-infra，不能再加资源/动词/Secret 权限。若现场权限与仓库不同，交给 Owner 另行核对，不现场扩权。

## 5. 固定身份阳性验证（统筹，PROD 平台）

先准备 M0：它已包含本次修复后的检查器、NUL 路径扫描器、镜像锁、登记和规则；旧 `0e90252` 不能作为修复生效的可信基线，仅把修复放在候选 R 不会生效；P 是含唯一生成器的 platform SHA。从 M0 做一个只修改 allow 文档的单父提交 R，证据引用使用可核验格式且不跨 500 行阈值。如需引用更早提交，浅克隆看不到其祖先时会拒绝；改用 M0 中已有节号或审批/线程证据，不能偷偷 fetch 历史。

**不要直接拿安装代码提交作阳性样本**：它的 M0 没有新检查器且改了硬底线路径，理应拒绝。设计 §5.8 的“main 与其父”只有在 main 是上述文档候选时才可作为阳性。这个启动顺序须由统筹安排。

在已授权的 CI 验证范围内，直接调用一条 Tier B 的 `start_pipeline_run`：

```json
{"name":"bifrost-ci-infra","revision":"<R>","params":{"revision":"<R>","base":"<M0>","platformRevision":"<P>","generation":"1","purpose":"landing"}}
```

不把 CI 运行当作合入授权；保持 landing 开关关闭至全部验收完成。

成功：全部九阶段绿，results 恰好为 `infra-commit=R`、`base-commit=M0`、`platform-commit=P`、`tools-from=M0`、`doc-policy=pass`、`purpose=landing`。保存日志与 quick 秒数；push 运行不能作为落地证据。失败：保留 run 和日志，不退选旧绿。

## 6. 拒绝对照（统筹，演练分支，不能推入 main）

先在本机复制阳性 fixture；每个负例只改变表中一项，然后逐个用第 5 步的单条 `start_pipeline_run` 起 run，替换对应 R/M0。

| 样本 | 基线与候选 | 成功判据 | 失败处理 |
|---|---|---|---|
| scope | 同一 M0；R 同时改 `scripts/x.py` 与 allow `REPORT-x.md` | scope 红，consumers 及后续未执行 | 若绿，立即保持 landing 关闭并修检查器 |
| consumers | 演练基线 M0′ 加读者 `scripts/x/read.py`，引用 `agent-config/work/multi-agent/PLAN-VIEW-R4-v1.json` 但漏登记；R′ 只改 allow 报告 | scope 绿，consumers 红且点名 `unregistered_consumer` | 若被 scope 遮蔽，重做只改文档的候选；若绿，修发现器 |
| consumers 成功对照 | 上例基线正确登记 reader、正确 hits 且 reads 不交 allow；候选仍只改文档 | consumers 绿 | 核对登记，不删约束 |
| 父身份 | 阳性 R，但 base 换为另一 40 位 SHA | clone 红 `base_mismatch` | 保留日志并修 clone |
| resolve | push purpose，platformRevision 留空 | resolve 输出 40 位 SHA，失败最多三次 30 秒尝试后红 | 不在 Binding 里解析，不跳过建 run |

演练 refs 如需清理，通过已有平台/Gitea 授权操作清理，不能把拒绝样本推 main。首次安装回退优先恢复旧 trigger 停止新触发；新建但未使用的 Tasks/Pipelines 可保留，删除须另经 Owner 平台动作。旧版本恢复必须按第 8 步先让回退内容进入 main，再走 plan/apply。

## 7. 本机同镜像复算（统筹，本机；不访问集群）

准备独立干净 `WS/cand/bifrost-trade-infra`=R、`WS/cand/bifrost-platform`=P，按 clone Task 建候选根链接。`WS` 是绝对路径，`D` 是已构建 digest（包含 `sha256:`），`R/M0/P` 是上面固定值。候选必须是 WS 内的独立 clone；不能用指向宿主工作区的 worktree。M0 对象必须已在候选 clone 中，不在复算阶段 fetch。

先在容器路径内建立 M0 worktree，避免 Git 保存的绝对路径指向宿主而在 `/ws` 挂载内失效：

```bash
docker run --rm --platform linux/amd64 -v "$WS:/ws" "192.168.10.73:30500/bifrost-ci-infra-tools@$D" git -C /ws/cand/bifrost-trade-infra worktree add --detach /ws/base/bifrost-trade-infra "$M0"
```

成功：新建 base worktree 指向 M0；失败：停下核对 WS 布局，不删除或复用未知旧 worktree。随后单独运行检查：

```bash
docker run --rm --platform linux/amd64 -v "$WS:/ws" -w /ws "192.168.10.73:30500/bifrost-ci-infra-tools@$D" bash /ws/base/bifrost-trade-infra/scripts/landing/ci-infra.sh --stage all --cand /ws/cand --base /ws/base --revision "$R" --base-sha "$M0" --platform-revision "$P"
```

成功：与 CI 相同阶段、相同结果；`statics` 调用 `check-release-chain.py --scope infra`，检查本仓所有 Pipeline 的 freeze 约束和本仓 release-window 约束，明确不声称完成 flex-query 跨仓验收。跨仓默认入口仍要求固定、完整的 `bifrost-platform-plugin-flex-query` 输入，缺仓拒绝；由具备这些输入的独立发布链验收运行。`parity-static` 绿仅代表树内静态检查，不是本机完整 hook parity。失败：按阶段定位，不能用本机工具版本不同解释成通过。

已知保守边界：新分支 push 的全零 before 归一为空，doc-policy 写 `skipped(no_base)`；code-health 因没有 M0 返回 `code_health_no_base`，不伪造差值绿。设计只显式定义 doc-policy 的 no-base 例外；若需要新分支 push 全绿，需统筹补充 code-health 的 no-base 契约。


## 8. 可执行回退（统筹准备受审提交，Owner 放行）

1. 安装前保存每个路径的原提交 SHA、路径、对象身份（namespace/kind/name）和实际 spec；首次不存在记为 absent。快照是核对材料，平台不能直接接收本地 YAML。记录原提交渲染与现场 spec 是否一致；不一致先由统筹核对来源，不能把现场状态猜成某个历史提交。
2. 出现异常先保持 landing 关闭，停止后续安装。基于当前 main 准备新的回退提交：先恢复 `trigger-trade-ci.yaml` 的原有内容以停止新触发，再恢复需要回退的 Task/Pipeline。按原提交逐路径取内容、复核完整 diff、逐个 git add、用 git commit -F 提交。不要重置 main，不要直接拿旧 SHA 当作可应用计划。首次新建且未使用的对象可保留；如需删除，另走 Owner 平台动作。
3. 回退提交经复核与既有检查后，按发布窗口及 `scripts/release/push-main.sh` 流程进入 main，记新的完整 SHA 为 RB。此步骤发生在重新计划之前；本操作单不授权 Agent 自行推送。确认当前 main 同路径渲染就是 RB 的回退内容。
4. **先 trigger、后逐个 Task/Pipeline**，对 RB 的每个恢复路径重新调用 `plan_manifest`：

```json
{"repo":"bifrost-trade-infra","path":"k8s/cicd/tekton/trigger-trade-ci.yaml","commit":"<RB>"}
```

成功：计划 ready，核对对象集与回退 diff；随后按第 2 步做 server dry-run。再调用 `request_action`，由 Owner 在 PROD 批准：

```json
{"action":"apply_manifest","params":{"plan_id":"<RB-plan-id>"},"reason":"W-31 回退 ci-infra；恢复内容已受审并进入 main，先恢复 trigger；已核对计划与 server dry-run","rollback":"停止后续安装；保留当前 run 和对象证据，后续修复仍先进入 main 再重新计划","work_id":"W-31"}
```

5. 计划到执行期间若 main 的同路径渲染改变，apply 会报 `renders differently at main's head` 并拒绝。停止使用旧 plan；重新核对当前 main、形成所需修复提交并按流程进入 main 后，重新计划、dry-run、审批。不得复用旧批准、绕过 main 比较或重试强行覆盖。main 仅变其他路径时，同路径渲染一致可以继续，但仍核对计划内容。
6. 每次 executed 后只读核对实际对象 spec 与 RB 对应对象一致（忽略 status、resourceVersion 等服务端元数据）；trigger 的 infra push 条目应已恢复原状态。核对失败则停在该对象，保留计划、执行日志与实际 spec，不继续其他文件。任务对象 absent 时保留未用对象，不把它写成已恢复不存在。

动作分级依据：platform `api/internal/actions/catalog.go` 的 `start_pipeline_run` 默认为 Tier B，`classify.go` 的 PROD 集合只有三个 deliver；`api/internal/approvals/service.go` 对 Tier B 返回 400 `call directly`。构建与 CI 不创建审批单；`apply_manifest` 等 C/D 动作仍在 PROD 建单批准。

## 9. push 的检查边界（779 B-01）

`purpose=push` **只验证最终树及固定 before/after 首尾差异，未验证中间提交**。`doc-policy` 的 Owner 决定证据检查只看端点 diff，`code-health` 只比较两棵树；不能将结果通过表述成“本次 push 中每个提交都通过”。例如 M0 → B（无证据决定或 501 行报告）→ C（恢复）→ R（普通文字），单独检查 M0/B 会拒绝，但 M0/R 可以通过。测试以真实浅 clone 和 M0 导出的 CLI 固定此边界，且确认 B 对象没有被取回。

依据：`DESIGN-S6-v3-2026-10-29.md` §5.1 第 262–268 行固定 `body.after` / `body.before`，声明 push 永远不能作为落地证据；§5.2 第 275 行规定浅取 R，§5.6 第 336 行比较 M0 与 R 两份扫描。保留端点语义是为了遵循这组输入与证据契约；逐提交审计需要另行定义完整历史、merge 和 force-push 遍历规则，本轮没有引入这些规则。

多提交、merge 与 force-push 均按固定 before/after 处理，不遍历祖先。clone 必要时只补取 before 的固定对象；缺失端点失败，缺失中间对象不属于检查输入。landing 仍严格要求唯一父，push 结果始终不能用于落地授权。新分支 no-base 行为见第 7 节。可用 `bash infra/scripts/landing/ci-infra.sh --help` 查看同一语义（infra 根运行时去掉路径前缀 `infra/`）。
