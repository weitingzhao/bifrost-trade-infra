VERDICT: fix first

复核提交 `aa61184`（相对 `2640059`）；**仍有 1 项 P1，未发现本 diff 的其他 P1/P2。**

- **P1：事件侧基线 tree 缺失时仍可错误放行。** `agent-config/scripts/lane/decide.py:256`、`:269`、`:279` 和 `:363` 都以 `if exp_tree` 决定是否比较树号。
  正常仓库登记只包含 target_sha（`agent-config/scripts/lane/commands.py:59`），因此 `query.py:185` 生成的基线 tree 为 None。
  内存复现：保持正确 commit，把 implement 的实际 tree、expected.tree、consumed.tree 分别改成三个不同的非空字符串，`decide` 仍返回 `passed`。
  首轮、`--start baseline` 后均可复现；context 的启动 tree 与 pinned tree 不同也可通过。应补全事件侧权威基线 tree，并拒绝缺失值，取消条件性比较。

前轮三项结论：

- **证据完整性：未完全关闭。** verify/review 错误启动 tree、逐项删除字段、删除 consumed 集合均已拒绝；但上述基线树号漏洞仍在。
- **空 pinned 覆盖旧起点：已关闭。** `query.py:161`；复现第二轮 pinned 为空，第三轮保留第一轮 commit/tree，显式 baseline 则回到基线。
- **gate 1 顺序：已关闭。** `recorder.py:123` → `commands.py:121`。内存模拟锁拒绝和残尾：LANE_EXEC 为空时，三个记录入口均先拒绝，锁与修复调用为零，残尾未变。

形状探测：重跑 131 个生成反例，均未通过；额外仓库、错误类型（包括 `"true"`、1、0）、None、双方 tree=None、空仓库集合均被拒绝。
重复仓库名仍会被 JSON/CLI 字典覆盖；这是既有解析行为，本 diff 未新增重复检测。仓库内部额外字段也仍允许，因此并非严格封闭字段形状。

正常首轮、context 和 baseline 重启的合成路径可通过，未发现合法路径回归。旧事件缺字段会被拒绝；按简报尚未投入使用，无现存迁移需求。
验证全程只读、禁用字节码写入；未运行需要落盘的完整测试套件。

目前不能视为第二轮的可靠基础；先关闭上述 P1，再推进检出、bundle、驱动和九个命令。

END OF REPORT