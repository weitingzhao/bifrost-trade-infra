# LANE-N — 删掉已经没有调用方的 `ExecSQLOnPrimary`（TD-268，platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-N.md`。
分支：`cursor/n-platform`（bifrost-platform，从当前 `origin/main` 新开）。

## 背景（台账 `### TD-268`，Claim 已由 Claude Code 在 main 634e305 上复核）

TD-256 与 TD-259 把两个插件新鲜度探测都挪到插件 HTTP 之后，`api/internal/cluster/pod_exec.go:65` 的 `ExecSQLOnPrimary` **没有任何非测试调用方**。
剩下的只有定义，加上两个专门约束它的测试文件：

- `api/internal/cluster/execsql_callers_test.go` —— LANE-P2 的防线（调用点基线 2 → 0，现在已满足）
- `api/internal/cluster/pod_exec_live_test.go` —— 针对它的 live 测试

**数一个没有调用点的函数的调用点，防不住任何东西。**

## 要做

1. 删掉 `ExecSQLOnPrimary`，以及只为它存在的那两个测试（`pod_exec_live_test.go` 里如果还测别的东西，只摘掉相关部分，别整文件删）。
2. **把防线换掉**：原来的「调用点数 ≤ N」改成断言**整个仓库对 `ExecSQLOnPrimary` 这个符号的引用为 0**（它自己的移除测试除外）。这样它不会悄悄回来。
3. 门禁：`cd api && go build ./... && go vet ./... && go test ./...`，退出码分开记录。

## 绝对不要做的一件事

**不要收窄 PROD 在 `data` 命名空间的 `pods/exec`。** 我在 634e305 上核过，这两个仍在大量使用：

- `execOnPrimary` —— `data_clone.go`（十余处）、`data_clone_fk.go:165`
- `execOnMinio` —— `postgres_wal_repair.go:294` 起（`repair_cnpg_wal_store`）

所以 `k8s/platform-rbac` 不要动，`check_platform_rbac.py` 的期望也不要动。碰到想改 RBAC 的念头就停下写进报告。

## 其他边界

- 不要碰 `api/internal/releasepolicy/`、`api/internal/approvals/`（分别是 LANE-RP 和审批服务）。
- 不要碰 `mcp/platform/`（LANE-B 刚改过）。
- 不推 main、不发版、不 apply。

## 验收（Claude Code 会照跑）

合并后 `git -C bifrost-platform grep -n ExecSQLOnPrimary origin/main -- 'api/**/*.go'` 只剩新防线测试里的那一处（或零处）；`go test ./...` 退出码 0。
