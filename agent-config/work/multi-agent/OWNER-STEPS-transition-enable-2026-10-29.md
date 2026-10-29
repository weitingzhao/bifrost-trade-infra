# 过渡期结束 C-7 后半：启用与实测 · Owner 操作单（2026-10-29，统筹已审；按 Owner 选 A 修订：api 不挂落地身份）

依据：`DESIGN-coordinator-landing-v3-2026-10-29.md` §2.1–§2.5、§5.6、§7.3、§9（C-7）、§12；`CUT-landing-2026-10-24.md` §11.14、§11.15。
现状（2026-10-29 13:47 CDT 读库核对）：核心块已在 PROD 与 STG 运行 platform `efac01e5`，迁移 0010 已在两边（`agentrt.task.executor_pin` 列存在）。所有新能力都关着：两边都**没有** `seat:coordinator`、没有 `coordinator-mbp` 主机；PROD 生效的 `standing-envelope:dev` 是 **v4（tighten，未签名）**，STG 是 v5（已签）；两边 `landing:dev` 都是 v1（`max_landings_per_day: 5`）。

**你要动手的共 13 件**：推 infra main 2 次（S2、P2）；签规则 4 次（S4、S5、P4、P8）；终端跑令牌脚本 2 次（S1、P1）；在 Console 批 D 级单 3 张、撤销 1 次（P6 两张加一次撤销、P7 一张）；P7 批之前在 Gitea 自己看一次 diff。
统筹每次只给你一步；你跑完回一句「跑完了」，统筹读输出文件核对后再给下一步。终端命令都能原样运行，输出写进 `/tmp/c7-*.txt`。
**顺序原则**：先 STG 完整走一遍（STG 不建授权单，授权是 PROD 专属，见 §6 事实 F12），STG 通过后 PROD 重复并做四件实测。任何一步不对就停，按 §5 回退。

---

## 第 0 步 · 统筹：准备 infra 改动（不需要你）

统筹在 infra 分支 `w31/infra-int` 上准备下列改动（完整内容见 §3），本机自检通过后分成两个提交：

- **提交 #1（STG 段）**：§3 的 A（新脚本 `put-coordinator-tokens.sh` 与测试）、B（`handin.sh` 两处补充与测试）、C（四份规则 YAML）、D（STG overlay 两个文件）、本操作单。
- **提交 #2（PROD 段）**：§3 的 E（PROD overlay 三个文件与 kustomization 一行）。

自检：`bash -n` 与两个脚本的测试；`kubectl kustomize k8s/overlays/platform-stg`、`kubectl kustomize k8s/overlays/platform-prod` 渲染成功，diff 只多出 §3 列的条目（统筹 2026-10-29 已在副本上渲染过这份内容，见 §6 F15）；四份规则用平台的解析器读过（§6 F14）。
**不要**跑 `scripts/sync_platform_k8s_config.sh`：它会用 platform 仓库的 `config/platform-auth.yaml` 覆盖 STG overlay 的同名文件，把 `agentd:agent-06-stg` 和本次新增的两条一起冲掉。

---

## 一、STG 演练

### S1 · 你：生成 STG 的两个统筹令牌（终端）

**在哪**：本机终端面板（要用你的管理员 kubeconfig `~/.bifrost-owner/kube/admin.yaml`；Agent 的 kubeconfig 只读，写不了 Secret）。
**做什么**：脚本在本机随机生成两个令牌（不需要你输入、不显示），写进 STG 命名空间 Secret `bifrost-platform-role-tokens` 的两个新键，再写两个本机文件（600）。它不碰 Secret 里其他键。

```bash
cd /Users/vision-mac-trader/agent-work/night-1028/infra && bash scripts/agentrt/put-coordinator-tokens.sh stg > /tmp/c7-stg-tokens.txt 2>&1
```

**看什么**：输出只有键名与文件路径——`PLATFORM_SEAT_COORDINATOR_STG_TOKEN`、`PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN` 都在 Secret 里读回，`~/.config/bifrost/coordinator-proposer-stg.token`、`coordinator-agentd-stg.token` 已写；退出码 0。
**失败就停**：脚本先做 server dry-run，失败时什么都没写；输出里有 `refused` 或退出码非 0，回线程说，不要重跑带 `replace`。

### S2 · 你：推 infra main（提交 #1）

**在哪**：本机终端，用你自己的 Gitea 账号输口令（格式同 S3 操作单第 1 步）。命令由统筹在这一步给（提交号此时才有）。推之前统筹先跑 `release.sh window` 确认没有窗口，并确认该提交的 CI 已 Succeeded。
**会发生什么**：Argo 自动同步 `bifrost-platform-stg`（automated + prune + selfHeal）：STG `platform-api` 因环境变量变化重启一次（Recreate，短暂不可用），读到两个新令牌，启动时把 `seat:coordinator` 登记进 STG 运行时库（`store.EnsureSeats`）。PROD 不受影响：提交 #1 不含 PROD overlay，规则文件不签就不生效。

### S3 · 统筹：核对 STG（不需要你）

