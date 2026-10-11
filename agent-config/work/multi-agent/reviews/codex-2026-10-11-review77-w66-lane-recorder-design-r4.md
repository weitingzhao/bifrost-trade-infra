# Codex 复核 77 — W-66 第一半「记录事件、生成状态」的设计，第 4 轮（Owner 重开后；344 行）

2026-10-11 14:32 CDT · 只读

统筹方处理：**可以实现**。必须改的四次是 8 → 3 → 1 → 0。复核 76 的五处全部关闭；剩两处应该改的（从没输出过的进程从哪一刻起算静默、`last_seen` 里的内容怎么由事件算出），已并进文档第 4 节和第 7 节，并写进第一片的任务书带验收。按规则：设计复核没有必须改的，改完小问题就开始实现。

---

VERDICT: implement
P1 COUNT: 0
76-1 closed｜§3–4、7 V7：仅 `reader_clock_behind` 可随 `now` 恢复，原反例三个时间点一致。
76-2 closed｜§4、7.3：判球统一用合并后的 ref；关闭校验保持本地语义。
76-3 closed｜§4、7.3：`record_created` 要求当前为 waiting 且确认有效。
76-4 closed｜§5、7.3：命令正文的发布例外、替代字段及回归已明确。
76-5 closed｜§4、7.2(b)：after、usual_s 对 holds_up、球、估算及发布的派生影响已纳入。
P2｜§4、7.5：process 开始后所有心跳均为 `output_bytes: 0`，从未“变大”，quiet 的计时起点未定义，但端到端验收要求它进入 quiet。最小修改：无增长记录时从 step_started.at 计算静默时间，首次增长后改用 sampled_at，并补零输出夹具。
P2｜§4：`last_seen{state, at}` 未规定历史 state 如何从事件计算；事件只有存活和输出观测，没有保存 running/slow/quiet，纯 fold 也没有上一份快照。最小修改：明确确定性的计算规则，或改为原始参照观测字段；不得读取上次生成的文档。
时间核对｜§3–4、7：以下均先固定事件，再仅推进 now；新增事件另行注明。
process 无心跳｜start=0、usual_s=100：now=0 running，151 slow，181 unknown(no_observation)；无估算则省掉 slow。
未来开始｜start=300、note=240：now=240 unknown(reader_clock_behind)，440 running，2240 unknown(no_observation)，符合 V7。
process 其余状态｜未开始的 waiting、dead、done、failed 随 now 不变；已有输出增长记录且心跳新鲜时可为 quiet，确认时间超过 180 秒后为 unknown。
none｜有效开始后 running 可随 now 成为 slow；waiting、done、failed 不变，不受观测期限和读方时钟落后影响。
record｜无名字的 waiting 不变；有名字、确认有效的 waiting/running/slow 在确认过期后均为 unknown，终态 done/failed 不变。
record 续确认｜found 且未开始、轮次 ended_at=300：now=440 waiting，500 unknown(not_confirmed)；追加 ended_at=600 的有效确认轮次后，600 恢复 waiting。
Owner 跨读方落后｜approved、轮次 ended_at=300：now=240 清单内 unknown，440 清单外且球为 agents，500 清单内 unknown；终态事项始终不回清单。
unknown 各原因｜clock_backwards、no_observation、log_invalid 仅推进 now 不恢复；not_confirmed 和八种 error 同样如此。
unknown 其余原因｜no_match、conflicting_observations 可在确认过期后改为 not_confirmed，仍是 unknown；只有 reader_clock_behind 能仅随 now 离开 unknown。
不变量核对｜上述序列未发现 V1–V12 与状态表的新冲突；真实 HandlePut 夹具尚未实现，本次只核对了本地源码，不能算运行验收通过。
六项额外修改｜未发现撤销复核 68、73、76 已接受的边界；process 的 command 从可选改为必填是明确收紧，符合始终展示命令的要求。
片 1｜可开始实现；上述两项 P2 应在任务书中确定并携带验收。缺陷代码、穷举字母表仍须按§3、7列全，无需新增架构或 Owner 决策。
判词与闸门｜§2、6、9：未发现新增放行入口；done、landed、can_act、wait 退出码仍可能被新消费者当作判词，现有防线的有限范围已如实记录。
执行记录｜仅只读检查文档、差异和本地源码；未写文件，未调用 HTTP、平台或集群，未读取凭证。
END OF REPORT