# LANE-D1 报告

只做了 D1。没有做 E1，没有做第 3 阶段，没有发版、apply、写库、跑 release.sh 或起 pipeline。

## 做了什么

进度按 ADR §8 算出来，不在登记里改数字。

1. **工作项登记** `agent-config/WORK.md`：W-1 到 W-30。阶段 1–7 各一条；报告未交或写明未执行的 Cursor 道各一条；`agent-config/work/` 里仍未完成的计划各一条。每条写了来源。没有改 TECH_DEBT.md，也没有改被登记的源文件。
2. **渲染**：`render-tech-debt-page.py` 增加「工作项」分区，读 WORK.md。`--allow-stale` 生成的页面含「工作项」、W-1、W-30，没有残留 `__WORK__`。
3. **提交尾注**：`agent-config/scripts/git-hooks/lineage.sh` 在 `commit-msg` 提取 `TD-数字`、`W-数字`、`LANE-字母数字`（可多个、去重、按出现顺序），写成 `Work: …`。提取不到写 `Work: unassigned`。已有 `Work:` 不改。rebase / cherry-pick / revert 整段退出，与现有三个尾注一样。`prepare-commit-msg` 不加 Work。
4. **双轨说明**：`agent-config/CLAUDE.md` 与 `agent-config/cursor/rules/shared-worktree.mdc` 的 parity-id 从 `shared-worktree-v3` 升到 `shared-worktree-v4`，写明第四个尾注。
5. **只读检查** `scripts/check_work_trailers.py`：`--since 7d` 按仓库列出 `Work:` 缺失 / unassigned。始终 exit 0（`--self-test` 失败才非 0）。没有接成门禁，没有改 `RATCHETS.md`。
6. **platform** `GET /api/v1/progress`：从 Gitea 镜像读 infra main 的 TECH_DEBT.md 与 WORK.md，与提交血缘（Work 尾注、标题里的编号、Claude-Session）和发布到达拼接。顶层四栏：待你签收、在途、本周上线、卡住；另给 unassigned 提交计数。卡住默认 3 天，可查询 `stuck_days`（1–30）。匿名即 viewer，与 `/lineage` 相同（`auth.Require(RoleViewer)` 会拒绝匿名）。MCP 全量 server 增加只读工具 `get_progress`。`config/actions-catalog.json` 未改。`catalog_test.go` 镜像清单已同步（stdio 镜像工具 76）。

### 登记规则（实现选择）

- 阶段 1（W-1）与 LANE-D（W-12）写 **已验收**。五种开放状态仍沿用技术债。阶段必须留在登记里，删掉就凑不齐阶段 1–7，所以 VERIFY 已关闭的条目用这一个终态：不进待签、不进在途、不算卡住。
- 阶段 2（W-2）仍是 **在做**：B2 / B4 / B1R / B1R2 / B3R 在 VERIFY 为 PASS，README 的退出条件（当天发布与同步都进 PROD 审计）还没成立。
- 道的提交别名只来自标题和 `匹配` 字段，不从「关联」或正文猜，避免路径里的 `LANE-*.md` 把阶段和道绑成同一组提交。
- 本批没有登记：W3 请求写 A/B/C 全部完成；symbol_paired 台账写 PROD CHECK 已放宽；三份 REVIEW 已收进阶段 0；VERIFY 已 PASS 的 ops-arch 道，以及 cursor 报告已交且没写「未执行」的道，不重复。B1/B3 返工已被 B1R / B1R2 / B3R 的 PASS 盖过，不单列。

## 分支与 SHA

| 仓库 | 分支 | 起点（origin/main） | 功能提交 |
|---|---|---|---|
| bifrost-platform | `cursor/d1-platform` | `286c305` | `a7b86813e66546e5bc0bce1bcf034327a59c1556` |
| bifrost-trade-infra | `cursor/d1-infra` | `aa1b9a5` | `2ef0ba4119bf12cc88526f6de9f7657958e044fa` |

本报告是 infra 功能提交之后的下一次提交。分支尖端以推送后的 `cursor/d1-infra` 为准。