1. STG `platform-api` 新 Pod 跑的仍是 `efac01e5`，日志有 `agentrt: seats registered` `[seat:coordinator]`。
2. 读库（`agent_reader`，`bifrost_platform_stg`）：`agentrt.actor` 有 `seat:coordinator`（kind `seat`）。
3. 只读解析两份 STG 规则：`rule.sh check …/stg/standing-envelope-dev.yaml --env stg` 应读成第 6 版、`loosen`、需要签名；`…/stg/landing-dev.yaml` 读成第 2 版、`loosen`。
   第 1 条不过（种子没登记）时，信封检查会报 `its proposer seat:coordinator is not a registered seat`——这就是先装令牌、后签信封的原因。

### S4 · 你：签 STG 信封 v6（终端）

**在哪**：本机终端面板（用你的签名私钥，会问口令或 Touch ID；STG 也要你的私钥：平台只认编译进去的你那把钥匙的指纹，STG 与 PROD 同一个二进制）。
**做什么**：`standing-envelope:dev` 第 6 版：在 v5 基础上 `hosts` 加 `coordinator-mbp`，新增 `external_hosts` 一段（统筹的 Mac 只能领被钉给它的 `bifrost-platform` 实现任务，提议者只能是 `seat:coordinator`，执行者 `exec:claude`/`anthropic`）。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1028/infra/agent-config/agentrt-rules/stg/standing-envelope-dev.yaml --env stg > /tmp/c7-stg-sign-envelope.txt 2>&1
```

**看什么**：输出里平台先读回（`standing-envelope:dev`、`rule_version 6`），再显示签名已收下；退出码 0。
**会发生什么**：STG 上 `seat:coordinator` 从此能提议钉给 `coordinator-mbp` 的任务；STG 的授权单仍然不存在（PROD 专属）。

### S5 · 你：签 STG 落地规则 v2（终端）

**做什么**：`landing:dev` 第 2 版，只把 `max_landings_per_day` 从 5 改成 12（CUT §11.15 的建议），其余与 v1 相同，到期日不变（2026-11-26）。STG 先签一遍，验证这份文件能签、能读。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1028/infra/agent-config/agentrt-rules/stg/landing-dev.yaml --env stg > /tmp/c7-stg-sign-landing.txt 2>&1
```

**看什么**：读回 `landing:dev`、`rule_version 2`、签名已收下；退出码 0。

### S6 · 统筹：STG 实测（不需要你）

统筹用 STG 的令牌文件跑 `handin.sh`（`PLATFORM_AGENTRT_URL=http://192.168.10.73:30878`，`HANDIN_AGENTD_TOKEN_FILE` / `HANDIN_PROPOSER_TOKEN_FILE` 指向两个 `-stg` 文件），推送身份是本机 Gitea 账号 `bifrost-mbp`（`--remote origin`）。

| # | 造什么 | 期望 |
|---|---|---|
| S6-a | 经 STG MCP 提一个目标（repo `bifrost-platform`，信封内，立即 active）；`handin.sh propose` 提一件钉住的任务；隔离分支上做一个**规则内**改动（只改 `console/src/pages/**/*.tsx`，纯展示，≤10 文件 ≤300 行），`handin.sh squash`、`handin.sh run` | `claim/pinned` 返回 `a1` 与 `agent/<task>/a1`；STG 库里出现主机 `coordinator-mbp`，`host_kind = external`；验收（agent-06-stg 跑 Verify）与 Codex 评审通过、任务 accepted；STG 演练循环照常：推 `land/stg/<task>/1`、CI、dry-run 结论；STG main 不动 |
| S6-b | 同上，但改动只碰软底线（例如 `api/internal/research/` 下一个测试文件） | 演练里 `MayAwaitGrant` 在 STG 恒为假：根直接 `failed{floor}`，**没有** `awaiting_grant`、没有单；STG 的自动回答规则处理可能出现的卡 |
| S6-c | 反例：`HANDIN_PROPOSER_TOKEN_FILE` 指向 agentd 那个文件再跑一次 `propose` | 403，零任务 |

**通过**：三项都如期，`handin.sh` 全程无需人工补救（读回、续租正常）。统筹在线程里报结果和用时，然后给你 P1。
**不通过**：统筹交一个收紧（§5 第 1 级，免签），STG 立即停止新钉与领取；往前修，再从 S6 重来。

---

## 二、PROD 启用与实测

### P1 · 你：生成 PROD 的两个统筹令牌（终端）

```bash
cd /Users/vision-mac-trader/agent-work/night-1028/infra && bash scripts/agentrt/put-coordinator-tokens.sh prod > /tmp/c7-prod-tokens.txt 2>&1
```

**看什么**：`PLATFORM_PROD_SEAT_COORDINATOR_TOKEN`、`PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN` 在 PROD 的 Secret 里读回；本机写了 `~/.config/bifrost/coordinator-proposer.token`、`coordinator-agentd.token`（`handin.sh` 的默认路径）；退出码 0。值与 STG 不同（各自随机生成）。

### P2 · 你：推 infra main（提交 #2）

