# LANE-U2 报告

起点都是各仓库 `origin/main`。共享 checkout 没有改。bifrost-ui `7b73d38` 已推 `cursor/u2-ui`。前端没有提交。

扫描方法：用 TypeScript 语法树读 `src/index.ts` 的具名再导出，再读两个消费方源码里 `from '@bifrost/ui'` 的具名 import / 再导出（含 `import type`）。两边都没有 `import *`，也没有 `import('@bifrost/ui')`。没有把 knip / ts-prune 加进依赖（新的 npm 包要另批，而且把 barrel 当入口时它们会把再导出当成「已使用」）。棘轮脚本做的是同一件事。

## TD-239

- Claim：成立。`origin/main` 的 `bifrost-ui/src/index.ts` 有 283 个公开名字。按上面的 import 图，Trade frontend（`6d861329`）和 Ops Console（`2727eb0`）都没有引用的有 **101** 个（42 个类型 + 59 个运行时名字）。台账写的「85 个文本未命中、约 45 个是 Props」是文本搜索，没有扣掉包内引用；这次按 import 子句重测，结论相同：公开面里有一批没有任何应用在用，而且之前没有工具在量。证据：`bifrost-ui/src/data-display/Kpi.tsx` 的 `KpiStrip`、`src/index.ts` 的 ContextMenu 再导出；两个消费方对这 101 个名字的 import 计数都是 0。
- 改动：`bifrost-ui` · `cursor/u2-ui` · `7b73d381f1bd8fe6eb3afca710446947a253b46e`（公开面缩小，版本 `0.13.0` → `0.14.0`，仓库自己的规则要求公开 API 变更 bump）。消费方走 `file:`，没有改它们的版本下限。
- 删掉的公开导出（79 个，不再从 `src/index.ts` 出去）：
  - 运行时 37 个：`navRowKind`、`defaultMatchActive`、`resolveShellNavSlot`、`shellNavSubItemButtonClass`、`shellNavSubItemButtonFlexClass`、`shellNavPhaseFocusClass`、`shellNavOffPhaseClass`、`shellNavExternalLinkIconClass`、`shellNavGroupLabelClass`、`shellNavGroupLabelSecondaryClass`、`shellNavGroupLabelTextClass`、`shellNavSeatZoneClass`、`shellNavPartnerZoneClass`、`shellNavGroupIconClass`、`shellNavGroupChevronClass`、`shellNavChildExpandButtonClass`、`shellNavExpandChevronButtonClass`、`shellNavFlyoutItemActiveClass`、`shellNavFlyoutItemInactiveClass`、`shellNavHeaderActionButtonClass`、`shellNavFlyoutDocLinkClass`、`shellNavPeerLinkExpandedClass`、`shellNavPeerLinkTitleClass`、`shellNavPeerLinkExternalIconClass`、`shellNavPeerLinkDescriptionClass`、`denseTagClass`、`holidayLine`、`isoMonthOf`、`useScrolledPast`、`useStuck`、`installStuckMarks`、`findScroller`、`STUCK_BAR_SELECTOR`、`useMorph`、`composeRefs`、`useIsMobile`、`MOBILE_BREAKPOINT`
  - 类型 42 个：`SectionBandProps`、`PanelHeadProps`、`ShellNavGroupEmphasis`、`PeerAppLink`、`ShellNavSidebarProps`、`ShellNavDocLink`、`ShellNavFilterOptions`、`ShellNavSlotContent`、`AuthStatus`、`ViewStateProps`、`ViewStateReport`、`IconActionButtonProps`、`IconActionButtonDefaultProps`、`IconActionButtonCloseProps`、`DenseTagSize`、`NumberFieldProps`、`KpiCardProps`、`KpiStripProps`、`KpiState`、`FilterBarProps`、`InspectorPanelProps`、`InspectorReadOnly`、`TokenSearchFieldProps`、`UndoToastProps`、`FilterChipProps`、`FilterTrayProps`、`FilterGroupProps`、`FilterGroupItem`、`FilterGroupState`、`CalendarGridProps`、`CalendarNavProps`、`CalendarHoliday`、`CalendarTense`、`MiniMonthProps`、`MiniMonthStatus`、`TimeStripProps`、`TimeStripLane`、`MorphSource`、`DenseCol`、`DenseListProps`、`DenseListHeadProps`、`DenseListRowProps`
  - 包内仍要的实现留着。只在定义文件里用的改成文件私有（`holidayLine`、`useScrolledPast`、`navRowKind`、`MOBILE_BREAKPOINT`、`STUCK_BAR_SELECTOR`、`findScroller`、`installStuckMarks`，以及 `shellNavClasses.ts` 里只给同文件函数拼类名的 5 个 const）。其它文件还在 import 的（`useMorph`、`composeRefs`、`useIsMobile`、`useStuck`、`isoMonthOf`、`denseTagClass`、侧栏用的那些 class helper）仍从模块导出，只是不再从包入口出去。
