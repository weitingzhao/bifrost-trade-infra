# LANE-V — 前端两项收尾：TD-145 Best regime 列、TD-150 数据缺口措辞（frontend）

先读 `cursor-tasks/README.md`（第 2 轮规则继续适用：只推分支，不推 main，不发版、不写库）。报告写到 `cursor-tasks/reports/LANE-V.md`。
分支：`cursor/v-frontend`（bifrost-trade-frontend，从 `origin/main` 新开）。两项各自成提交。
前端 worktree 里 husky 不执行：提交信息尾注用 `lineage.sh commit-msg` 补；`node_modules` 从共享 checkout 软链。

## TD-145 — JudgeTrackRecord 的 Best regime 列

后端已上（research 0.186.0）：`GET /research/candidate-outcome/summary?source=<src>&days=<n>&by_regime=true`
返回 `data.by_regime`（每个 regime 的 hit_rate 与样本数）；`/rows` 每行带 `regime` / `regime_scope` / `regime_date`。端点要 research 用户令牌（require_owner），沿用该页现有的 Research 请求方式。

1. 先对 DEV 实测这两个端点（`:5173` 代理或 research-api），把真实响应形状写进报告，再写代码。
2. JudgeTrackRecord 的 Best regime 列：取 hit_rate 最高、且样本数 ≥ 门槛的 regime；门槛写成常量（建议 5，报告里写依据）。不过门槛的写 `—` 并在 `title` 写「fewer than N settled in any regime」，不写 0。
3. 同页 Journal Settled 的 Right / Wrong 拆分改读 `/rows?source=&days=`（TD-147 的端点）——先实测它在 DEV 有数再改；没数就停下写进报告。
4. 新端点同 PR 加 zod schema（`src/lib/schemas/research.ts`），正向不误报、缺字段能拦。
5. 防线：组件测试覆盖「过门槛选最高」「都不过门槛显示 —」；`git grep -n by_regime -- src` 至少一行（台账验收命令）。

## TD-150 — 三处数据缺口措辞（已有分支，落地）

代码在 `origin/fix/data-gap-wording`（024077be · e8e554fc · 7caac1f8，基于 d1254adc；d1254adc 已在 main）。

1. 把这三个提交 cherry-pick 到 `cursor/v-frontend`（保留原 Change-Id 尾注，不要重写），解决冲突。
2. 全量门禁：`npx tsc -b && npm run lint && npx vitest run && npm run build && npm run check:legacy-css && npm run check:code-health`，每个退出码单独记录。
3. 在 `:5173` 对 DEV 看 Today、Limits、Scan、Vol ratings、Corporate Actions、Symbol?CUE，每页一句实际看到的措辞写进报告。
4. 防线：一个 vitest 在 `src`（排除 `src/layout/designNotes`）里搜退役短语，命中即失败：
   `earnings date reaches this side` · `No earnings date on this side` · `carry nothing at all` · `cannot say whether they pay`。
   已有就写测试名；没有就加。
5. 台账验收（Claude Code 会照跑）：上面四个短语在 `src`（除 designNotes）无命中；`only adjusted contracts` 至少一行。

## 不做

不改 Design 原型（`design/trade/` 只读）、不改 routeTable 的 aligned 状态、不推 main、不发版。
Design 待看三点（Vol ratings All 下 Earn 列、CUE 指标块 No reading、440 紧凑版）只记录现状，不改。