命令由统筹在这一步给。推之前统筹再查一次发布窗口和该提交的 CI。
**会发生什么**：Argo 自动同步 `bifrost-platform-prod`：PROD `platform-api` 重启一次（Recreate，两个副本一起换，约一分钟不可用），读到两个令牌、登记 `seat:coordinator`（授权材料、建单校验、审批执行器在 api 进程里用已挂的只读 Gitea 读者读 Git；落地身份只在 workers，Owner 2026-10-29 选 A）。`platform-workers` 不变，live 照旧开着。此时仍没有任何新能力打开：信封没签，钉不了、领不了、建不了授权单。

### P3 · 统筹：核对 PROD（不需要你）

1. PROD `platform-api` 两个 Pod 跑 `efac01e5`，旧 ReplicaSet 为 0；日志有 `seats registered`；读库 `bifrost_platform` 有 `seat:coordinator`。
2. `/health` 的 `landing` 段照旧（`live: true`、卡能力五项）。
3. 只读解析 `…/prod/standing-envelope-dev.yaml --env prod`：第 5 版、`loosen`（上一版 v4 是未签的收紧）、需要签名。

### P4 · 你：签 PROD 信封 v5（终端）

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1028/infra/agent-config/agentrt-rules/prod/standing-envelope-dev.yaml --env prod > /tmp/c7-prod-sign-envelope.txt 2>&1
```

**看什么**：读回 `standing-envelope:dev`、`rule_version 5`、签名已收下；退出码 0。
**会发生什么**（签了立即生效）：
- 统筹能用 `seat:coordinator` 提钉住的任务、用 `coordinator-mbp` 精确领取、`handin.sh` 交付。
- 授权通道打开（`GrantEnabled`）：钉住任务碰软底线 → `awaiting_grant`，等统筹建 D 级单；**agent-06 跑的普通运行时任务**如果碰到 `hard_core`，也不再直接 `failed{floor}`，而是进入等待、可由核心级单放行（设计 §12.3 末条）——没人建单时最多等 72 小时后 `failed{approval_expired}`，发一张可「再试一次」的卡。

### P5 · 统筹：实测 1 · 规则内一件（不需要你）

见 §4 实测 1。通过标准：不建单，`landed`，main 上的提交带 `Landed-By: agentrt-prod/land:<task>:1`。

### P6 · 你 + 统筹：实测 2 · 软底线单一件，含撤销一次

见 §4 实测 2。你要做三件事，统筹每次给链接：
1. **Console 批第一张单 #A**（ops.bifrost.lan → 审批，动作 `approve_guardrail_landing`，D 级、要确认单号）。批之前统筹已持住发布窗口，所以批了不会马上推。
2. **撤销**：打开统筹给的授权页（`ops.bifrost.lan/#landing-grant?op=…&stg_release=false`），点 `Revoke grant #<单号>`。页面应显示 Revoked。
3. 统筹放开窗口、重建第二张单 #B；**你批 #B**。之后统筹盯到 `landed`。

### P7 · 你 + 统筹：实测 3 · 核心级单一件

见 §4 实测 3。你要做两件事：
1. 单上点 `Compare M0...R in Gitea`，在 **Gitea 自己的页面**看一遍 diff（这页不经平台代码渲染）。若单上写 `Decision chain: true`，页面要求勾选 `I checked this in Gitea` 才能批。
2. **Console 批这张 `approve_core_landing` 单**。

### P8 · 你：签 PROD 落地规则 v2（终端）