主检出没有改。没有动 `bifrost-platform-phase3-*`、`bifrost-trade-infra-phase3-report`、`bifrost-platform-e1`、`bifrost-trade-infra-e1`。

## 门禁

| 命令 | 结果 |
|---|---|
| `agent-config/scripts/git-hooks/lineage_test.sh` | 通过（多编号、无编号、已有不改、prepare 不加、rebase / cherry-pick 不改） |
| `python3 scripts/check_work_trailers.py --self-test` | 通过 |
| `python3 scripts/check_work_trailers.py --since 7d` | exit 0，只报告 |
| platform `api/`：`go build ./... && go vet ./... && go test ./...` | 通过（第一次 lineage 测试编译失败已修，重跑通过） |
| `mcp/platform`：`npx tsc -b && npm test` | 通过，18 pass |
| `render-tech-debt-page.py --allow-stale` | 通过（见上） |
| console 门禁 | 未跑（没有改 console） |

platform 的 pre-commit 这次没有因超长文件失败，提交已带 `Work: LANE-D1`。没有 `--no-verify`，没有改基线，没有改主检出。

### 最近 7 天基线（2026-10-07 本地扫描）

活跃检出 11 个。第 12 个是已归档的 `bifrost-analytics`（脚本按 install.sh 跳过）。`bifrost-trade-socket` 已退役且不在工作区。worktree 不扫。

| 仓库 | 提交 | 缺 Work | unassigned | 缺口 |
|---|---:|---:|---:|---:|
| bifrost-platform | 72 | 72 | 0 | 100% |
| bifrost-platform-plugin | 1 | 1 | 0 | 100% |
| bifrost-platform-plugin-flex-query | 27 | 27 | 0 | 100% |
| bifrost-platform-plugin-market-data | 4 | 4 | 0 | 100% |
| bifrost-research | 121 | 121 | 0 | 100% |
| bifrost-trade-api | 72 | 72 | 0 | 100% |
| bifrost-trade-core | 41 | 41 | 0 | 100% |
| bifrost-trade-frontend | 167 | 167 | 0 | 100% |
| bifrost-trade-infra | 411 | 411 | 0 | 100% |
| bifrost-trade-worker | 0 | 0 | 0 | 0% |
| bifrost-ui | 13 | 13 | 0 | 100% |
| **合计** | **929** | **929** | **0** | **100%** |

缺口 =（缺失 + unassigned）/ 提交数。钩子尚未合并，所以除 worker 外全是缺失。这不是门禁。

### parity

`agent-config/scripts/check-agent-config-parity.sh` exit 0。它校验的是工作区符号链接，指向**主检出**，两侧仍是 `shared-worktree-v3`。本分支的 `CLAUDE.md` 与 `shared-worktree.mdc` 都是 `shared-worktree-v4`，脚本看不到这条 worktree。

`stocks/scripts/git-hooks/install.sh` 把钩子指到主检出的脚本（符号链接解析后的目录），那里还没有 Work 提取。本分支两次提交是用 worktree 里的 `lineage.sh` 预先写入 `Work: LANE-D1` 的，已有尾注不会被旧钩子改掉。没有把别的仓库的 hooksPath 指到这条未合并的 worktree。

## 没做到的

- **Console 进度页**：LANE-D1 写明不做，等第 3 阶段合并后再开。
- **检查没有接成门禁**，也没有改 `RATCHETS.md`。文档要求只报告并给出基线。
- **`GET /api/v1/progress` 在合并前读不到 WORK.md**：文件只在本分支。合并进 infra main 之前，接口会在 `errors` 里记下 WORK.md 读失败，债的条目仍返回。
- **`api/internal/server/server.go` 的路由注册**可能和第 3 阶段冲突。本道只在 `/lineage` 旁加了 `/progress`。合并由 Claude Code 处理。

## 派发与审批

没有碰到。没有改 `internal/checklist` 的 `dispatch.go`、`executeDispatch`、husbandry-sync 派发路径，也没有改 approvals 端点、审批令牌或 `RequestActionButton`。
