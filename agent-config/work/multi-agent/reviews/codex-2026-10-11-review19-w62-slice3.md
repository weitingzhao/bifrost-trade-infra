VERDICT: fix first

1. **P1：审批卡片可冒充另一项请求。** [ProgressNeedsYou.tsx:72](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/ProgressNeedsYou.tsx:72) 只读取真实状态；第83、125–150行仍使用文档的请求号和说明，没有展示列表中的真实 summary，也不核对请求种类。已复现：卡片写“无害文档、#6”，实际打开“删除生产数据、#91”。第50–55行的步骤链接甚至不要求 id 存在于列表。应从真实请求生成编号与说明，将代理文字明确分开。当前不会直接批准，但会误导 Owner 打开错误请求。

2. **P2：“Part of”把代理声明呈现为请求的关联事实。** [ApprovalRow.tsx:69](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/needs-you/ApprovalRow.tsx:69) 未标明信息来自不可信进度文档，且没有长度限制或双向文字隔离。真实标题只显示两行，代理关联文字却可无限换行，占满视口并挤走后续请求。应标明“Agent-reported”，限制展示长度，并隔离方向控制字符；普通换行虽被折叠，长文和同形字符仍可误导。

3. **P2：审批状态没有持续刷新。** [ProgressNeedsYou.tsx:97](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/ProgressNeedsYou.tsx:97) 的审批查询没有轮询；进度文档每15秒刷新不会刷新另一 query key。页面持续打开、请求在另一设备完成后，卡片仍可能无限保留 pending 按钮。应周期刷新审批状态，并处理本地到期。

4. **P2：列表不可读时恢复催办，终态也未移除旧指令。** [ProgressNeedsYou.tsx:74](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/ProgressNeedsYou.tsx:74) 将加载中或失败直接视为 asking，不显示读取失败说明。已知非 pending 状态虽隐藏主按钮，第128–150行仍保留等待计时、批准指令及 action 链接；旧文档可继续催办已决定的请求。应显示状态未知，终态卡片停止计时并移除催办内容。

5. **P2：无效或过期配额仍可显示健康结论。** [quotaModel.ts:73](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/quotaModel.ts:73) 直接相信 verdict，不检查必要数值和重置时间。已复现：过去的 resets_at 同时显示“Reset due”和“On pace”；非数值 used 被解析丢弃后仍显示绿色“Spare”。未知 verdict 静默消失，负 used 则显示负百分比而条形为0。应把无效数据降为未知，过期窗口撤销旧节奏结论。

6. **P3：配额行数无限制。** [ProgressQuota.tsx:109](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/ProgressQuota.tsx:109) 全量渲染所有池，每行还有每秒更新的 Tick；解析500行会全部保留。应限制首屏行数并提供折叠或分页，避免长文档挤走工作区、放大持续渲染负担。

7. **P3：每秒更新超出“仅时长文本”的要求。** [ProgressWorks.tsx:134](~/agent-work/w62-slice3/bifrost-platform/console/src/pages/shell/progress/ProgressWorks.tsx:134) 的 StepBar 订阅秒钟，每秒重新计算并渲染条形，包括已完成步骤。应使用文档刷新时的快照计算条形，让秒钟仅驱动时长文字。

其余核查：文本使用 React 转义，未发现 HTML 注入；请求 id 限制为 `appr_` 加16位小写十六进制，路由参数经编码。action 链接沿用既有安全规则。零/负 usual_min、未来 started 均不会产生负条形或除零；等待 Owner 的步骤不显示 late；缺少 pools 时保留旧用量展示。

验证采用只读代码检查及内存转译/模拟渲染，未运行完整测试套件；未写文件、读取凭据或调用平台/集群。

END OF REPORT