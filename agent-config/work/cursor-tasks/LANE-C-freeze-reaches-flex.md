# LANE-C — 冻结管不到 flex-query 构建：它的流水线没有 release-window 任务（TD-263，flex 插件 + infra）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-C.md`。
分支：`cursor/c-flex`（bifrost-platform-plugin-flex-query）、必要时 `cursor/c-infra`（bifrost-trade-infra）。都从当前 `origin/main` 新开。

## 背景（台账 `### TD-263`）

deliver-research、Dagster 构建、market-data 构建的流水线**第一个 task 都是 `release-window`** —— 那里读发布窗口，LANE-RP 之后也在那里读冻结 ConfigMap。
`bifrost-build-flex-query` 的任务只有 `clone-plugin`、`clone-core`、`kaniko`，**没有** `release-window`。所以窗口和冻结在 Tekton 这一层都约束不到它：Owner 设了冻结要停下一切，flex-query 构建照样能跑，而且没有任何东西报告这条管道没被约束。

## 要做

1. 在 `bifrost-platform-plugin-flex-query/k8s/cicd/pipeline-build.yaml` 里把 `release-window` 加成**第一个** task，写法照 market-data 的构建流水线（`bifrost-platform-plugin-market-data/k8s/cicd/`）和 `bifrost-trade-infra/k8s/cicd/tekton/task-release-window.yaml` 的现有用法。
   - 后续 task 要依赖它（`runAfter` 或 workspace 顺序，按现有流水线的写法照抄，不要自创）。
   - 它需要的参数（仓库名等）按 market-data 那条的实际值对应填 flex-query。
2. **防线（这条是重点，比改一个 YAML 更重要）**：在 infra 的 `scripts/check-release-chain.py` 里加断言 —— **每个** `bifrost-build-*` / `bifrost-deliver-*` 流水线的第一个 task 都是 `release-window`，不是就失败并点名是哪条。
   这样下一条新建的流水线漏了它会被当场抓住，而不是像这次一样靠人读 YAML 发现。
   - 注意：`check-release-chain.py` 在 LANE-RP 分支上**被改过**。本道从当前 `origin/main` 开，RP 还没合。改同一个文件会和 RP 冲突 —— **按下面「和 RP 的关系」处理**。
3. 门禁：infra `cd scripts/release && python3 -m unittest test_ci_gate test_window_decision`（照现有模块名）、`python3 scripts/check-release-chain.py`；flex 插件 `make lint && make test`。退出码分开记录。
4. YAML 只改不 apply。报告里写清 apply 的命令和顺序，交 Claude Code。

## 和 LANE-RP 的关系（要紧）

LANE-RP 的 infra 分支改了 `scripts/check-release-chain.py` 和 `k8s/cicd/tekton/task-release-window.yaml`，而且 **RP 的 infra 半会在 Owner apply 两个 ConfigMap 之后才合并**（先合会把整条发布链冻住）。

所以：

- **把你的检查写成独立的一个函数 / 一段**，不要重排或重写该文件现有结构，尽量让它和 RP 的改动能并存。
- 做完在报告里明确写一句：你改的是 `check-release-chain.py` 的哪一段、RP 合并后预计会不会冲突。Claude Code 合并时按这句话决定先后。
- 不要去 checkout 或合并 `cursor/rp-*` 任何分支。

## 不做

不 apply、不发版、不推 main、不碰 `api/internal/`。
