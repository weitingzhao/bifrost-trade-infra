# LANE-RP — 发版策略授权：符合 Owner 签的策略就自动放行，到期前主动提醒（infra · platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply）。报告写到 `cursor-tasks/reports/LANE-RP.md`。
再读 `agent-config/work/release-approval/PROPOSAL-2026-10-08.md`（§3 与 §7 Owner 决定）和同目录 `release-policy.draft.yaml`。
分支：`cursor/rp-infra`、`cursor/rp-platform`（各从 `origin/main` 新开）。

**实现者约束**：本道的代码决定「谁的发布可以不等人」。实现它的会话不能同时是待批发布的申请方；不要在本道里批准、发起或推进任何发布。

## Owner 已定（10-08）

- 授权绑在**策略**上，不绑在任何 Agent 身份上（不实现 §4）。
- 不设滚动 24 小时次数上限；并发 1 由发布窗口保证。
- 策略 7 天过期；**到期前 48 / 24 / 2 小时主动推送提醒**，过期后有发布在等时再推一次；消息里直接给签发命令。不能默默卡住。

## 签名（信任根）

- 策略 = `policy.yaml` + `policy.sig`，签名用 `ssh-keygen -Y sign -n bifrost-release-policy`，验证用 `ssh-keygen -Y verify`（Go 侧用 `golang.org/x/crypto/ssh` 的 sshsig 等价校验，或调用系统 ssh-keygen——选一种写进报告，**不引入新的第三方依赖**；若必须引入，停下列选项）。
- Owner 的签名私钥**不能被 Agent 使用**：默认方案是一把带口令、不加进 ssh-agent 的专用密钥 `~/.ssh/bifrost_release_owner`（签发时 Owner 手输口令）；可选 Secretive（Secure Enclave + Touch ID）。生成密钥是 Owner 的动作，本道只写文档与命令，不生成、不读任何私钥。
- 公钥（allowed_signers）放 infra `agent-config/release-policy/allowed_signers`，**并且** platform-api 编译期内置其指纹；两者不一致即视为无有效策略。改公钥 = 改信任根，命中 `no_trust_anchor_change`，必须人批。

## 要做

### infra（`cursor/rp-infra`）

1. `scripts/release/release.sh policy {status,sign,verify}`：
   - `status`：读 ConfigMap `cicd/bifrost-release-policy`，打印 policy_id、到期时间、剩余小时、校验结果；冻结状态。
   - `sign [--days 7]`：从 `release-policy.draft.yaml` 模板生成 policy.yaml（填 signed_at / expires_at / policy_id），调用 `ssh-keygen -Y sign`（会提示 Owner 输口令或 Touch ID），然后**打印**要执行的 `kubectl apply` 命令（不自己 apply）。
   - `verify`：本地校验签名与到期。
2. `release.sh freeze --reason <r>` / `release.sh unfreeze`：写 ConfigMap `cicd/bifrost-release-freeze`。unfreeze 要求一份有效签名（同一把密钥签一段 `unfreeze <time>` 文本），freeze 谁都能设（安全方向）。
3. `release.sh merge <repo> <sha>`：推 main 的唯一入口——查窗口（自己 hold）、查 CI（`ci-*` Succeeded）、查策略条件（下面第 5 条的同一函数），通过就 `git push origin <sha>:refs/heads/main`；不通过就打印原因并 exit 3（等 Owner）。
4. `release.sh stg|prod|dev` 与 research / 插件构建入口：开工前读策略 + 冻结。策略有效且条件全满足 → 照常执行，日志写「auto-approved by <policy_id>」；否则 exit 3 并打印「等 Owner：<原因>」与签发命令。
5. 条件检查实现成一个可复用脚本（如 `scripts/release/policy_check.py`），输入 repo + 旧 SHA（当前部署）+ 新 SHA，按 draft 的 `no_ddl` / `no_d10_paths` / `no_trust_anchor_change` 路径表判断；路径表放一份文件，platform 与 infra 共读，不复制两份。
6. 清单（只推分支，不 apply）：`k8s/cicd/release-policy/`（两个 ConfigMap 的空壳 + RBAC：agent 的 SA 只 `get`；`bifrost-platform` 的 SA 只 `get`）。
7. 防线：`policy_check.py` 单测（每类路径命中 → 需人批；全不命中 → 放行；签名坏 / 过期 / 缺失 / 冻结 → 需人批）；`release.sh policy verify` 的 bash 测试。

### platform（`cursor/rp-platform`）

1. `api/internal/server/actions_wire.go:60`（现在返回 `approval required` 的地方）：C 级动作先读策略 + 冻结；策略有效、动作在 `allow`、条件满足 → 直接执行，审计写 `auto-approved policy_id=<id> requester=<who> sha=<sha>`；否则照旧建审批单。D 级动作一律不自动批。
2. **到期提醒**：platform-workers 加一个每小时检查——策略剩余 ≤ 48 / 24 / 2 小时各推一次（复用 `api/internal/approvalnotify` 的手机推送通道，同一档只推一次）；已过期且有待决单据 → 立即推「策略已过期，N 个发布在等你签」。推送正文带签发命令 `bifrost-trade-infra/scripts/release/release.sh policy sign`。Console 横幅显示剩余时间（≤ 48 小时变黄，过期变红）：做成**独立组件 + 数据 hook**（`console/src/components/ReleasePolicyBanner.tsx` 与自己的测试），**不要改** `ConsolePage`、header、`consoleNavConfig`——ops-arch 第 3 阶段 S2 正在重写外壳；后落地的一方负责挂载（RP 先落地就由 ops-arch 在新 header 里挂）。
   每小时检查的维护者名字固定为：日志前缀 `release_policy_expiry_check`，指标 `bifrost_release_policy_expires_in_seconds`（gauge，无有效策略时为 0）与 `bifrost_release_policy_reminders_sent_total{window="48h|24h|2h|expired"}`；合并后由 ops-arch 登记进 `agent-config/MAINTAINERS.yaml`。
3. 冻结：读 `cicd/bifrost-release-freeze`，设了就拒绝所有 C 级发布动作；读不出来按冻结处理。
4. 防线：Go 测试——有效策略 + 条件满足 → 自动执行并写审计；过期 / 签名坏 / 冻结 / 路径命中 / D 级 → 建单据；提醒在 48/24/2 小时各一次且不重复；过期且有待决 → 推送。

## 不做

不改 approvals 的人工审批路径（Owner 仍可随时手动批或拒）；不实现 Der 主体（§4）；不生成或读取任何私钥；不 apply 任何清单；不发版。
`api/internal/checklist` 的派发代码归 ops-arch 第 3 阶段，不碰。改 `api/internal/approvals/` 之前先看 `agent-config/work/ops-arch/` 有没有同时在改它的道，有就停下写报告。

## 报告里要写

- 签名校验选的实现方式与理由。
- Owner 签发与轮换的完整操作手册（生成密钥 → 放公钥 → 第一次 sign → apply → status），每步一条命令。
- 「要 Owner 批」：合并、apply 两个 ConfigMap 与 RBAC、生成签名密钥并第一次签发、用 `apply-release-permissions.sh` 把 `release.sh merge` / `policy *` 加进放行规则（若需要）。