前三件实测都过了再签（实测只用 3 次落地，5 次额度够；先签反而让一个没验完的通道拿到更多额度）。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/agent-work/night-1028/infra/agent-config/agentrt-rules/prod/landing-dev.yaml --env prod > /tmp/c7-prod-sign-landing.txt 2>&1
```

**看什么**：读回 `landing:dev`、`rule_version 2`、`max_landings_per_day 12`；退出码 0。全租户每日总额度从此是 12（运行时与统筹共用一份）。

### P9 · 统筹：收尾（不需要你）

CUT 加 §11.16 启用记录（时间线、四件实测的单号与提交号、意外）；第一次真实拒推若出现，补进 `TestClassifyPush`；`LESSONS-from-practice.md` 记卡点；四份规则 YAML 与本操作单随下一次 infra 提交入库（`rule.sh` 留下的 `*.sig` 不入库，签名已存进平台库）。从此统筹的 platform 提交走 `handin.sh`，你不再手推 platform main（`hard_absolute`、紧急修复、混合来源三种例外照旧）。

---

## 三、infra 改动清单

| # | 文件 | 内容 | 部署方式 |
|---|---|---|---|
| A1 | `scripts/agentrt/put-coordinator-tokens.sh`（新） | 见下「A 的规格」 | 不部署；你在 S1/P1 从 night-1028 检出运行 |
| A2 | `scripts/agentrt/test_put_coordinator_tokens.sh`（新） | 假 `kubectl`/`openssl`：不回显值、值不进 argv、已存在拒绝、dry-run 失败零写入、只打印键名 | 不部署 |
| B1 | `agent-config/scripts/landing/handin.sh` | 加 `material --op land:… [--stg-release false]`；`run` 的 claim 失败时打印服务端 `error`/`message`（现在只报 HTTP 码，`no_lease` 的原因看不到） | 不部署；统筹本机用 |
| B2 | `agent-config/scripts/landing/test_handin.sh` | 补上两处的用例 | 不部署 |
| C1 | `agent-config/agentrt-rules/stg/standing-envelope-dev.yaml` | v6，全文见下 | 不同步；S4 签名后生效 |
| C2 | `agent-config/agentrt-rules/stg/landing-dev.yaml` | v2，全文见下 | S5 签名后生效 |
| C3 | `agent-config/agentrt-rules/prod/standing-envelope-dev.yaml` | v5，全文见下 | P4 签名后生效 |
| C4 | `agent-config/agentrt-rules/prod/landing-dev.yaml` | v2，全文见下 | P8 签名后生效 |
| D1 | `k8s/overlays/platform-stg/config/platform-auth.yaml` | 末尾加两条令牌 | Argo 自动（`bifrost-platform-stg`） |
| D2 | `k8s/overlays/platform-stg/platform-api-role-tokens.patch.yaml` | `env` 末尾加两项 | Argo 自动；STG `platform-api` 重启 |
| E1 | `k8s/overlays/platform-prod/config/platform-auth.yaml` | 末尾加两条令牌 | Argo 自动（`bifrost-platform-prod`） |
| E2 | `k8s/overlays/platform-prod/platform-api-role-tokens.patch.yaml` | `env` 末尾加两项 | Argo 自动；PROD `platform-api` 重启 |
| E3 | （删除）api 进程不挂落地身份 | Owner 2026-10-29 选 A：platform `2150b99c` 让授权链用只读的 Gitea 读者（`GITEA_READER_DIR`，api 已挂），落地身份只留在 workers | — |

平台仓库（`bifrost-platform`）**不需要改**：`config/platform-auth.yaml` 只给本机开发用，集群读 infra overlay 的副本。

### A 的规格：`put-coordinator-tokens.sh stg|prod [replace]`

| | stg | prod |
|---|---|---|
| 命名空间 / Secret | `bifrost-platform-stg` / `bifrost-platform-role-tokens` | `bifrost-platform-prod` / `bifrost-platform-role-tokens` |
| 提议令牌键 | `PLATFORM_SEAT_COORDINATOR_STG_TOKEN` | `PLATFORM_PROD_SEAT_COORDINATOR_TOKEN` |
| 执行令牌键 | `PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN` | `PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN` |
| 本机文件 | `~/.config/bifrost/coordinator-proposer-stg.token`、`coordinator-agentd-stg.token` | `~/.config/bifrost/coordinator-proposer.token`、`coordinator-agentd.token` |

- 开头拒绝 xtrace（同 `handin.sh` 开头）、`umask 077`；KUBECONFIG 的取法与 `put-reader-token.sh` 完全相同（复用它的那一行，本单不重复写路径）。
- 两个值各用 `openssl rand -hex 32` 生成，只在 shell 变量里，不进 argv、不回显（与 agent-06 令牌同形：64 位十六进制）。
- 没带 `replace` 时：本机文件已存在、或 Secret 里已有同名键（只用 `python3 -I` 打印键名来查，绝不输出 `.data`）→ 拒绝，零写入。
- 写 Secret：`python3 -I` 从 stdin 读值，生成 `{"stringData": {...}}` 到 600 临时文件；先 `kubectl patch … --type merge --patch-file … --dry-run=server`，过了再正式 patch（同 `agent-06-owner.sh` `step_secret`）；随后读回、只打印键名，确认两键都在。
- 再写本机文件（属主本人、600、拒绝符号链接；`handin.sh` 会核对这三条），最后只打印键名与文件路径。

### B1 的规格：`handin.sh material`

`GET /agentrt/landing/{op}/material?stg_release=<true|false>`（执行令牌即可，`read` 能力含 agentd）。打印：`material.action`（`approve_guardrail_landing` 或 `approve_core_landing`）、`problems`（非空就不建单）、`main_is_M0`、`soft_at_request`、`hard_core_paths`、`decision_chain`、`trust_review`，以及可原样交给 `request_action` 的参数 `{env:"prod", repo, task, op, R, material_digest, stg_release}`。

### C · 四份规则全文（统筹 2026-10-29 用平台解析器读过，§6 F14）

`agent-config/agentrt-rules/stg/standing-envelope-dev.yaml`：

```yaml
rule_id: standing-envelope:dev
rule_version: 6
direction: loosen
effective_at: 2026-10-29T00:00:00Z
expires_at: 2027-01-15T00:00:00Z
tenant: dev
max_action: branch
budget:
  max_attempts: 40
  max_wall_hours: 48
