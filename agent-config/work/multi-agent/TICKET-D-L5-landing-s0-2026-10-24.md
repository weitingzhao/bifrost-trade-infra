# D-L5 审批准备单：已归档，尚未提交审批（Work 565）

来源：Work 564 原索引、`INVENTORY-lifecycle-2026-10-24.md` §3.1、`CUT-lifecycle-2026-10-24.md` §5 D-L5。原 19 条分支与 20 个 accepted 结果不能互换；本单以最新数据库与 Gitea 读取为准。

本地归档：`/Users/vision-mac-trader/agent-work/d-l5-archive/2026-10-25-work-565`；`SHA256SUMS` SHA-256：`75e6a1f170f339a3eae0a7fdd39c653ed2d59c508d6253216933e8705f7fc14d`。

两个数据库的 READ ONLY snapshot 使用 agent_reader。AGENT_FACTS 给出主机 .73:30432，但没有写平台库名；库名另外按 platform-agentrt-env.patch.yaml 核实：PROD bifrost_platform、STG bifrost_platform_stg。真实 mission_id 恰好就是 M-n，以下是 SQL 读出值，未从显示编号猜测。

共 13 个 mission、81 个任务、91 个尝试；20 个 accepted 实现结果；34 份完整自包含 bundle。14 份额外归档覆盖取消、失败和被替代分支。缺失远端 ref 的分支通过 Gitea 按确切 SHA fetch 成功；不把这些恢复出的 ref 冒称远端仍存在。

STG M-27 Q07：a1 failed，DB pushed_ref/pushed_commit 为 null；远端 a1=c073b353526fd69fe054486452b1e8af3109b0fd，按观察到的 ref 额外保全。accepts_attempt=true 的 verification 明确选择 a2=a5c3c28d972fa989fb843a6ea2bafdfb9c9eb49e。

main 快照：`bifrost-platform` = `ed8bb2276d423085014d80fddebfe2937c60f3be`；`bifrost-trade-infra` = `e742f6745132006a2945d3aa5be20f28c6a45069`。

全部 34 个 SHA 都不是此次 main 快照的祖先；main 日志没有 “This reverts commit <完整 SHA>” 的匹配。运行时 landing/revert notes 另存于 snapshot。没有按标题/patch-id 代替对象归档；未做等价 cherry-pick 或手改 revert 的人工裁决，不能把上述有限检查写成“绝无等价代码”。

所有任务均为 accepted 或 cancelled；plan/review/verify 是相应工作的配套任务，实施类已取消任务也全部列出。没有未结束的新任务混入范围；本单对整 mission 设置 no_merge，阻止原尝试合入，不改任务的交付状态。PROD M-1、M-2、M-4 是 Owner 自己的注释工作，不是演练；内容已作为新提交从 platform w31/dl5-comments 取回，并由 Owner 于 2026-10-25 推至 platform main：93399f27（M-4）、ce5d2c30（M-1）、ca4f8149（M-2）。这三个 mission 保留 no_merge，仅表示原尝试不合入；原始对象归档保留。其余 mission 仍按历史演练处置。除上述已用新提交取回的三项外，若 Owner 仍需要任一任务，该 mission 整体排除并重建参数，不在执行时扩大/缩小。

## STG 当前 mission 与全部任务

读取时间 `2026-10-25T04:40:50.272073+00:00`；scope 版本用 mission.version，没有另一个 scope_version 字段。

### M-103 · version 2 · done

任务背景：W-31 drill on STG: T24 and Gate A T34 cases 5 and 8 (one freeze of the STG agentd)。

完整旧 scope：`{"repos": ["bifrost-trade-infra"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5G4W33CRXXVX4C7GJTCJ3VR` | implement / accepted | `a_01M5G4WE3FA4EFXYAGK8BHCZ92` |
| `t_01M5G6RTTDHSRMA8NTY1V8RPBW` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5G6SR376DDJ8CYA5Q0KW510` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-16 · version 2 · done

任务背景：T26 rework drill on STG。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M595BAVBMBJWDV5QWMSWJ4J6` | implement / accepted | `a_01M595CY0ZE9EG9GTDE40E41XX` |
| `t_01M595CF9PN6HHCNGGS5V2HJK5` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M595DV7P7ZSBD5495RMGA4N0` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M595E9WHQFDGJJXP325CPRTQ` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-2 · version 2 · done

任务背景：2.2 walkthrough 2: Cursor writes, Codex reviews (UniFi client tests)。

