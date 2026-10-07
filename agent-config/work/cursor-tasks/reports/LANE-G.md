# LANE-G 报告 — 治理文档更正落地（TD-241）

Cursor，2026-10-07。没有改共享 checkout。worktree：`/tmp/cursor-G-bifrost-trade-infra`、`/tmp/cursor-G-bifrost-trade-worker`、`/tmp/cursor-G-bifrost-platform`（做完已删）。

rebase infra 时 `TECH_DEBT.md` 与 Claude Code 的 `90efc15` 冲突。只动了 TD-196 的「验收」行：保留他们新加的「验收结果」行，并在「验收」行末尾加上 data-clone 那一句。

## 落点

| 仓库 | 分支 | 完整 SHA |
|---|---|---|
| bifrost-trade-infra | `main` | `b3486096897d05be1616e3f0589fd6e5082b5e49` |
| bifrost-trade-worker | `main` | `7cddef467ee7a4d25d6d74ae8aa3994cf4d9b432` |
| bifrost-platform | `cursor/td-241`（未推 main；main 仍是 `a162fe867910ca781a555cae29fd7e8e90f69278`） | `7cc0844113b8713631b218d17beaf653d3264985` |

推 main 之前都 `git fetch` 并 rebase 到当时的 `origin/main`。窗口检查和 push 在同一条命令里：`release.sh window && git push origin <sha>:refs/heads/main`。两次都是「no release window open」。

## 共用门禁

- 验收：`git -C bifrost-trade-infra show origin/main:agent-config/RATCHETS.md | grep -n 'namespace=~"bifrost-\.\*"\|0 error / 65\|ci-python-bifrost-trade-api-j5d4v'` → **无输出**（exit 1）。表里的正则在单元格里写成 `bifrost-.*\|research\|plugin-.*`，避免 `|` 把 Markdown 表格拆列；读出来仍是同一条 PromQL。
- parity：`bash scripts/check-agent-config-parity.sh` → **exit 0**（`✓ Cursor ↔ Claude 治理配置一致`，Cursor 20 / Claude 20，spine D10 = BLOCKED）。工作区根的符号链接还指着没 pull 的共享 checkout（两侧仍是 `trade-execution-freeze-v2`，所以也一致）。对已推上 main 的 worktree 文件再跑同一脚本（`trade-execution-freeze-v3` 两侧都有）→ **exit 0**。
- platform：`cd console && npx vitest run` → **118 files / 801 tests passed**，exit 0。第一次全量跑失败，是因为工作树在 `/tmp`，`cssTokens.test.ts` 用 `../../../bifrost-ui` 找不到令牌文件，另外三条是 worker 超时；补上 `/tmp/bifrost-ui` 符号链接后重跑通过。`cd api && go test ./internal/probe` → **ok**，exit 0。
- `node agent-config/scripts/agent-guard/test.js` → **42 通过 / 0 失败**。preflight 只改了两行注释，匹配逻辑没动。

---

## TD-241 行 1

- Claim：成立（过时）。origin/main 告警规则已是 `namespace=~"bifrost-.*|research|plugin-.*"`（`k8s/monitoring/bifrost-alerting-rules.yaml` 的 HighErrorRate / HighLatency / WithoutHttpMetrics）。
- 改动：bifrost-trade-infra · main · `b3486096897d05be1616e3f0589fd6e5082b5e49`（`agent-config/RATCHETS.md` Prometheus 行第 5 列）
- 防线：无新测试。验收 grep 守住旧句子不再出现。
- 门禁：见共用门禁。
- 验收：同上 grep，无输出。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 1b

- Claim：成立。Failure-as-success 行仍写「只看 bifrost-* namespace 的 5xx」和修法 (3)。
- 改动：同上 SHA。现状改为「5xx 告警覆盖 bifrost-* / research / plugin-*（TD-161）」；删掉修法 (3)，原 (4) 顺延为 (3)。
- 防线：无新测试。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n '去掉 namespace 限制' origin/main -- agent-config/RATCHETS.md` → 无输出。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 2

- Claim：部分成立。三个 `test_http_metrics.py` 都在，路径没写全。已在各自 origin/main 上核对：`bifrost-research/tests/api/test_http_metrics.py`、`bifrost-platform-plugin-market-data/tests/api/test_http_metrics.py`、`bifrost-platform-plugin-flex-query/tests/test_http_metrics.py`。
- 改动：同上 SHA。TD-161 行写成这三条完整路径。
- 防线：无新测试。路径写全之后，渲染脚本才能做存在性检查（LANE-D 已说明）。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n 'bifrost-research/tests/api/test_http_metrics.py' origin/main -- agent-config/RATCHETS.md` → 有一行。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 3