executors: [exec:claude, exec:codex, exec:cursor, exec:deterministic]
hosts: [agent-06-stg, coordinator-mbp]
external_hosts:
  - host: coordinator-mbp
    pin: external:coordinator
    proposer: seat:coordinator
    executor: exec:claude
    provider: anthropic
    repos: [bifrost-platform]
    roles: [implement]
```

`agent-config/agentrt-rules/prod/standing-envelope-dev.yaml`：与上相同，只改两行——`rule_version: 5`，`hosts: [agent-06, coordinator-mbp]`。

`hosts` 里必须有 `coordinator-mbp`：信封内的目标，其任务只在信封列出的主机上领（`store/envelope.go:117–129`，领取时 `claim.go:243` 调用）；只写 `external_hosts` 不写 `hosts`，`claim/pinned` 会以 `no_lease`（「names neither this host nor its executor」）拒绝。设计 §2.1 的片段没写这一点。

`agent-config/agentrt-rules/stg/landing-dev.yaml`：

```yaml
rule_id: landing:dev
rule_version: 2
direction: loosen
effective_at: 2026-10-29T00:00:00Z
expires_at: 2026-11-26T00:00:00Z
tenant: dev
repos:
  - repo: bifrost-platform
    allow: ["console/src/components/**/*.tsx", "console/src/components/**/*.css", "console/src/pages/**/*.tsx", "console/src/styles/**/*.css"]
    deny: []
    stg_release: none
limits:
  max_files: 10
  max_changed_lines: 300
  max_landings_per_day: 12
  max_in_flight_per_repo: 1
```

`agent-config/agentrt-rules/prod/landing-dev.yaml`：与上相同，只改 `expires_at: 2026-11-28T00:00:00Z`（保持 v1 的到期日）。

签名前统筹再用 `rule.sh show` 核对在用版本仍是 STG 信封 v5 / PROD 信封 v4 / 两边落地 v1；若有人先签了新版，改号后再给你。

### D · STG overlay

`k8s/overlays/platform-stg/config/platform-auth.yaml` 末尾追加：

```yaml
  # W-31 round 4 C-7 (DESIGN-coordinator-landing-v3 §2.1): the coordinator's
  # proposer seat (the only writer allowed to pin a task, once the signed
  # envelope names it) and its Mac's agentd principal (exact claim only).
  - name: seat:coordinator
    role: reporter
    token_env: PLATFORM_SEAT_COORDINATOR_STG_TOKEN
  - name: agentd:coordinator-mbp
    role: agentd
    token_env: PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN
```

`k8s/overlays/platform-stg/platform-api-role-tokens.patch.yaml` 的 `env:` 末尾追加：

```yaml
            - name: PLATFORM_SEAT_COORDINATOR_STG_TOKEN
              valueFrom:
                secretKeyRef:
                  name: bifrost-platform-role-tokens
                  key: PLATFORM_SEAT_COORDINATOR_STG_TOKEN
                  optional: true
            - name: PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN
              valueFrom:
                secretKeyRef:
                  name: bifrost-platform-role-tokens
                  key: PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN
                  optional: true
