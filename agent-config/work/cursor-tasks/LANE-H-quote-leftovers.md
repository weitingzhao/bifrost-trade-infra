# LANE-D — TD-260 之后的三处报价残留（TD-264，frontend + core）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-D.md`。
分支：`cursor/d-frontend`、必要时 `cursor/d-core`。都从当前 `origin/main` 新开（TD-260 已在 main 上、已上 PROD：core 0.60.0 / frontend 81a796b）。

## 背景（台账 `### TD-264`）

LANE-X 落地 TD-260 时顺带查出三条，当时没做：

1. **`StockPositionSection` 没有任何 importer** —— 死代码。
2. **`buildTradeGroups.ts:45` 期权行优先用 `/status` 的价格**。今天无害（`/status` 的期权行不带价格），但只要 `/status` 哪天又带上旧的期权价，它会盖过 EOD 的价格。
3. **`degraded_leg_count` 没人显示**。core 的 model 会返回它 —— 期权 mid 永远取不到（TD-260 的残留：portfolio model 仍 JOIN `contract_quote_live` 取期权 mid，那张表已无写入方），于是对应腿的 Greeks 记为 degraded。**前端一处都不显示这个计数**，所以腿被静默降级，页面什么都不说。

第 3 条是活的问题，属于「未量到的东西显示成绿的」那一类，优先做。

## 要做

1. **先量第 3 条**：`degraded_leg_count` 现在在 PROD / DEV 的实际值是多少？哪些页面显示 Greeks？把实测写进报告，再决定显示在哪、怎么措辞。
   显示要求：**一个计数加它的原因**，不要只画个图标；没有 degraded 的腿时不要显示一个 0（和既有规则一致：`—` 不是 `0`）。
2. 删掉 `StockPositionSection`（确认真的没有 importer 再删，包括动态 import 和字符串引用）。
3. 把 `buildTradeGroups.ts:45` 的优先级反过来：**带日期的 EOD 价优先，除非实时源更新** —— 和 `src/utils/spotPrice.ts` 对股票已经用的规则一致。直接复用 `spotPrice.ts` 的判定，不要再写第二套。
4. 防线：`spotPrice.test.ts` 的优先级用例扩到期权行；一条断言 `degraded_leg_count` 非零时会被渲染出来。
5. 门禁：frontend `npx tsc -b && npm run lint && npx vitest run && npm run build && npm run check:legacy-css`；core（如果动了）`make lint && make test`。退出码分开记录。
   frontend worktree 要有兄弟 `bifrost-ui` 软链，否则 `npm run build` 会报 `semantic.css` ENOENT。
   core 测试的 `PYTHONPATH` 要把本分支 worktree 的 `src` 放最前面。

## 不做

- **不要给 `contract_quote_live` 加写入方**（Owner 10-08 定了删镜像）。期权 mid 取不到就是取不到，页面说清楚即可。
- 不删表、不写 DDL、不推 main、不发版。
- core 若改了公开接口，按 `.cursor/rules/versioning.mdc` bump；**删公开函数不是 patch**（上两轮因此定在 0.59.0 / 0.60.0）。