- Claim：成立（过时）。`ci-python-bifrost-trade-api-j5d4v` 已不代表当前 main。
- 改动：同上 SHA。MEASURED 段换成 10-07 的 `zsgx6` / `5jndn` / `7p45j`。保留「push 到 main 之后才跑；release.sh 和 deliver pipeline 都不查 CI 结果」。
- 防线：无新测试。
- 门禁：见共用门禁。
- 验收：共用 grep 无 `j5d4v`。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 4

- Claim：台账里的 65 已过时。按 LANE-D 在 `1d471e48` 上的实测改成 0 error / 68 warning。
- 改动：同上 SHA。
- 防线：无新测试。
- 门禁：见共用门禁。
- 验收：共用 grep 无 `0 error / 65`。
- 要 Owner 批：没有
- 后续：无后续。若要把 eslint 改成阻塞，仍要先清 `react-refresh/only-export-components`（LANE-D 已记）。

## TD-241 行 5

- Claim：成立。ci-platform 不跑 Console vitest（`pipeline-ci-platform.yaml` 没有 vitest）。
- 改动：同上 SHA。TD-108（slotScheduler）和 TD-165（DoctorPanel.computing）的强度改为 `manual`，备注写明 ci-platform 只跑 `go test`、`tsc --noEmit`、check-spine、code-health。原来的 fixture / 纯函数备注保留。
- 防线：无新测试。这两条测试本身还在，只是不在 CI。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n 'slotScheduler.test.ts' origin/main -- agent-config/RATCHETS.md` 该行强度为 `manual`；DoctorPanel 行同样。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 6

- Claim：成立。强度名义上是 blocking，但 `--no-verify`、新 worktree、别的 clone、推 main 都不经过它。
- 改动：同上 SHA。强度改为「blocking（仅本地；…推 main 不检查）」，备注写入 dfb7858e 的 1/0 和 e98afbf0 之后 `1d471e48` 回到 0/0。opt-in / 不跑 vitest 的旧备注保留。
- 防线：无新测试。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n 'blocking（仅本地' origin/main -- agent-config/RATCHETS.md` → 有一行。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 7

- Claim：成立。漏了 bifrost-ui（`OVERSIZED_UI_BASELINE=1`）。
- 改动：同上 SHA。code-health 行第 5 列补上 bifrost-ui，并写明 ui 的 push 走 ci-frontend、扫的是 bifrost-trade-frontend。
- 防线：无新测试。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n 'OVERSIZED_UI_BASELINE=1' origin/main -- agent-config/RATCHETS.md` → 有一行。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 9

- Claim：部分成立。data-clone 缓存已经写在 TD-196 的「Also (round 3)」，「验收」行没有。
- 改动：同上 SHA。只改 TD-196 的「验收」行，末尾加上「经 api pod `PUT` data-clone schedule 后，workers pod 的 `maybeAutoClone` 读到 `enabled:true`（store 每个 tick 重读）」。状态字段和其他条目没动。冲突时保留了 Claude 已写入的「验收结果：部分 PASS 2026-10-07…」行。
- 防线：无新测试（验收句本身是观察项，实现不在本道）。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra show origin/main:agent-config/TECH_DEBT.md | grep -n 'maybeAutoClone' ` → 验收行含 `enabled:true`。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 10a

- Claim：成立。五处文字写「只有 Daemon 写 `ib:operator:cmd`」，platform-api 按 D-IB-Heal 写 `op=reconnect_all`。Owner 已选方案 A。
- 改动：
  - infra main `b3486096897d05be1616e3f0589fd6e5082b5e49`：`agent-config/CLAUDE.md` §3 与 `agent-config/cursor/rules/trade-execution-freeze.mdc` 换成同一句（Agent 不得写；Daemon 与 platform-api 的 `reconnect_all` 是合法写入方）。两侧 parity-id：`trade-execution-freeze-v2` → `trade-execution-freeze-v3`。
  - `scripts/agent-guard/preflight.js`：只改了约 81、85 行的注释。返回文案和匹配条件没改。
  - platform 分支 `cursor/td-241` `7cc0844113b8713631b218d17beaf653d3264985`：`agentProtocolCatalog.ts` 的 action 改为 `ib:operator:cmd write by an agent (platform-api reconnect_all is D-IB-Heal L1)`；`probe.go` 的 Detail 用同一句。
