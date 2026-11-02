# REVIEW r3 — DESIGN-tech-debt-runtime-2026-11-01.draft.md（r3，741 行）

只读确认。基线没有变化：infra `de152c7`、platform `bfa513d6`。

## r2 的 R1–R7：全部真改了

- **R1**：冻结拆成五步，先后写明。第 1 步改评估的读法，第 3 步要求父提交正好是导入读的那一个、只快进推；第 4 步推 overlay；渲染器在 3b 删掉；5.8-6 的验收覆盖运行时读者。引用核对无误：`agentrt_assess.go:258-263`，overlay `:63-64`。
- **R2**：E3 的代价写实了（每天一次、14 份日备份加周备、同一台 NAS、快照不算缓解）。新增 E4，github-sync 对账清单的引用 `cronjob-reconcile.yaml:39-49` 核对无误。TD-218 确实是「异地副本」那条债。
- **R3**：改按 `AGENTRT_ENV` 选前缀，库里加了 `current_user` 守卫。agentrt 的迁移里没有 `SECURITY DEFINER`，所以触发器里的 `current_user` 就是连接的角色，这道守卫成立。
- **R4**：三处都改了：manual 的 CHECK 要求有复核者且不是作者；段引用改成复合外键；`debt_floor_raised` 只给 owner 或 controller。
- **R5**：python 那半边改对了，frontend 和 platform 那半边见下面 S1。
- **R6**：重开的转换和事件都补上了；导入的 PASS 被限定在「导入时就在待签收、之后没离开过」，自动关闭不认它；独立复核挪到「规格复核」，写者不能是规格作者。T12 已按「只管三件事」改写。
- **R7**：几条 NOTE 都落了；T13 的扫描写清了；T14 删掉，并进了 5.8-2；TD-473 的基线写对了，也注明了证据只在统筹本机。

## 新问题（没有 BLOCKING）

**S1 · SHOULD-FIX · §6.4 与 T9：frontend 不能用 `ci_test`，platform 要加一个条件**
- ci-frontend 根本不跑测试：流水线只有 lint（不卡）和 build（`pipeline-ci-frontend.yaml:2,13,106-111`）。frontend 的 `package.json` 里有 `vitest`，但 CI 不调用它。所以 frontend 的 `ci_test` 什么也证明不了，T9 里「CI 真卡住的六个仓库」会误导你，实际只有五个。
- ci-platform 在 `api-scope=console` 时只跑读 `api/` 以外文件的 Go 测试，但这次运行照样显示 Succeeded（`pipeline-ci-platform.yaml:5-10`、`task-ci-platform-changes.yaml:4-5`）。所以 platform 的 Go 测试要额外核对：提交 C 那次运行的 `api-scope=full`。

**S2 · SHOULD-FIX（小）· §7.3 第 1 步 / 3a：PROD 评估会空一段时间**
- 3a 就把「评估从 `agentrt.debt` 读」发到了 PROD，但 PROD 要到 3b 才导入。这期间 PROD 的评估会把所有 TD 号都记成 `NotRead`。
- 修法：库里还没导入时回退到读 `AGENTRT_LEDGER` 文件，或者把切换开关放在导入完成之后。3a 的验收现在只看 STG。

**NOTE**
- T13 的扫描规则「8 位以上连续数字」会误伤：十六进制提交号里常有 8 位以上的连续数字，还有发布 run 名（如 `bifrost-deliver-platform-1792633362`）、`YYYYMMDD` 日期。要放过提交号和已知的编号格式。
- 7.3 第 4 步：STG 的 overlay 按工作区 CLAUDE.md §5「STG 发布 A」可以由 Agent 推，只有 PROD 那份需要你推。
- E3 写「只靠逻辑备份」说轻了：同一台 NAS 上还有 Barman 的基础备份加 WAL（见 TD-218 标题），只是从没做过恢复演练。
- 库守卫的正向测试需要测试库里有 `platform_agentrt_prod` 这个角色，但 `agentd/testdb.go:225` 里只有 dev 和 stg。

## 13 项待定的检查

- 除了 T9 里的「六个仓库」（见 S1），没有误导你的地方。
- T12-B 现在只把「接受残余风险」和「改规则」的交给你签，与「只管三件事」一致；导入的 25 条统一由你签，前后不矛盾。
- T13-C 的代价写实了。T5 和 T6 是相关的，但各自自洽。

VERDICT: PASS