其它已取消实现任务也在本 mission 放弃范围：Gate A T06 probe: a failed experiment。它们不需要继续交付，已有推送对象均另行保全。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M50M1CZSDN8PNHRH8C2241RS` | implement / accepted | `a_01M50M1FDJVG8SDC39N32CKH7E` |
| `t_01M50M53QQDND5GE09QAHGBANC` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M50M5JCD8ST2GFC9ZKSPWJ62` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M50P8BGEJWJV767MMT1G16ZP` | implement / cancelled | `无 accepts_attempt 记录` |
| `t_01M50P9RZYYEKX3H8HKEY3GTA3` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M50PB4Y94J1EDW6A956S6HFT` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M50PBKK2XEQQQVE2NCG43452` | review / cancelled | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-23 · version 2 · done

任务背景：confine walk 2 10-19 (b): a review that reaches its verdict (STG)。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5B37AYBAHQTM6RMQZZHE3AT` | implement / accepted | `a_01M5B37K81CZ9TRQ710SNERPZ3` |
| `t_01M5B39W70GRQQE33BGZ63TWKC` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5B3B8570R2QSCYNV2CD2ZD6` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-24 · version 2 · done

任务背景：confine walk 3 TD-382 10-19。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5B6KKPMM15HZB4BC0ZWVJ5R` | implement / accepted | `a_01M5B6KMED2TQVWSM7XNF6DW2N` |
| `t_01M5B6MZYCJNMZ4SRY5RFTZMPD` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5B6PBX2QSBHGA2EYZBQSWGG` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-26 · version 2 · done

任务背景：W-31 Gate B 实测（STG）：T04 冒充批准记告警、T13 执行者看不到业务键。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5BSBEZ7J3BQM0EV7SG3NB2N` | implement / accepted | `a_01M5BSBSNMF0CPD13A3KPGZ80D` |
| `t_01M5BSC85KWJE76JYT2JCSQXK6` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BSCPTJGWKSRFKFE5NAZJDC` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-27 · version 2 · done

任务背景：W-31 2.2-31 基准题（STG 预演）：6 道回放题经运行时从领到结论。

其它已取消实现任务也在本 mission 放弃范围：Q12 (Python): refactor(recorder): the fold result is opaque; publish takes nothing else；Q20 (shell): the Gitea protection probe compares Gitea's words whole; a lost PR answer is found and closed。它们不需要继续交付，已有推送对象均另行保全。

完整旧 scope：`{"repos": ["bifrost-platform", "bifrost-trade-infra"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5BSPFV3S9ET52X3JT76HJFS` | implement / accepted | `a_01M5BSPXNQ4ZHGGX7FWE6D7543` |
| `t_01M5BSPFV8JBH908TR6M58S6Q9` | implement / accepted | `a_01M5BSRVB127GEYXY98K3Y2DNR` |
| `t_01M5BSPFVBXYBAQYADX2KPVF1X` | implement / accepted | `a_01M5BSW6X1K7QVX47Y2V04FG7R` |
| `t_01M5BSPFVDY1N34EGQ5THXYMMD` | implement / accepted | `a_01M5BSYM56ZY324FK8KVWKJ1XX` |
| `t_01M5BSPFVFY0MY6J7NABB6SR5C` | implement / cancelled | `无 accepts_attempt 记录` |
| `t_01M5BSPFVJZFBAZ2XES6GPFTTM` | implement / cancelled | `无 accepts_attempt 记录` |
| `t_01M5BSS5QFQ0F4YN8P1HC0AZ29` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BSTHNEJ4S5GK3AV474Z60X` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BSYNG6B27DWAQVMKYQ1D59` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT0YQW8D2TZN4C0DYQGEAF` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT3PMBCXZ0MS1543MK8C3B` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT5H7ECT729M3K51J3VTKV` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT5ZWB8PVV56G0RRJWX0E8` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT6EH03PKWN39VNPP7SVAV` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT7BTJ2DNKJ4CK45AP9S82` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BT8940HP21S9048128C63G` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BTBY9X86ZTEA8XZFZM1V3X` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BTE1MDCFMEKMCDS5TZC6GC` | verify / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

## PROD 当前 mission 与全部任务

读取时间 `2026-10-25T04:40:50.237386+00:00`；scope 版本用 mission.version，没有另一个 scope_version 字段。

### M-1 · version 2 · done

任务背景：在 api/internal/agentrt/agentrtapi/goals.go 的 GoalRepos 上方补一段注释：说明以后要让目标能指定新仓库该怎…。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M511RV9S41AEW9CDA76024Q3` | implement / accepted | `a_01M511S4GWWFHB0HPA5F36NPF4` |
| `t_01M511TG2R2KD16YZ4982YV1BP` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M511X7ZB8W33K9NW2M6TPN6C` | review / accepted | `无 accepts_attempt 记录` |

该 mission 是 Owner 自己的注释工作，不是演练；内容已从 platform `w31/dl5-comments` 以新提交 `ce5d2c30` 取回，由 Owner 于 2026-10-25 推至 platform main。no_merge 保留，仅表示原尝试不合入；配套 plan/review/verify 不另计实现交付，原始对象归档保留。

### M-13 · version 2 · done

任务背景：W-31 Gate B 实测（PROD）：T04 冒充批准记告警、T13 执行者看不到业务键。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5BSTGPP9FC3PCF4NF5PM7GD` | implement / accepted | `a_01M5BSTSRZR5BKTRPJ63TQMGRG` |
| `t_01M5BSV7QAMQ6F4JH3JR5KGTSX` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BSZBJG0VE80TJ9S0FMVX20` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-15 · version 2 · done

任务背景：W-31 2.2-31 ★ 正式环境：6 道基准题经运行时从领到结论，无人插手。

其它已取消实现任务也在本 mission 放弃范围：Q12 (Python): refactor(recorder): the fold result is opaque; publish takes nothing else；Q20 (shell): the Gitea protection probe compares Gitea's words whole; a lost PR answer is found and closed。它们不需要继续交付，已有推送对象均另行保全。

完整旧 scope：`{"repos": ["bifrost-platform", "bifrost-trade-infra"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M5BV3W403F0SYH6HF8RAFNJ0` | implement / accepted | `a_01M5BV45VGR5QFM2KQPJZA7EC2` |
| `t_01M5BV3W43ETJPVBT55T2XYW30` | implement / accepted | `a_01M5BV6M1PNF9PA5YE2TM8BY8P` |
| `t_01M5BV3W45NDSBHBTEFY4RMT97` | implement / accepted | `a_01M5BV823FS69FQV6X6FXKSH1V` |
| `t_01M5BV3W48B5HGHZB5JJKHE81G` | implement / accepted | `a_01M5BVAM7BP316DGR5951GMG7J` |
| `t_01M5BV3W4AHSAB5XXNJWT3FWJD` | implement / cancelled | `无 accepts_attempt 记录` |
| `t_01M5BV3W4CCAPD00XXEB4PKYJY` | implement / cancelled | `无 accepts_attempt 记录` |
| `t_01M5BV6XJ1T18XPBE0HJCZD1WQ` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BV89GA9DND4CQ9SD6KSKQA` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVB1CZTKJQC6DX73Y63GCE` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVCVZPG4E6WF85RRPYJ3MD` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVF57KYHAK9XB3FRDTAGZ3` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVGZTGDDG9N5521AN5NZKC` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVHEFDGEP285RTG0SZ2TGR` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVHX42N9QPY2WDABTZ8QEV` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVJTDKPN76M1FEHPEZ2FYX` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVK92D2TSQMAHDG59CRGFF` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVP0Z1FG5NQ47BQMRGERQX` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5BVRRV9QBVGK63FC13GMZKD` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5C0YY7H2PCG0T8J98X43XZ1` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M5C124RRX1GDAD2XTRXXB9Z9` | verify / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-2 · version 3 · done

任务背景：在 api/internal/agentrt/store/repos.go 的 Repos 上方补一段注释：说明新增一个仓库要填哪两项（Verify、Test…。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch", "out_of_scope": ["The comment on GoalRepos in api/internal/agentrt/agentrtapi/goals.go (mission M-1).", "Adding a repository to Repos or changing any Verify or TestDirs value.", "Changing checkTest, planparse.go or any other code.", "Editing the comments on Repo, RepoNames, SpecTimeoutS or ImplementSpec."]}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M51EG5TBPF16TXV6SGY5E5M2` | plan / accepted | `无 accepts_attempt 记录` |
| `t_01M51EHZ92V5F2PRB7JCZVHTQ3` | implement / accepted | `a_01M51EJ05WGZGTKNWW7WYR9SE6` |
| `t_01M51EQXPQ9CAC4HCW1WP53M4G` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M51ES9MXG579B3408P457V21` | review / accepted | `无 accepts_attempt 记录` |

该 mission 是 Owner 自己的注释工作，不是演练；内容已从 platform `w31/dl5-comments` 以新提交 `ca4f8149` 取回，由 Owner 于 2026-10-25 推至 platform main。no_merge 保留，仅表示原尝试不合入；配套 plan/review/verify 不另计实现交付，原始对象归档保留。

### M-3 · version 2 · done

任务背景：2.3 agent host PROD walk: agent-06 on PROD (safego and statefile tests)。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch"}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M55AN78GPF9V6NFZFS4KJP8N` | implement / accepted | `a_01M55ANAD0BY5929G318XMKJ1K` |
| `t_01M55AN78M1MX9NF9Q958T96Z3` | implement / accepted | `a_01M55ANB9A6WEB66V4HTMVVC11` |
| `t_01M55AQKM4YWG9BK0P71VY2M2D` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M55AQKN3YEWGBNJHGYQ0RTBS` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M55AR28TN9TR0DMZZ2Q5G9DK` | review / accepted | `无 accepts_attempt 记录` |
| `t_01M55AR29AV28P1PXYFW6JB0NN` | review / accepted | `无 accepts_attempt 记录` |

该 mission 全部任务均按历史演练处置；配套 plan/review/verify 不另计实现交付。

### M-4 · version 3 · done

任务背景：在 api/internal/safego/safego.go 的 Go 函数上方补一段注释，说明 recover 之后为什么要记日志再继续。

完整旧 scope：`{"repos": ["bifrost-platform"], "max_action": "branch", "out_of_scope": ["Changing the behaviour of Go, Recover, Do or record.", "Rewording the package doc or the comments on Recover, Do or Contained.", "Adding or changing tests.", "Touching callers of safego.Go in other packages.", "Console or governance catalog changes."]}`；旧 no_merge：不存在。

| task_id | role / state | 被收下的 attempt（或无） |
|---|---|---|
| `t_01M56J3D55HYKVYFZ0ZR7NH977` | plan / accepted | `无 accepts_attempt 记录` |
| `t_01M56J5QPAAQQP53KV4MQYCW5Q` | implement / accepted | `a_01M56J5RB40TESB4AN7RNXDRQ6` |
| `t_01M56J80XXX3ZGMXPYKFMD4T4G` | verify / accepted | `无 accepts_attempt 记录` |
| `t_01M56JB7FGS87Z8A7ZHA7DGXEN` | review / accepted | `无 accepts_attempt 记录` |

该 mission 是 Owner 自己的注释工作，不是演练；内容已从 platform `w31/dl5-comments` 以新提交 `93399f27` 取回，由 Owner 于 2026-10-25 推至 platform main。no_merge 保留，仅表示原尝试不合入；配套 plan/review/verify 不另计实现交付，原始对象归档保留。

## 全部尝试的数据库字段

plan/review/verify 等任务没有独立代码 ref 时，归档为环境 runtime.json 中的任务/尝试/验收记录；不伪造 accepted attempt 或代码 bundle。accepted 实现尝试按 accepts_attempt 关联；其它任务仅 state=accepted 不能推导一次代码合入。Q07 a1 的远端额外分支见后表。

### STG 全部尝试（包括不产代码的任务）

| mission / task | attempt_id / no / state | DB pushed_ref / pushed_commit |
|---|---|---|
| M-2 `t_01M50M1CZSDN8PNHRH8C2241RS` | `a_01M50M1FDJVG8SDC39N32CKH7E` / a1 / submitted | `refs/heads/agent/t_01M50M1CZSDN8PNHRH8C2241RS/a1` / `f30cdd8a6077ece6248f70706f0562fb84791801` |
| M-2 `t_01M50M53QQDND5GE09QAHGBANC` | `a_01M50M540BBZD9DWQFEJ6NFYX4` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M50M5JCD8ST2GFC9ZKSPWJ62` | `a_01M50M5KAGDJS3CXJW9NTE72CM` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M50P8BGEJWJV767MMT1G16ZP` | `a_01M50P92FXWDPR3TWXR8BK1435` / a1 / submitted | `refs/heads/agent/t_01M50P8BGEJWJV767MMT1G16ZP/a1` / `c07d318c0b2d2f0fbba4b01195d4bdb94b3af2b5` |
| M-2 `t_01M50P8BGEJWJV767MMT1G16ZP` | `a_01M50PA7YZVF1SCWS0173H1T1S` / a2 / submitted | `refs/heads/agent/t_01M50P8BGEJWJV767MMT1G16ZP/a2` / `667fe2abddb3901f69708ca9084f3879c345cd0b` |
| M-2 `t_01M50P9RZYYEKX3H8HKEY3GTA3` | `a_01M50P9SDY1DZYCZ05HVT8RV5V` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M50PB4Y94J1EDW6A956S6HFT` | `a_01M50PB5FE0X3ZT1VRXGC1CJFH` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-16 `t_01M595BAVBMBJWDV5QWMSWJ4J6` | `a_01M595BJ2XWJ5GSQR4AMV7PA6P` / a1 / submitted | `refs/heads/agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a1` / `00ab399377e0d06d92d98c0987ff39300903e249` |
| M-16 `t_01M595BAVBMBJWDV5QWMSWJ4J6` | `a_01M595CY0ZE9EG9GTDE40E41XX` / a2 / submitted | `refs/heads/agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a2` / `586a1c029aa3bd4ac95850bbd75dc9cfcec889c1` |
| M-16 `t_01M595CF9PN6HHCNGGS5V2HJK5` | `a_01M595CFPX7NDWY8NFD1EK0Q0S` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-16 `t_01M595DV7P7ZSBD5495RMGA4N0` | `a_01M595DVKYXJ1DEFXSMDYX151R` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-16 `t_01M595E9WHQFDGJJXP325CPRTQ` | `a_01M595EAYF4AMDPNEK7TMGW9RR` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-23 `t_01M5B37AYBAHQTM6RMQZZHE3AT` | `a_01M5B37K81CZ9TRQ710SNERPZ3` / a1 / submitted | `refs/heads/agent/t_01M5B37AYBAHQTM6RMQZZHE3AT/a1` / `f4d19631ba58a0e03af5c45f394aff10268dabdc` |
| M-23 `t_01M5B39W70GRQQE33BGZ63TWKC` | `a_01M5B39WJ26Y4MVCJX2RMMG2TA` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-23 `t_01M5B3B8570R2QSCYNV2CD2ZD6` | `a_01M5B3B92G2324AK6RVQSN3XG8` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-24 `t_01M5B6KKPMM15HZB4BC0ZWVJ5R` | `a_01M5B6KMED2TQVWSM7XNF6DW2N` / a1 / submitted | `refs/heads/agent/t_01M5B6KKPMM15HZB4BC0ZWVJ5R/a1` / `9da7881ed6c017f73d244cb20e934aef07f38397` |
| M-24 `t_01M5B6MZYCJNMZ4SRY5RFTZMPD` | `a_01M5B6N02B31FXHXDQ3P5M9ZJ3` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-24 `t_01M5B6PBX2QSBHGA2EYZBQSWGG` | `a_01M5B6PCH4PA2B8T5E4V19TX1Y` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-26 `t_01M5BSBEZ7J3BQM0EV7SG3NB2N` | `a_01M5BSBSNMF0CPD13A3KPGZ80D` / a1 / submitted | `refs/heads/agent/t_01M5BSBEZ7J3BQM0EV7SG3NB2N/a1` / `cecf2c7bee55b326c0885e5392b63dc55346733f` |
| M-26 `t_01M5BSC85KWJE76JYT2JCSQXK6` | `a_01M5BSC8P4GNPTJ793JF0BV905` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-26 `t_01M5BSCPTJGWKSRFKFE5NAZJDC` | `a_01M5BSCQ6019B2S9XFRBXC1TCA` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BSPFV3S9ET52X3JT76HJFS` | `a_01M5BSPXNQ4ZHGGX7FWE6D7543` / a1 / submitted | `refs/heads/agent/t_01M5BSPFV3S9ET52X3JT76HJFS/a1` / `e56d0c906c89b62a205df7ad6a1784abeda61588` |
| M-27 `t_01M5BSPFV8JBH908TR6M58S6Q9` | `a_01M5BSRVB127GEYXY98K3Y2DNR` / a1 / submitted | `refs/heads/agent/t_01M5BSPFV8JBH908TR6M58S6Q9/a1` / `7a0a121c65cd56863ff24d218b0d6bee982a525f` |
| M-27 `t_01M5BSPFVBXYBAQYADX2KPVF1X` | `a_01M5BSTC7SHPNNQ7ZP73PFGJS4` / a1 / failed | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BSPFVBXYBAQYADX2KPVF1X` | `a_01M5BSW6X1K7QVX47Y2V04FG7R` / a2 / submitted | `refs/heads/agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a2` / `a5c3c28d972fa989fb843a6ea2bafdfb9c9eb49e` |
| M-27 `t_01M5BSPFVDY1N34EGQ5THXYMMD` | `a_01M5BSYM56ZY324FK8KVWKJ1XX` / a1 / submitted | `refs/heads/agent/t_01M5BSPFVDY1N34EGQ5THXYMMD/a1` / `839825bc6ba660ca0d2390410d88eb1aec90e386` |
| M-27 `t_01M5BSPFVFY0MY6J7NABB6SR5C` | `a_01M5BT0TN4V6HHSKXPQ2C9GXXW` / a1 / submitted | `refs/heads/agent/t_01M5BSPFVFY0MY6J7NABB6SR5C/a1` / `782e146c096565207c1c204749816de0a697228a` |
| M-27 `t_01M5BSPFVFY0MY6J7NABB6SR5C` | `a_01M5BT8KSD0BKXPY8PGPGKESKD` / a2 / submitted | `refs/heads/agent/t_01M5BSPFVFY0MY6J7NABB6SR5C/a2` / `7d062cdb0a5828a27e0a40b1cab0f478328f176d` |
| M-27 `t_01M5BSPFVJZFBAZ2XES6GPFTTM` | `a_01M5BT3DS8A1TJP4ZTTMDEM0P8` / a1 / submitted | `refs/heads/agent/t_01M5BSPFVJZFBAZ2XES6GPFTTM/a1` / `d01ddf8d6438c5a2c9e1918e35b00231b528c4a3` |
| M-27 `t_01M5BSPFVJZFBAZ2XES6GPFTTM` | `a_01M5BTBQFTHK8RGGX0R8MTS6G6` / a2 / submitted | `refs/heads/agent/t_01M5BSPFVJZFBAZ2XES6GPFTTM/a2` / `cf95d341823acb5a149e20dac4f47af18575582f` |
| M-27 `t_01M5BSS5QFQ0F4YN8P1HC0AZ29` | `a_01M5BT58G64ZTJWN3M2MGERY64` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BSTHNEJ4S5GK3AV474Z60X` | `a_01M5BT5W6CSZ5SFZEFZ7PED6GK` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BSYNG6B27DWAQVMKYQ1D59` | `a_01M5BT691KJY9P61ZBF6B4E93V` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT0YQW8D2TZN4C0DYQGEAF` | `a_01M5BT7BBDPXP6ZWD7RPVSS7DA` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT3PMBCXZ0MS1543MK8C3B` | `a_01M5BT7V3ZTYVFSM1Y0J7WGJC2` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT5H7ECT729M3K51J3VTKV` | `a_01M5BT88XP9ET3H23VGNYKYHNN` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT5ZWB8PVV56G0RRJWX0E8` | `a_01M5BTDM5RKNRMRPR80J7F8GYQ` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT6EH03PKWN39VNPP7SVAV` | `a_01M5BTHP6W1PS7Q72V3WZ6ZN76` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT7BTJ2DNKJ4CK45AP9S82` | `a_01M5BTQ920VY8V6R39ET8ZGTYS` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BT8940HP21S9048128C63G` | `a_01M5BTTCREFJ6ZWYJGGCY54GSS` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BTBY9X86ZTEA8XZFZM1V3X` | `a_01M5BTY43MK28PA8TB6NKNE614` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-27 `t_01M5BTE1MDCFMEKMCDS5TZC6GC` | `a_01M5BTYEZ6D56E2K07MPP9GR6P` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-103 `t_01M5G4W33CRXXVX4C7GJTCJ3VR` | `a_01M5G4WE3FA4EFXYAGK8BHCZ92` / a1 / lost | `refs/heads/agent/t_01M5G4W33CRXXVX4C7GJTCJ3VR/a1` / `393f1608729e42524a96a040b02d75ef166e2275` |
| M-103 `t_01M5G4W33CRXXVX4C7GJTCJ3VR` | `a_01M5G6S6TCPC04T53EJRAH6E17` / a2 / cancelled | NULL / NULL（无数据库推送记录） |
| M-103 `t_01M5G6RTTDHSRMA8NTY1V8RPBW` | `a_01M5G6S6V34YVDGXTTKDMP56DC` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-103 `t_01M5G6SR376DDJ8CYA5Q0KW510` | `a_01M5G6SRM4NR1VB8PRNJB4EJ2F` / a1 / submitted | NULL / NULL（无数据库推送记录） |

### PROD 全部尝试（包括不产代码的任务）

| mission / task | attempt_id / no / state | DB pushed_ref / pushed_commit |
|---|---|---|
| M-1 `t_01M511RV9S41AEW9CDA76024Q3` | `a_01M511S4GWWFHB0HPA5F36NPF4` / a1 / submitted | `refs/heads/agent/t_01M511RV9S41AEW9CDA76024Q3/a1` / `a8c886df038fbd71b119c9a1e15dfd9de1cddf76` |
| M-1 `t_01M511TG2R2KD16YZ4982YV1BP` | `a_01M511TGYN67QBM55DJAE397D7` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-1 `t_01M511X7ZB8W33K9NW2M6TPN6C` | `a_01M511X8MXVA66FM2MAS2JQR8Y` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M51EG5TBPF16TXV6SGY5E5M2` | `a_01M51EGKH208CEFXAW537MBYE7` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M51EHZ92V5F2PRB7JCZVHTQ3` | `a_01M51EJ05WGZGTKNWW7WYR9SE6` / a1 / submitted | `refs/heads/agent/t_01M51EHZ92V5F2PRB7JCZVHTQ3/a1` / `d7ce5db6a38245fd9a6f2069d05f4885ccac3757` |
| M-2 `t_01M51EQXPQ9CAC4HCW1WP53M4G` | `a_01M51EQXSQH1VA2WMPM3EB5KDF` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-2 `t_01M51ES9MXG579B3408P457V21` | `a_01M51ESA60XETGGK1519204Y27` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-3 `t_01M55AN78GPF9V6NFZFS4KJP8N` | `a_01M55ANAD0BY5929G318XMKJ1K` / a1 / submitted | `refs/heads/agent/t_01M55AN78GPF9V6NFZFS4KJP8N/a1` / `a27c23cf18b1184fce2c3b3e09341b237a0c609c` |
| M-3 `t_01M55AN78M1MX9NF9Q958T96Z3` | `a_01M55ANB9A6WEB66V4HTMVVC11` / a1 / submitted | `refs/heads/agent/t_01M55AN78M1MX9NF9Q958T96Z3/a1` / `42bb2c9672b94b1178797d062df0e72dd789f200` |
| M-3 `t_01M55AQKM4YWG9BK0P71VY2M2D` | `a_01M55AQKR0J3SR2MZYDN4GQB8V` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-3 `t_01M55AQKN3YEWGBNJHGYQ0RTBS` | `a_01M55AQMH9W5YAWG47GD6G96ME` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-3 `t_01M55AR28TN9TR0DMZZ2Q5G9DK` | `a_01M55AR2MB4TMV0PAETNCQ8Q6V` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-3 `t_01M55AR29AV28P1PXYFW6JB0NN` | `a_01M55AR31V0YJ9VNJ3E0T78GGZ` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-4 `t_01M56J3D55HYKVYFZ0ZR7NH977` | `a_01M56J3EQ53FNYJKJS6R17KWKK` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-4 `t_01M56J3D55HYKVYFZ0ZR7NH977` | `a_01M56J4TE124XRZTE5YVT4WF8B` / a2 / submitted | NULL / NULL（无数据库推送记录） |
| M-4 `t_01M56J5QPAAQQP53KV4MQYCW5Q` | `a_01M56J5RB40TESB4AN7RNXDRQ6` / a1 / submitted | `refs/heads/agent/t_01M56J5QPAAQQP53KV4MQYCW5Q/a1` / `d75de4f31f5a54b4b74de4f53737741970a819f5` |
| M-4 `t_01M56J80XXX3ZGMXPYKFMD4T4G` | `a_01M56J817BVAYKGD0GMNKRWNNM` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-4 `t_01M56JB7FGS87Z8A7ZHA7DGXEN` | `a_01M56JB80Z3ZANP9BQWEBAZ6D4` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-13 `t_01M5BSTGPP9FC3PCF4NF5PM7GD` | `a_01M5BSTSRZR5BKTRPJ63TQMGRG` / a1 / submitted | `refs/heads/agent/t_01M5BSTGPP9FC3PCF4NF5PM7GD/a1` / `247702576212beb040be8d2a0ddd5bf2f6571a9d` |
| M-13 `t_01M5BSV7QAMQ6F4JH3JR5KGTSX` | `a_01M5BSYZVFY4K97MK0DXXEJBZ6` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-13 `t_01M5BSZBJG0VE80TJ9S0FMVX20` | `a_01M5BSZBRNQH28BBSJRT3QCJJ6` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BV3W403F0SYH6HF8RAFNJ0` | `a_01M5BV45VGR5QFM2KQPJZA7EC2` / a1 / submitted | `refs/heads/agent/t_01M5BV3W403F0SYH6HF8RAFNJ0/a1` / `003c2f309e7d0f6dcfd749925f5e6a235ee442af` |
| M-15 `t_01M5BV3W43ETJPVBT55T2XYW30` | `a_01M5BV6M1PNF9PA5YE2TM8BY8P` / a1 / submitted | `refs/heads/agent/t_01M5BV3W43ETJPVBT55T2XYW30/a1` / `0260d57c65df2ff86f2dec5885785f65e79d8f34` |
| M-15 `t_01M5BV3W45NDSBHBTEFY4RMT97` | `a_01M5BV823FS69FQV6X6FXKSH1V` / a1 / submitted | `refs/heads/agent/t_01M5BV3W45NDSBHBTEFY4RMT97/a1` / `da7d79a49f42a73c2ecedce9e158575ddde30554` |
| M-15 `t_01M5BV3W48B5HGHZB5JJKHE81G` | `a_01M5BVAM7BP316DGR5951GMG7J` / a1 / submitted | `refs/heads/agent/t_01M5BV3W48B5HGHZB5JJKHE81G/a1` / `be4563eadeaccf041d0d072c6d8b51e977e22735` |
| M-15 `t_01M5BV3W4AHSAB5XXNJWT3FWJD` | `a_01M5BVCSQSW1H3RPH8CMGTC3RY` / a1 / submitted | `refs/heads/agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a1` / `96d023703f439ae647948e94e3fe22028d356462` |
| M-15 `t_01M5BV3W4AHSAB5XXNJWT3FWJD` | `a_01M5BVKV7FX0STKXV8DBQHJA2G` / a2 / submitted | `refs/heads/agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a2` / `7cf9f2c94f17da0a761c286a4e2a3605a809f2ca` |
| M-15 `t_01M5BV3W4AHSAB5XXNJWT3FWJD` | `a_01M5C0VS6GRQR13QRDHY6GQ6XV` / a3 / submitted | `refs/heads/agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a3` / `d85abcce213529ed9b9d7e55ae9ac16cec8640c4` |
| M-15 `t_01M5BV3W4CCAPD00XXEB4PKYJY` | `a_01M5BVF24WSAX2N1ZC5T24K3WH` / a1 / submitted | `refs/heads/agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a1` / `222ed9792413f56eb10efa2859e2c9a6b0887555` |
| M-15 `t_01M5BV3W4CCAPD00XXEB4PKYJY` | `a_01M5BVNVSGT9DSRRSSC61X0M16` / a2 / submitted | `refs/heads/agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a2` / `056abcdfb35747b52c7d4f948f4cebfc736555a0` |
| M-15 `t_01M5BV3W4CCAPD00XXEB4PKYJY` | `a_01M5C0YS4SNZGTHJVT1836B51Z` / a3 / submitted | `refs/heads/agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a3` / `becfcab138be358ea3091e82c321ce0c704e0fdd` |
| M-15 `t_01M5BV6XJ1T18XPBE0HJCZD1WQ` | `a_01M5BVGJ4QQ2CFMAK5Z58HYKSJ` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BV89GA9DND4CQ9SD6KSKQA` | `a_01M5BVH5SDT5SNN1CMXKCBAHFP` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVB1CZTKJQC6DX73Y63GCE` | `a_01M5BVHJJFSQGS7K1BGJPZ7NPA` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVCVZPG4E6WF85RRPYJ3MD` | `a_01M5BVJMVDTVVB1JC3JM52WYJK` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVF57KYHAK9XB3FRDTAGZ3` | `a_01M5BVK4JQVJZQNHHNEVJTRQSW` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVGZTGDDG9N5521AN5NZKC` | `a_01M5BVKGCS6P6PTE9NQ3CR16EH` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVHEFDGEP285RTG0SZ2TGR` | `a_01M5BVRBYRMDFJGD4CRQ7V1KEK` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVHX42N9QPY2WDABTZ8QEV` | `a_01M5BVXH4AVC39T4GA976BV6WN` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVJTDKPN76M1FEHPEZ2FYX` | `a_01M5BW20V4RE15AY7FA16BW498` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVK92D2TSQMAHDG59CRGFF` | `a_01M5BW4ZQSHHTSM4K5V80FKDD2` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVP0Z1FG5NQ47BQMRGERQX` | `a_01M5BWB906FDRHCE8R6YA91YM6` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5BVRRV9QBVGK63FC13GMZKD` | `a_01M5BWBMSKVP2540FMP9P9HB92` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5C0YY7H2PCG0T8J98X43XZ1` | `a_01M5C11S0C4FTECVXGMY0J3BHG` / a1 / submitted | NULL / NULL（无数据库推送记录） |
| M-15 `t_01M5C124RRX1GDAD2XTRXXB9Z9` | `a_01M5C124ZPCPMDQW5H6MS45D1M` / a1 / submitted | NULL / NULL（无数据库推送记录） |

## 分支 / SHA / 归档逐项对应

| 环境 / mission / attempt | 分支（均在 refs/heads/ 下） | 完整 SHA | 远端 ref | bundle / SHA-256 |
|---|---|---|---|---|
| prod M-1 `a_01M511S4GWWFHB0HPA5F36NPF4` a1 **accepted** | `agent/t_01M511RV9S41AEW9CDA76024Q3/a1` | `a8c886df038fbd71b119c9a1e15dfd9de1cddf76` | 存在 | `bifrost-platform--agent__t_01M511RV9S41AEW9CDA76024Q3__a1.bundle` / `4e16c3d3b732e02a70d7626ea549c94d4cf94bdbdc229a97213b138bc7ffced4` |
| prod M-2 `a_01M51EJ05WGZGTKNWW7WYR9SE6` a1 **accepted** | `agent/t_01M51EHZ92V5F2PRB7JCZVHTQ3/a1` | `d7ce5db6a38245fd9a6f2069d05f4885ccac3757` | 存在 | `bifrost-platform--agent__t_01M51EHZ92V5F2PRB7JCZVHTQ3__a1.bundle` / `3dccefd8f3b3ee0e692a68f7bf0df51ae4442ad17fa6eb97cab12697ee7e83f1` |
| prod M-3 `a_01M55ANAD0BY5929G318XMKJ1K` a1 **accepted** | `agent/t_01M55AN78GPF9V6NFZFS4KJP8N/a1` | `a27c23cf18b1184fce2c3b3e09341b237a0c609c` | 存在 | `bifrost-platform--agent__t_01M55AN78GPF9V6NFZFS4KJP8N__a1.bundle` / `89dc66c93c679441436ae10955f86bd30b6073bb0b676f9fd2e2608dd28207b2` |
| prod M-3 `a_01M55ANB9A6WEB66V4HTMVVC11` a1 **accepted** | `agent/t_01M55AN78M1MX9NF9Q958T96Z3/a1` | `42bb2c9672b94b1178797d062df0e72dd789f200` | 存在 | `bifrost-platform--agent__t_01M55AN78M1MX9NF9Q958T96Z3__a1.bundle` / `b24cd636b498ffe90cb4e14d10533bbc32e66f483bdc78ec858191a95ce899fd` |
| prod M-4 `a_01M56J5RB40TESB4AN7RNXDRQ6` a1 **accepted** | `agent/t_01M56J5QPAAQQP53KV4MQYCW5Q/a1` | `d75de4f31f5a54b4b74de4f53737741970a819f5` | 存在 | `bifrost-platform--agent__t_01M56J5QPAAQQP53KV4MQYCW5Q__a1.bundle` / `87ed79a91a69f636bfbdca5badd9501d496d8a298ddc52cb6ffef98352861b64` |
| prod M-13 `a_01M5BSTSRZR5BKTRPJ63TQMGRG` a1 **accepted** | `agent/t_01M5BSTGPP9FC3PCF4NF5PM7GD/a1` | `247702576212beb040be8d2a0ddd5bf2f6571a9d` | 存在 | `bifrost-platform--agent__t_01M5BSTGPP9FC3PCF4NF5PM7GD__a1.bundle` / `5e644882407c649473c81aa78d830a4353120525b8f930c0fb6e4cde5401fbf5` |
| prod M-15 `a_01M5BV45VGR5QFM2KQPJZA7EC2` a1 **accepted** | `agent/t_01M5BV3W403F0SYH6HF8RAFNJ0/a1` | `003c2f309e7d0f6dcfd749925f5e6a235ee442af` | 存在 | `bifrost-platform--agent__t_01M5BV3W403F0SYH6HF8RAFNJ0__a1.bundle` / `f3ff3e48e8f68cc532f0d63fd2c4d20787b2f8f5c6cf0de88d63377985058c7c` |
| prod M-15 `a_01M5BV6M1PNF9PA5YE2TM8BY8P` a1 **accepted** | `agent/t_01M5BV3W43ETJPVBT55T2XYW30/a1` | `0260d57c65df2ff86f2dec5885785f65e79d8f34` | 存在 | `bifrost-platform--agent__t_01M5BV3W43ETJPVBT55T2XYW30__a1.bundle` / `2effb22f50917513aa99d4b5d6b8f89f6a545a0ea588a22763cf89fb72dab660` |
| prod M-15 `a_01M5BV823FS69FQV6X6FXKSH1V` a1 **accepted** | `agent/t_01M5BV3W45NDSBHBTEFY4RMT97/a1` | `da7d79a49f42a73c2ecedce9e158575ddde30554` | 存在 | `bifrost-platform--agent__t_01M5BV3W45NDSBHBTEFY4RMT97__a1.bundle` / `b104ba3c52bd710ca26a8515d97ca67d1124b20db97979cfdc342baee690012f` |
| prod M-15 `a_01M5BVAM7BP316DGR5951GMG7J` a1 **accepted** | `agent/t_01M5BV3W48B5HGHZB5JJKHE81G/a1` | `be4563eadeaccf041d0d072c6d8b51e977e22735` | 存在 | `bifrost-platform--agent__t_01M5BV3W48B5HGHZB5JJKHE81G__a1.bundle` / `eb5648fd819e1a76c78784e9676f335c9cd57a07cdd50edde6a76094fa880543` |
| stg M-2 `a_01M50M1FDJVG8SDC39N32CKH7E` a1 **accepted** | `agent/t_01M50M1CZSDN8PNHRH8C2241RS/a1` | `f30cdd8a6077ece6248f70706f0562fb84791801` | 存在 | `bifrost-platform--agent__t_01M50M1CZSDN8PNHRH8C2241RS__a1.bundle` / `6766aca9f68c7028a8ae65ec09105e41634eea9f4f5066f47b4fef30460b278b` |
| stg M-2 `a_01M50P92FXWDPR3TWXR8BK1435` a1 额外保全 | `agent/t_01M50P8BGEJWJV767MMT1G16ZP/a1` | `c07d318c0b2d2f0fbba4b01195d4bdb94b3af2b5` | 已不存在；SHA fetch 恢复 | `bifrost-platform--agent__t_01M50P8BGEJWJV767MMT1G16ZP__a1.bundle` / `786fdcc94e858d6c7f311bc8a28f10948b7c7a75d82da80b03a467737cc22c56` |
| stg M-2 `a_01M50PA7YZVF1SCWS0173H1T1S` a2 额外保全 | `agent/t_01M50P8BGEJWJV767MMT1G16ZP/a2` | `667fe2abddb3901f69708ca9084f3879c345cd0b` | 已不存在；SHA fetch 恢复 | `bifrost-platform--agent__t_01M50P8BGEJWJV767MMT1G16ZP__a2.bundle` / `3e934767e2d203e3f09aa8d85022f454b462cd1e5c7068a42229dfe8b87942c6` |
| stg M-16 `a_01M595BJ2XWJ5GSQR4AMV7PA6P` a1 额外保全 | `agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a1` | `00ab399377e0d06d92d98c0987ff39300903e249` | 已不存在；SHA fetch 恢复 | `bifrost-platform--agent__t_01M595BAVBMBJWDV5QWMSWJ4J6__a1.bundle` / `3a4ba51a850c8afbcab74b423291e84b151aa3fe44c34954cd75e7d099724517` |
| stg M-16 `a_01M595CY0ZE9EG9GTDE40E41XX` a2 **accepted** | `agent/t_01M595BAVBMBJWDV5QWMSWJ4J6/a2` | `586a1c029aa3bd4ac95850bbd75dc9cfcec889c1` | 存在 | `bifrost-platform--agent__t_01M595BAVBMBJWDV5QWMSWJ4J6__a2.bundle` / `4d92e8d458d5ea7eb688244ac780f91f19086c402676b98d02f411a07c143659` |
| stg M-23 `a_01M5B37K81CZ9TRQ710SNERPZ3` a1 **accepted** | `agent/t_01M5B37AYBAHQTM6RMQZZHE3AT/a1` | `f4d19631ba58a0e03af5c45f394aff10268dabdc` | 存在 | `bifrost-platform--agent__t_01M5B37AYBAHQTM6RMQZZHE3AT__a1.bundle` / `7df14942f953118d4219b95b9d17794880ab0370b1ddb9d91484f5dc62e8e3eb` |
| stg M-24 `a_01M5B6KMED2TQVWSM7XNF6DW2N` a1 **accepted** | `agent/t_01M5B6KKPMM15HZB4BC0ZWVJ5R/a1` | `9da7881ed6c017f73d244cb20e934aef07f38397` | 存在 | `bifrost-platform--agent__t_01M5B6KKPMM15HZB4BC0ZWVJ5R__a1.bundle` / `afe39b58de6e595fc4b370017bf2cabcba0b074a7db6b9e56097f529ca14144a` |
| stg M-26 `a_01M5BSBSNMF0CPD13A3KPGZ80D` a1 **accepted** | `agent/t_01M5BSBEZ7J3BQM0EV7SG3NB2N/a1` | `cecf2c7bee55b326c0885e5392b63dc55346733f` | 存在 | `bifrost-platform--agent__t_01M5BSBEZ7J3BQM0EV7SG3NB2N__a1.bundle` / `eb6d56355591cfdda78d3e3e28676a679b314ed38dc8f984d7b1d4726fc9ab53` |
| stg M-27 `a_01M5BSPXNQ4ZHGGX7FWE6D7543` a1 **accepted** | `agent/t_01M5BSPFV3S9ET52X3JT76HJFS/a1` | `e56d0c906c89b62a205df7ad6a1784abeda61588` | 存在 | `bifrost-platform--agent__t_01M5BSPFV3S9ET52X3JT76HJFS__a1.bundle` / `0a6fcfce2d48e745e6e5bfadf37e0e5038f73cc4d43f505fc39d6e480021be03` |
| stg M-27 `a_01M5BSRVB127GEYXY98K3Y2DNR` a1 **accepted** | `agent/t_01M5BSPFV8JBH908TR6M58S6Q9/a1` | `7a0a121c65cd56863ff24d218b0d6bee982a525f` | 存在 | `bifrost-platform--agent__t_01M5BSPFV8JBH908TR6M58S6Q9__a1.bundle` / `1dd8b7440e5c967aeeacf753468c7fc33bef7679dd54f5950325f569004fca3e` |
| stg M-27 `a_01M5BSTC7SHPNNQ7ZP73PFGJS4` a1 额外保全 | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a1` | `c073b353526fd69fe054486452b1e8af3109b0fd` | 存在 | `bifrost-platform--agent__t_01M5BSPFVBXYBAQYADX2KPVF1X__a1.bundle` / `107881226aefcecff5ad87456498954c8d2860ed64f7f8c83b997221f54e14ef` |
| stg M-27 `a_01M5BSW6X1K7QVX47Y2V04FG7R` a2 **accepted** | `agent/t_01M5BSPFVBXYBAQYADX2KPVF1X/a2` | `a5c3c28d972fa989fb843a6ea2bafdfb9c9eb49e` | 存在 | `bifrost-platform--agent__t_01M5BSPFVBXYBAQYADX2KPVF1X__a2.bundle` / `2e165c1b9413bc3877685697cd5da1c04484cfc41fd7ea77790f7e0ae7a6ecd8` |
| stg M-27 `a_01M5BSYM56ZY324FK8KVWKJ1XX` a1 **accepted** | `agent/t_01M5BSPFVDY1N34EGQ5THXYMMD/a1` | `839825bc6ba660ca0d2390410d88eb1aec90e386` | 存在 | `bifrost-platform--agent__t_01M5BSPFVDY1N34EGQ5THXYMMD__a1.bundle` / `aa503100df0ce235820a7b41f42dc8d9672c452912a7d87697938756d46fa29d` |
| prod M-15 `a_01M5BVCSQSW1H3RPH8CMGTC3RY` a1 额外保全 | `agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a1` | `96d023703f439ae647948e94e3fe22028d356462` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4AHSAB5XXNJWT3FWJD__a1.bundle` / `d1a17fdf1f34db7606998e8520d0e6f7c08671de134837ed41104c506c112b5d` |
| prod M-15 `a_01M5BVKV7FX0STKXV8DBQHJA2G` a2 额外保全 | `agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a2` | `7cf9f2c94f17da0a761c286a4e2a3605a809f2ca` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4AHSAB5XXNJWT3FWJD__a2.bundle` / `58161b62e7e54eea46d25c402c7a7ab664ef5efc8670e6b0a02e7bb7e1564642` |
| prod M-15 `a_01M5C0VS6GRQR13QRDHY6GQ6XV` a3 额外保全 | `agent/t_01M5BV3W4AHSAB5XXNJWT3FWJD/a3` | `d85abcce213529ed9b9d7e55ae9ac16cec8640c4` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4AHSAB5XXNJWT3FWJD__a3.bundle` / `574a707721fcb69d4dd794b556911a1efca36c12acc9c81eb62cbfc88595557b` |
| prod M-15 `a_01M5BVF24WSAX2N1ZC5T24K3WH` a1 额外保全 | `agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a1` | `222ed9792413f56eb10efa2859e2c9a6b0887555` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4CCAPD00XXEB4PKYJY__a1.bundle` / `1b6bbf808eda941795074b2fc893003fb162db827ce19e56e1bcd7b73b7fb7aa` |
| prod M-15 `a_01M5BVNVSGT9DSRRSSC61X0M16` a2 额外保全 | `agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a2` | `056abcdfb35747b52c7d4f948f4cebfc736555a0` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4CCAPD00XXEB4PKYJY__a2.bundle` / `22bc6ec25063cc63a78e02a863f2bc0dbc727d177b7e2a0594193138bfdc795a` |
| prod M-15 `a_01M5C0YS4SNZGTHJVT1836B51Z` a3 额外保全 | `agent/t_01M5BV3W4CCAPD00XXEB4PKYJY/a3` | `becfcab138be358ea3091e82c321ce0c704e0fdd` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BV3W4CCAPD00XXEB4PKYJY__a3.bundle` / `f9c026faadb5d4c8428e0f7690ffc731bc4ea8f0d87c5363e16cfc9b19e2dece` |
| stg M-27 `a_01M5BT0TN4V6HHSKXPQ2C9GXXW` a1 额外保全 | `agent/t_01M5BSPFVFY0MY6J7NABB6SR5C/a1` | `782e146c096565207c1c204749816de0a697228a` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BSPFVFY0MY6J7NABB6SR5C__a1.bundle` / `b2283f47136f01207da165463c6beae6a5293309cab0f2a01b2a932b4e53a7e6` |
| stg M-27 `a_01M5BT8KSD0BKXPY8PGPGKESKD` a2 额外保全 | `agent/t_01M5BSPFVFY0MY6J7NABB6SR5C/a2` | `7d062cdb0a5828a27e0a40b1cab0f478328f176d` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BSPFVFY0MY6J7NABB6SR5C__a2.bundle` / `c4da6c65ee073cbd628bdbeafc202d416a023ac6c47756f42a599a036a28abfa` |
| stg M-27 `a_01M5BT3DS8A1TJP4ZTTMDEM0P8` a1 额外保全 | `agent/t_01M5BSPFVJZFBAZ2XES6GPFTTM/a1` | `d01ddf8d6438c5a2c9e1918e35b00231b528c4a3` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BSPFVJZFBAZ2XES6GPFTTM__a1.bundle` / `2a37b9bb1ea86d97716e5c9036e4d8311b09f6d1f6201b872e322acaf3c9423a` |
| stg M-27 `a_01M5BTBQFTHK8RGGX0R8MTS6G6` a2 额外保全 | `agent/t_01M5BSPFVJZFBAZ2XES6GPFTTM/a2` | `cf95d341823acb5a149e20dac4f47af18575582f` | 已不存在；SHA fetch 恢复 | `bifrost-trade-infra--agent__t_01M5BSPFVJZFBAZ2XES6GPFTTM__a2.bundle` / `d74d0f24d17fd70e9cb6032cb5d3749cc83d7f91b601ab16a779c9c7a2f38eeb` |
| stg M-103 `a_01M5G4WE3FA4EFXYAGK8BHCZ92` a1 **accepted** | `agent/t_01M5G4W33CRXXVX4C7GJTCJ3VR/a1` | `393f1608729e42524a96a040b02d75ef166e2275` | 存在 | `bifrost-trade-infra--agent__t_01M5G4W33CRXXVX4C7GJTCJ3VR__a1.bundle` / `906878de68a055045e40a3e1927d46d4979ddeee41f270eace920682e3cf12a3` |

以上每份均 `git bundle verify`、独立空 bare 仓 fetch、rev-parse 与完整 SHA 相等、`git fsck --full --no-reflogs` PASS。完整路径是页首归档根目录加 bundle 文件名。

## 统筹将提交的 request_action 参数

先复核此证据及两个 JSON，按 **STG 后 PROD、分两张 D 级单**提交；参数文件是完整工具入参，不是占位符。本片没有调用 request_action。

- `d-l5-2026-10-25/stg-request-action.json` → action=owner_run_command、runner=owner、7 missions。
- `d-l5-2026-10-25/prod-request-action.json` → action=owner_run_command、runner=owner、6 missions。

Owner 在 Console 批准后，由正常 Owner executor 领取、执行已签 command 并上报退出码和输出；不能直接复制 SQL 跳过审批。runner=owner 不会让平台自行运行管理员命令。此命令要求 Owner 在存有本地归档的 Mac 执行；它先校验清单固定 SHA 和全部文件，再从每个 bundle 空仓读回，最后执行内嵌 SQL。旁边的 .sql 只是复核副本，执行不读可被修改的外部 SQL。

两环境不是一个分布式事务；一张失败则保留其失败事件，重新读取并重建该张参数。每张命令以 mission/task/attempt/verification 的只读快照指纹、完整旧 scope 和 version 拒绝漂移；事务将 version 增一，不改任务状态/accepted/landed。MD5 仅作并发快照比较，归档真实性由 SHA-256 与审批签名固定。

批准/执行事件由现有审批链保留，结果包含每个 mission 的新 version/no_merge。没有伪造 agentrt.event 的哈希链事件。执行后统筹用 agent_reader 单独读回同一精确集合，并关联后续 agentd 清理日志与这两张审批号；单号尚不存在，不能预填。

回退：未执行可取消。执行后必须另建版本约束更正单，不能直接清空理由；版本预期为本单旧 version+1 且 no_merge 等于本单新理由。若 agentd 已清理分支，须由 Owner 从本单 SHA-256 锁定的 bundle 恢复确切 ref/SHA；清空 no_merge 不会恢复分支。保留原审批、执行事件和读回输出。

END OF EVIDENCE

## Owner 2026-10-25：M-1、M-2、M-4 取回

PROD M-1、M-2、M-4 是 Owner 自己的注释工作，不是演练；内容已作为新提交从 platform w31/dl5-comments 取回，并由 Owner 于 2026-10-25 推至 platform main：93399f27（M-4）、ce5d2c30（M-1）、ca4f8149（M-2）。这三个 mission 保留 no_merge，仅表示原尝试不合入；原始对象归档保留。5 个 cancelled 实现任务核对：4 个是基准题回放，原修复已在 infra main（Q12 = `67fda99`，Q20 = `4a59032`）；1 个是故意失败的实验（STG M-2 T06）。都没有要保留的工作。