```

### E · PROD overlay

`k8s/overlays/platform-prod/config/platform-auth.yaml` 末尾追加（与 D 相同，`token_env` 换成 `PLATFORM_PROD_SEAT_COORDINATOR_TOKEN`、`PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN`）。
`k8s/overlays/platform-prod/platform-api-role-tokens.patch.yaml` 的 `env:` 末尾追加两项（同 D 的形状，键名换成上面两个 PROD 键）。

（原拟的 `platform-api-landing-grant.patch.yaml` 已取消：Owner 2026-10-29 选 A，授权链在 api 进程里用只读的 Gitea 读者读 Git，见 platform `2150b99c`。）

**不需要改**：RBAC（api 与 workers 同用 ServiceAccount `bifrost-platform`，`bifrost-platform-observer` 已含 `tekton.dev pipelineruns get/list/watch`，`k8s/platform-rbac/00-clusterroles.yaml:57–59`；workers 现在就用它读落地 CI）；Gitea 读者（api 已挂 `bifrost-gitea-reader`，`agentRuntimeMains` 读 main 头用它）；`AGENTRT_ENV=prod`（api 已有）。

---

## 四、实测清单（C-7 设计 §9：规则内一件、软底线单一件、核心级单一件、撤销一次）

通用做法：统筹在**独立 worktree** 的隔离分支上写改动（不碰共享检出）；目标经 PROD MCP 提（repo `bifrost-platform`，信封内 → 立即 active）；`handin.sh propose`（碰 `api/internal/agentrt`、`api/internal/agentd`、`api/cmd/agentd` 时带 `--core`）→ `handin.sh squash` → `handin.sh run --remote origin`。改动都用**真实排队的小修**，不造假改动（它们会真的上 main）；候选：§11.12 的 N-02（文案）、R-08/R-09（Console 读取逻辑）、R-05（`store` 的 ABA 核对）——按实际 diff 分到下面三类。
测试期间请你**不要手推 platform main**；运行时（agent-06）的落地也会让 main 前进，统筹在请你批单前看 `main_is_M0`，过时就 `handin.sh refresh` 重建单。
看哪里：目标详情的 Landing 块、`/health` 的 `landing` 段、`handin.sh status --task … --op …`、读库 `landing:bifrost-platform` 流的 `note` 事件（`landing_grant`、`landing_grant_revoked`、`landing_grant_request`）与 `main_intent` 事件的 `landing_grant_use` 段。

### 实测 1 · 规则内（P5）

- **造**：只改 `console/src/pages/**/*.tsx` 的纯展示（不 import `api/`、`lib/`、`hooks/`，不 `fetch`），≤10 文件、≤300 行。
- **看**：`claim/pinned` → `a1`；PROD 库主机 `coordinator-mbp` 为 `external`；验收、Codex 评审（路由固定 `exec:codex`）通过 → 领取 `land:<task>:1` → 推 `land/prod/<task>/1` → CI 绿 → 第二道闸 `main_intent`（**不带** `landing_grant_use`）→ 推 main → `landed`；目标按落地证据关 done。不出现 `awaiting_grant`，不建单。

### 实测 2 · 软底线 + 撤销（P6）

- **造**：只碰软底线、不碰 hard 的路径（例如 `api/internal/research/` 下的文件，或 `console/src/lib/**` 中不在 §4.2 C 表的文件）。
- **过程**：
  1. 落地准备、CI 绿后，第二道闸写 `awaiting_grant`（`soft` 列出 `floor_soft`/`rule_paths` 等），不预留额度；目标详情显示「等统筹建 D 级单（op 1）」，不进你的待办。
  2. 统筹 `handin.sh material --op land:<task>:1 --stg-release false`：`problems` 为空、`action = approve_guardrail_landing`、`main_is_M0 = true`；然后 `release.sh hold --what bifrost-platform` 持住发布窗口（第二道闸在窗口开着时不推，`landingci/window.go:32`），再用 `request_action` 建单 #A。
  3. 你批 #A → 流里出现 `landing_grant`（`grant_id = lg_<approval_id>`、`expires_at` = 批准时刻 + 24 h）；授权页显示「已授权，等推送」；因窗口持住，**零推送**。
  4. 你在授权页撤销 → 流里出现 `landing_grant_revoked`；操作仍是 `awaiting_grant`；授权页显示 Revoked。
  5. 统筹放开窗口，等一轮：**不推**（grant 已撤销），状态回到「等统筹建 D 级单」。
  6. 统筹重读材料、建单 #B（#A 已执行结束，不算未结单）→ 你批 #B → 下一轮第二道闸写 `main_intent` 带 `landing_grant_use{grant_id = lg_<B 的 id>}` → 推 main → `landed`。
- **另看**：等待期间（第 1–5 步）别的根照常可领可推（`awaiting_grant` 不计在途）；`stg_release` 用 `false`（理由见 §7 Q4）。

### 实测 3 · 核心级（P7）

- **造**：碰 `hard_core` 但不碰 `hard_absolute`（`.env*`、`.gitmodules`、`.github/`）的一个工作单元，例如 `api/internal/agentrt/store/` 的小修（带 `--core`）。第一次建议选 `decision_chain = false` 的（不碰审批、身份目录与 Console 决策页），把「决策链自改」留到通道跑顺以后。
- **看**：
  1. 评审 spec 自动带信任链问题（`store/pinreview.go:104–106`：碰 hard 的钉住任务 → `TrustReviewText`）；Codex 评审结论逐条回答。
  2. 第二道闸 `awaiting_grant`，`soft` 含 `core`。
  3. **反例（统筹做）**：先用 `request_action` 建一张 `approve_guardrail_landing` → 建单校验拒绝（两种单类别不交）。
  4. `handin.sh material` 显示 `action = approve_core_landing`、`hard_core_paths`、`trust_review = true`；统筹建单 #C，理由第一段照 §12.2 第 1 条写「批准后，此提交改动审批 / 身份 / 落地闸门代码……」。
  5. 你在 Gitea 看 diff、批 #C → `landing_grant` → `main_intent` 带 `landing_grant_use` → 推 main → `landed`；提交带 `Landed-By`。

### 撤销一次

已含在实测 2 第 3–5 步。如果时间允许，统筹另记一个可选观察：对**已消费**的 grant 点撤销，应返回「已交给推送」且不写撤销记录（不需要你专门造）。

---

## 五、停与回退（由轻到重）

1. **收紧信封（统筹可做，免签，立即生效）**：交一版去掉 `external_hosts` 与 `coordinator-mbp` 的信封。效果：新钉被拒（`pin_not_permitted`）、`claim/pinned` 被拒、`GrantEnabled` 变假（等待中的根不再能被授权，72 h 后 `approval_expired`）。统筹用平台的 `Tightens` 核过它们确实是收紧（§6 F14）。
   - PROD：`rule_version: 6`、`direction: tighten`、`hosts: [agent-06]`、删掉整个 `external_hosts` 段，其余同 v5。
   - STG：`rule_version: 7`、`direction: tighten`、`hosts: [agent-06-stg]`、删掉 `external_hosts`。
   - 命令：`cd /Users/vision-mac-trader/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh tighten <回退文件> --env prod`（统筹跑）。之后要重新打开，需要你再签一版 loosen。
2. **撤销未消费的 grant（你）**：授权页 `Revoke`。已消费的撤不了，只能另做 revert。
3. **关 live（你推 infra）**：同 S3 操作单第 10 步，`platform-workers-landing-live.patch.yaml` 改回 `"off"`，停全部落地推送。
4. 代码不回退：流里已有 v1.2 记录，向前修（设计 §5.2、§7.3 第 5 条）。

---

## 六、统筹核实过的事实（platform `w31/core-int` 含 `efac01e5`；infra `ace7899`；库为 2026-10-29 13:4x CDT 读数）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 座位只在启动时由平台自登记，且只登记令牌表里有值的 `seat:coordinator`；没有路由写座位 | `api/internal/agentrt/store/seat.go:21,28–71`；调用 `api/internal/server/agentrt_wire.go:134`；`actuation/auth.go:262`（`Seats()` 只列加载到值的座位）、`:244`（座位名重复启动失败） |
| F2 | 座位令牌用 `reporter` 角色，但不受「受限 reporter」约束，可提议 | `agentrtapi/reporter.go:13–15`；`agentrtapi/api.go:116–117` |
| F3 | 设 pin 要求：非 Relayed、座位、令牌名即 actor；生效信封必须**已签名**且有该 pin 的条目，提议者、仓库、角色相符 | `store/pin.go:147–157,163–206`（`env.SignedBy == ""` 拒绝在 `:181`） |
| F4 | 签含 `external_hosts` 的信封时，提议者必须**已登记**为座位、执行者已登记；主机可以尚未登记 | `store/rules.go:427–455`（`case !seat` 在 `:446`），`:290–300` |
| F5 | 外部主机只在 `claim/pinned` 时、且已签生效信封点名时登记为 external；普通 agentd 登记被点名的主机会被拒 | `store/pinclaim.go:155–200`（`registerHostIn(... HostExternal ...)` 在 `:177`）；`store/kernel.go:298` |
| F6 | 精确领取的工具取条目的 `{executor, provider}`，model 为空串 | `store/pinclaim.go:85` |
| F7 | `job:implementer` 里 `exec:claude` 的 `probation` **不会**让精确领取 `no_lease`：路由与领取都接受 active 和 probation，probation 只降一档；`model_pattern: "*"` 匹配空串；probation 在 core 任务上被排除只发生在路由规则设了成绩门槛时，两边 `routing:dev` 都没设 | `store/route.go:94–100,163`；`store/claim.go:456–492`；`store/competence.go:120–131`；`agentrt-rules/{prod,stg}/routing-dev.yaml` |
| F8 | 精确领取仍受额度线约束：该执行者的池读数 ≥ `quota_stop_percent`（两边 90）时本次不领，`no_lease`（HTTP 409） | `store/pick.go:186–196`；`agentrtapi/api.go:290–291` |
| F9 | 信封内目标的任务只在信封 `hosts` 列出的主机上领 → `hosts` 必须加 `coordinator-mbp` | `store/envelope.go:117–129`；`store/claim.go:236–246`；`store/propose.go:398–415`（信封内目标记 `envelope_rule_id`） |
| F10 | 授权材料、建单校验、审批执行器在 **platform-api 进程**里读 Git，起草时用的是落地身份 `LanderFromEnv("prod")`；按 Owner 选 A 已改为只读读者（`2150b99c`）；进程没有落地身份或没有集群时全部拒绝 | `server/agentrt_grant.go:32–48,84–90,163`；`agentrtapi/landing_wait.go:58–72`；`landinggit/git.go:58–76` |
| F11 | 审批批准后，执行器在处理批准请求的进程里**同步**运行（即 api 进程）；workers 只做重试 | `approvals/service.go:519–527`；`server/approvals_loop.go:16–21` |
| F12 | 授权单只在 PROD：动作 PROD only、运行时 env 必须是 prod；STG 的演练是 DryRun，`MayAwaitGrant` 只在 prod + live 成立 → STG 没有 `awaiting_grant` 与单 | `server/agentrt_grant.go:58–78`（`IsProd` 在 `:67`，`rt.env != "prod"` 在 `:74`）；`landing/eligibility.go:187–190`；`landing/protocol.go:413` |
| F13 | 签了含条目的信封即 `GrantEnabled`；之后运行时普通任务碰 `hard_core` 也进等待，评审也带信任链问题 | `store/landing_grant_ci.go:297–308`；`landing/eligibility.go:158–163,187–190`；`store/pinreview.go:87–89` |
| F14 | 本单 §3 C 的四份规则与 §5 的两份回退信封，用平台自己的 `rules.Parse` 与 `rules.Tightens`（拷贝 `rules`、`canon` 两包到临时模块）读过：四份都能读，回退两份判为收紧 | 解析器 `api/internal/agentrt/rules/rules.go:228`、`envelope_hosts.go:46–118`、`tighten.go:16` |
| F15 | §3 D、E 的 overlay 改动在副本上 `kubectl kustomize` 渲染成功；PROD diff 只多出两条令牌、两项 env、api 的两项 env、一个卷与挂载 | 渲染于统筹临时目录，2026-10-29 |
| F16 | 当前库：两边无 `seat:coordinator`、无 `coordinator-mbp`；`executor_pin` 列在；PROD 信封最新 v4 为未签 tighten，STG v5 已签；两边 `landing:dev` v1 | `agent_reader` 读 `bifrost_platform`、`bifrost_platform_stg` |
| F17 | 规则签名在 STG 也要你的私钥：`rule.sh sign` 用 `~/.ssh/bifrost_release_owner`，平台只认编译进去的指纹；STG 历史上 v1、v2、v3、v5 都是已签 | `scripts/agentrt/rule.sh:9–14,103–122`；`server/agentrt_wire.go:84`（`Anchor: releasepolicy.OwnerKeyFingerprint`） |
| F18 | 集群读的是 infra overlay 的 `platform-auth.yaml`（ConfigMap，`disableNameSuffixHash`）；令牌值来自 Secret `bifrost-platform-role-tokens` 经 `secretKeyRef optional: true` 注入 `platform-api` | `k8s/overlays/platform-prod/kustomization.yaml:14–29`；`platform-api-role-tokens.patch.yaml`；`config/platform-auth.yaml` 两份 |
| F19 | `bifrost-platform-prod` / `-stg` 两个 Argo 应用是 automated + prune + selfHeal：推 infra main 立即生效 | `agent-config/AGENT_FACTS.md:412–414` |
| F20 | 第二道闸在发布窗口开着时不推（窗口 ConfigMap 未过期即阻断） | `api/internal/agentrt/landingci/window.go:28–50`；`controller/landing_live.go:82` |
| F21 | `handin.sh` 默认连 PROD（`http://192.168.10.100:30876`）、默认读 `~/.config/bifrost/coordinator-{agentd,proposer}.token`，可用 `PLATFORM_AGENTRT_URL`、`HANDIN_*_TOKEN_FILE` 改；没有 `material` 子命令；claim 失败只报 HTTP 码 | `agent-config/scripts/landing/handin.sh:25–33,42,109–112,311` |
| F22 | `preflight.js` 只拦 admin 令牌与 `mcp-tokens.env`，不拦 `handin.sh` 读两个统筹令牌文件 | `agent-config/scripts/agent-guard/preflight.js:754–755,1050` |
| F23 | Gitea `agent/**` 的保护已删（TD-383），有写权的账号都能推尝试分支；本机 Gitea 用户名配置为 `bifrost-mbp`（钥匙串） | `scripts/gitea/protect-repo.sh:261–274`；本机 `git config credential.http://192.168.10.73:30300.username` |

## 七、核实不了 / 有疑问的点

- **Q1（已定）**：Owner 2026-10-29 选 A——api 进程不挂落地身份；platform `2150b99c` 加 `landinggit.ReaderFromEnv`（只读的 Gitea 读者，任何写操作在联网前拒绝），授权链改用它。随下一批 platform 代码由 Owner 推 main、走 PROD 发布单上线，启用前完成。
- **Q2 额度线**：精确领取受 Claude 池额度线（90%）约束（F8）。统筹自己就在用同一个 Owner 账号的池；周额度高时 `handin.sh run` 会被 `no_lease` 拒。B1 让原因可见；需要时你可签 `routing:dev` 提高 `quota_stop_percent`，本单不做。
- **Q3 `bifrost-mbp` 的 Gitea 写权**：没读令牌就无法确认它能写 `bifrost-platform`。S6-a 第一次 `handin.sh run` 推 `agent/<task>/a1` 就会证明；不行再补团队成员。
- **Q4 `stg_release` 取值**：设计 O-1 A 默认 `true`；但 PROD 跑的 `efac01e5` 还没有 B5 的批次授权（`f4153c41` 在其后），PROD `landing:dev` 也是 `stg_release: none`。实测建议用 `false`，免得把 B5 牵进来；B5 上线后再按默认。请统筹定。
- **Q5 STG 演练对钉住任务的端到端**：代码路径读过（演练用 `EligibleToClaim`，钉住、规则内的根可领），但没在真库上跑过 handin 类任务进演练；S6-a 是第一次。
- **Q6 推送分工**：提交 #1 含脚本与规则文件，不是「只改 STG overlay」，不在「STG 发布 A」范围内；且 4.1 推送冻结期 infra main 由你推。所以两次都写成你推。若统筹确认冻结已解除，提交 #1 可拆出纯 STG overlay 的一小份由统筹 `push-main.sh` 推，你少一次推送。
- **Q7 回退版本号**：§5 的回退信封按「签完 v5/v6 后没有别的新版」写号；真要用时统筹先 `rule.sh show` 再定号。
- **Q8 实测件数与额度**：实测 3 件 + 运行时当天已落的件数要 ≤ 5（P8 之前）；若当天运行时已落多件，统筹把实测 3 挪到 P8 之后。