- Design 有意保留（应用没 import，`design-keep:` 写在导出语句上）：
  - `BifrostLogoMark`、`BifrostLogoFull`：Design preview 和 `componentSrcMap` 都在用，设计代理要 `.d.ts`（`.design-sync/NOTES.md`、`config.json`）。`ShellNavSidebar` 内部也在画它们。
  - `KpiCard`、`KpiStrip`：0.5.0 的 Design preview（`.design-sync/previews/KpiStrip.tsx`）和 `componentSrcMap` 钉着；两个应用都没 import。
  - `ScrollEdge`：Design preview 和 `componentSrcMap` 钉着；应用没 import。`useScrolledPast` 只被这个组件自己用，已经收成文件私有。
  - `ContextMenu` 及 13 个部件（`Trigger`、`Content`、`Item`、`CheckboxItem`、`Label`、`Separator`、`Shortcut`、`Group`、`Portal`、`Sub`、`SubContent`、`SubTrigger`、`RadioGroup`）：NOTES「Discovery / grouping」写明 shadcn 每个子导出都是组件，设计代理要各自的 `.d.ts`，`componentSrcMap` 逐个钉着。
  - `SheetTrigger`、`SheetClose`、`SheetFooter`：同上（Sheet 家族）。同条导出里的 `Sheet`、`SheetContent`、`SheetHeader`、`SheetTitle`、`SheetDescription` 应用在用，注释说明的是这三个没有应用引用的部件。
- 防线：`bifrost-ui/scripts/public-exports.test.mjs` 的 `every @bifrost/ui export is imported by an app or marked design-keep`。没有写进 `scan.sh` 的 `UI_UNUSED_EXPORTS`：那个文件在 `bifrost-trade-infra`，本轮归 LANE-R1，S2 也开着 `cursor/s2-infra`；而且今天没有任何 CI 对 `bifrost-ui` 跑 `scan.sh --repo`（`pipeline-ci-frontend.yaml` 的 code-health 扫的是 `bifrost-trade-frontend`）。包内测试在两个消费方目录都在时会失败于「没人 import、又没有 design-keep 理由」的新导出。消费方目录不在时测试退出为 NOT MEASURED，不当成通过。
- 门禁（退出码分开看）：
  - bifrost-ui：没有 `tsc -b` 的 project reference（`npx tsc -b` 退出 0，无输出）；`npx tsc --noEmit`（即 `npm run lint`）退出 0；没有 eslint、没有 vitest；`npm test`（`node --test scripts/*.test.mjs`）5 passed、退出 0；`npm run build` 退出 0
  - Trade frontend（只读 worktree，对照这次 ui 的 `dist`）：`npx tsc -b` 退出 0；`npm run lint` 退出 0（67 条既有 warning，0 error）；`npm run build` 退出 0。没有改前端源码，没有跑约 9 分钟的 vitest
  - Ops Console（platform `origin/main` 的只读 detached worktree，没有提交）：`npx tsc -b` 退出 0；`npm run lint` 退出 0（19 条既有 warning，0 error）；`npm run build` 退出 0。没有改 console 源码，所以没有和 S1/S2/R1 撞文件
- 验收：在 bifrost-ui 的 `cursor/u2-ui` 上，把两个消费方指到 **origin/main**（共享 frontend checkout 落后 origin/main，不要用它）：

  ```
  BIFROST_UI_FRONTEND_SRC=<bifrost-trade-frontend>/src \
  BIFROST_UI_CONSOLE_SRC=<bifrost-platform>/console/src \
  npm test
  ```

  预期：`every @bifrost/ui export is imported by an app or marked design-keep` 通过；`src/index.ts` 不再导出 `holidayLine`、`useMorph`、`KpiStripProps`；仍导出 `KpiStrip`、`ContextMenu`，且这些语句上有 `design-keep:`。
- 要 Owner 批：没有。分支只推了 `cursor/u2-ui`，没有推 main，没有发版。
- 后续：`UI_UNUSED_EXPORTS` 还没进 `scripts/code-health/scan.sh` / `baselines.env`，也没有 CI job 跑 `--repo bifrost-ui`。那两处在 infra，本道没有改。合入后若要把台账里的验收命令换成 `scan.sh | grep UI_UNUSED_EXPORTS`，需要另开 infra 改动，并确认不和 LANE-R1 改同一文件。

## TD-182

- Claim：不成立。台账证据 `bifrost-trade-frontend/src/components/research/EventRadarDashboard.tsx:213`（`'Forward releases appear when macro CSV includes forward_flag rows'`）在 **origin/main 上已经不存在**。`e98afbf0`（`chore(research): delete the unmounted EventsBoard and EventRadarDashboard`，TD-199）删了这个组件。共享 checkout 落后 origin/main 9 个提交，工作区里还能看见旧文件，不以它为准。`origin/main` 上搜 `forward_flag rows`、`Macro pipeline pending`、`macro/input` 没有命中。剩下的 `forward_flag` 只在 `src/api/researchEngine.ts:391` 作为可选字段类型，不是空状态文案。
- 改动：没有。没有提交，没有推 `cursor/u2-fe`（本地分支已删，避免一条和 `origin/main` 相同的空分支）。
- 防线：不需要新测试。组件已经不在；`src/lib/orphanModules.test.ts` 从 `main.tsx` 走 import 图，`KNOWN_ORPHANS` 基线是空的，删掉的模块再出现且没人 import 会失败。
- 门禁：没有改前端，没有单独再跑一遍 vitest。上面 TD-239 的 frontend `tsc -b` / lint / build 是在 `origin/main`（`6d861329`）上对这次 ui 跑的，退出码都是 0。
- 验收：`git -C bifrost-trade-frontend grep -n "forward_flag rows" origin/main -- '*.ts' '*.tsx'` 应无输出；`git -C bifrost-trade-frontend cat-file -e origin/main:src/components/research/EventRadarDashboard.tsx` 应失败（路径不存在）。
- 要 Owner 批：没有。
- 后续：台账后半（Massive `/fed/v1/inflation` 的 raw 表灌进 `macro_event_daily.actual`）不在本道，没有做。宏观缺口面板若以后重新挂上页面，空状态应写明 consensus 不在订阅里（权限缺口），不要再写 CSV `forward_flag`。
