VERDICT: fix first

逐项复核 review 35（文件均位于 `agent-config/scripts/lane/`）：

- **P1 重复 attempt：已关闭原复现。** `recorder.py:150` 拒绝第二次记录；`query.py:199` 将重复证据判为无效。重跑“implement 成功后追加退出 9”和“review 通过后追加否决”，两者均返回 `unknown`。
- **P1 启动条件：未完全关闭。** 原来的错误起点复现现在返回 `step_failed`（`decide.py:151`），但完整放行契约仍有缺口，见下。
- **P2 产物持久化：已关闭。** `recorder.py:243` 起调用同步写入；`fsutil.py:44` 同步文件和目录，再发布 manifest。
- **P2 残尾副本短写：已关闭。** `fsutil.py:35` 循环写完，零长度写入报错；`repair.py:83` 先发布副本再截断。
- **P2 六关统一入口：未关闭。** 空 `LANE_EXEC`、参数优先级、`new` 查表及共用预算已补齐（`commands.py:37`、115；`query.py:129`）；记录器仍提前取锁和修复残尾。
- **P2 第二轮 brief：正常路径已关闭。** `recorder.py:411` 引用当前 `round_opened.brief_copy`。
- **P2 验收覆盖：部分关闭。** T22 增加入入口检查，T28、T48、T53②已补案例（`test_table.py:175`、`test_evidence.py:47`、215、`test_flow.py:157`）；T31 仍漏掉下述放行缺口。
- **P3 T23／still-unknown：已关闭。** 规格 §4 与 `decide.py:58`、95 一致：信号失败优先，否决集合保留，备注不关闭轮次。

剩余发现：

- **P1 — 不完整或错误的启动证据仍可通过。** `decide.py:164` 只比较 verify/review 的提交号，不比较树号，也不要求逐仓库完整检查。内存实测：分别把 verify、review 的启动树号改为错误值，仍返回 `passed`；三步分别删除 `tree/clean/hidden`，以及删除 implement 的消费集合，也仍通过（`decide.py:147`、155、157）。应要求完整仓库集合、必要字段和提交／树号一致；缺失证据不得通过。
- **P2 — 未固定集合的轮次清掉此前起点。** `query.py:148` 用空 `pinned` 覆盖此前集合。复现：第一轮固定 B，第二轮 implement 未启动，第三轮默认 `start=pinned`，`expected_start` 返回基线 A。规格 §3 要求最近一次固定集合；应保留 B，显式 `--start baseline` 才回基线。
- **P2 — 记录入口在第一关之前可能写日志。** `recorder.py:37` 先取锁、修复残尾，之后才进入 `enter` 检查 `LANE_EXEC`。内存模拟同时设置空 `LANE_EXEC` 和锁拒绝，得到锁错误；锁空闲且有残尾时会先修复。应将第一关移到锁与修复之前。

恢复与第二轮边界：

- 未发现新增的正常转换死路；已有 intent 可凭同一 attempt_id 完成记录（`recorder.py:153`、424），未被误判为重复；pending verdict 的补落仍先于查表（`commands.py:149`）。驱动崩溃后的 `run` 仍须走人工关闭，不能借此重启旧步骤。
- **当前尚不适合直接作为第二轮基础。** 修复上述 P1/P2 后，第二轮必须保留纯判定、单轮单步一次 attempt、事件事实与判词不可改、否决集合永久保留、六关顺序、预算共用及产物先于 manifest 持久化；驱动只负责检出、启动、等待和记账。

验证：完成只读静态审查、三条原复现及新增内存复现；实跑 T22 纯转换表与四步搜索通过。未运行需要写临时文件的整套 60 项测试。

END OF REPORT