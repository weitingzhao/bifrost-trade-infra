# 复核 548 的回应（TD-432 第一批的补丁）

| 复核 | 结论 | 处理 |
|---|---|---|
| R1 比较的两侧处理阶段不同：checker 原地删掉已存在的 Namespace，main 头一侧没删，渲染未变的旧 main 提交被误拒 | 接受 | 渲染后、checker 之前把候选结果另存一份，和 main 头的未处理渲染比较；apply 仍用 checker 处理过的文件。复核的离线探针改写成仓库测试 `scripts/test_apply_manifest_pipeline.py`（13 种情形），把比较改回旧写法时它失败 |
| A 既有的 `kubectl create … \| jq` 管道 | 接受 | 拆成两步，kubectl 失败即停 |
| D 操作单「任何非零退出码都停」、第 2 节旧概述 | 接受 | 改正 |
| awk 解析依赖当前 YAML 排版 | 接受为现状 | 当前文件无首尾斜杠、无引号；策略文件由 `check_actuation_policy.py` 守格式 |

验证：`scripts/test_*.py` 与 `gitea/test_put_reader_token.py` 共 105 条通过；复核 548 的离线探针对新流水线 15 种情形全部符合预期（C 级旧 main 含 Namespace 放行，内容变化拒绝）；四个 Argo 自动同步的 overlay 在本批前后渲染逐字节相同。
