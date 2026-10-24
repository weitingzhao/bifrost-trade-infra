# 复核 545 的回应（TD-432 切法第 2 稿 → 第 3 稿）

被复核：infra `w31/td432-cut` c735a215、platform `w31/td432-gitea-reader` 0150b811。第 3 稿在分支 `w31/td432-land-a`（第一批进 main 的内容，从 infra main 切出），逐条对照在切法 §0。

| 复核 | 结论 | 处理 |
|---|---|---|
| F1 applier 的输入不限来源 | 接受 | 受信的应用流水线按渲染出的级别拒：C、D 级 `apply` 必须 `requireOnMain=true`。准入不加参数组合规则：级别只有流水线自己算得出来 |
| F2 Pod 模板改主机解析 | 接受 | 三处 Pod 模板只许 `nodeSelector`、`tolerations`、`affinity`；CRD 有类型，其余 14 个字段逐个要求不出现；`--live` 报 CRD 新增字段 |
| F3 没有放行用例、拒绝不核来源 | 接受 | Deployment 整对象更新（replace）11 例含 3 例放行；拒绝必须带被测策略名；求值出错算失败；交付 15 步放行、CI 8 步拒绝、参数 11 例；测试加「被别的策略拒」的阳性对照 |
| F4 Deployment 其余字段 | 接受 | 冻住五个发布设置、自身标签；自身注解只许 `bifrost.dev/session-desired-replicas` |
| F5 参数收窄合法 ref | 接受 | 字母（含非 ASCII）、数字、`._/:@+=-`，首字符不能是 `-` |
| D 顺序 | 接受 | 准入挪到操作单第 2 节，撤 STG 绑定在其后 |
| D 类型检查 | 部分接受 | 读 `status.typeChecking`；线上现有策略已有告警，运行时按无类型对象求值、告警不改行为，所以不把「无告警」作为应用的前提，改为应用后读、新表达式的告警逐条判断。不加 Warn 阶段：放行用例已覆盖平台的每类请求，`--live` 紧接应用跑，出错即删绑定 |
| D 防线 2 文字、S8 令牌集合、`rotate-admin-token.sh` 读旧 Secret | 接受 | 改正 |
| D §6 #4 Dockerfile 刷新只认 main 和发布标签 | 未定 | 仍是 Owner 的决定（推荐只认 main 和发布标签），不挡第 1、2 节 |

另：本轮把 TD-435 的第二个入口（CI webhook 不核对发送方，`after` 进 `revision`）的过滤放进同一批，`scripts/test_ci_trigger_filters.py` 守住。

验证：`scripts/test_*.py` 与 `gitea/test_put_reader_token.py` 共 101 条通过；`apply-manifest-check_test.sh` 通过；`check_admission_guards.py` 静态 ok，去掉一处 `hostAliases` 要求或 F1 那段拒绝时静态检查报 FAIL；`kubectl kustomize k8s/platform-rbac` 渲染 8 条策略。CEL 没编译，`--live` 没跑。