- 防线：`check-agent-config-parity.sh`（parity-id）；`agent-guard/test.js` 42 例（匹配没变）；platform vitest + `go test ./internal/probe`。
- 门禁：parity exit 0；vitest 801 passed；probe 包 ok；test.js 42/42。
- 验收：`git -C bifrost-trade-infra grep -n 'trade-execution-freeze-v3' origin/main -- agent-config/CLAUDE.md agent-config/cursor/rules/trade-execution-freeze.mdc` → 两处都有。`git -C bifrost-platform grep -n 'platform-api reconnect_all is D-IB-Heal L1' cursor/td-241 -- console/src/lib/architecture/agentProtocolCatalog.ts api/internal/probe/probe.go` → 两处都有。
- 要 Owner 批：没有（方案 A 已选）。platform 分支还没进 main，等当前 platform 发布结束再合。
- 后续：preflight 拦下时的返回字符串仍写「唯一合法写入方是 Daemon 本身」（`preflight.js` 匹配成功后的 return）。本道规定只改注释、不改匹配逻辑，所以没动。TD-221 的 runner 把 PROD gateway 切到 mock 仍不在本道。

## TD-241 行 10b′

- Claim：成立（LANE-D 新发现）。§8c 的 NodePort 表没有 Grafana 和 Dagster webserver。
- 改动：infra main `b348609…`。`AGENT_FACTS.md`「入口与 NodePort」加了 Grafana `.73:30883`（`monitoring/kube-prometheus-stack-grafana`）和 Dagster webserver `.73:30301`（`research/dagster-webserver`）。`parity-id` `agent-facts-v7` → `agent-facts-v8`，`generated` 改为 2026-10-07。
- 防线：无新测试。parity 脚本不比对 `agent-facts-v*`（它不在两侧规则对里）；按文件头要求 bump 了。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n '30883\|30301' origin/main -- agent-config/AGENT_FACTS.md` → 两行。
- 要 Owner 批：没有
- 后续：无后续

## TD-241 行 10c

- Claim：成立。data-warehouse 的 MinIO 从未跑起来（LANE-D：`deployment/minio 0/0`，PVC Pending）。
- 改动：同上 SHA。删了「第二个 MinIO @ data-warehouse」那一条。§6 GPU 行和节点表 gpu-server 行的 MinIO 短语改成「data-warehouse：从未运行，TD-237 待删」。`:202` 的 namespace 清单里的 `data-warehouse` **没动**。
- 防线：无新测试。删 namespace 等 TD-237。
- 门禁：见共用门禁。
- 验收：`git -C bifrost-trade-infra grep -n '第二个 MinIO' origin/main -- agent-config/AGENT_FACTS.md` → 无输出；`grep -n 'data-warehouse$'` 在 namespace 那一行仍有。
- 要 Owner 批：没有。要不要删 namespace 归 TD-237。
- 后续：无后续（TD-237 已有）

## TD-241 行 10d

- Claim：成立。worker `CLAUDE.md` 把未成交订单和 TWS 成交写成会落 `raw_broker.*`。插件 origin/main 的 `src` 里没有 `open_orders` / `last_execution_rows`。
- 改动：bifrost-trade-worker · main · `7cddef467ee7a4d25d6d74ae8aa3994cf4d9b432`。账户、持仓仍走 `raw_broker.*`，并保留原来的 `daemon_broker_writes_off` 条件（这条对账户和持仓仍成立）。另起一条：未成交订单与 TWS 成交实际不落库（TD-211）。
- 防线：无新测试。文档更正；行为修复仍是 TD-211。
- 门禁：纯文档，没有 lint/test 门禁。
- 验收：`git -C bifrost-trade-worker grep -n '实际不落库' origin/main -- CLAUDE.md` → 有一行；`grep -n '未成交订单、TWS 成交' origin/main -- CLAUDE.md` → 无输出。
- 要 Owner 批：没有
- 后续：无后续（TD-211 已有）

## 要 Owner 批

没有。platform 的 `cursor/td-241` 不要在当前 platform 发布结束前合进 main。
