# 复核 542 的回应（TD-432 切法第 1 稿 → 第 2 稿）

被复核：infra `w31/td432-cut` 4d669f3e、platform `w31/td432-gitea-reader`。第 2 稿在同一分支，提交见下。逐条对照在切法 §0。

| 复核 | 结论 | 处理 |
|---|---|---|
| A1 名字白名单要管 CREATE | 接受 | `k8s/platform-rbac/46-cicd-configmaps.yaml`（CREATE/UPDATE/DELETE，按对象名，不看标签） |
| A2 PROD 能改 `cicd` 的 Deployment | 接受 | `47-platform-deployments.yaml`：平台身份只许改副本数和 `restartedAt` |
| A3 平台建的 run 可选高权限身份；参数进 shell | 接受 | `40-admission.yaml`：身份按（流水线, 步骤）白名单、TaskRun 身份、参数字符白名单、`giteaBase`/`url` 钉死；平台 `0150b811` 拒绝非分支非标签的 Dockerfile 刷新。登记 TD-435、TD-436 |
| A4 S7 漏 PROD `check-source` | 接受 | S7 加；S8 前 `git grep` 核对无引用 |
| A5 S8 要吊销旧令牌 | 接受 | S8 改为吊销并逐个试旧令牌被拒 |
| A6 分页上限静默成功 | 接受 | 读到空页才停、第 40 页未完拒绝；`replace` 模式；7 条测试（`916f5c42`） |
| TD-434 验收太窄 | 接受 | `--live` 对两个平台身份试 9 个外部 ConfigMap（拒）和自己的 5 类（放行）；`tekton-deliver` 写 Dockerfile（放行）；单测断言这些用例都生成了 |
| B 交付边界与未核实项 | 接受 | S5 拆两步（Argo 自动同步：overlay 推上即生效，挂载 `optional`，核对文件可读）；S7 查 `tekton.dev/git-0` 与凭证初始化目录、凭证只给 git 子进程；S8 等在途任务、把「无人能读」收窄成可证明的身份范围；4.1 闸门写成明确条件；§5 更新 `.git` 进构建阶段的发现 |
| B Owner 时间 | 接受 | 改为 6 次约 70 分钟（理想操作时间，不含排障） |
| C RBAC 防线只认 ServiceAccount | 接受 | 扫整个 `k8s/`，认 Group 与 `system:serviceaccount:` User；阳性对照（去掉组解析后测试失败） |
| C 删了重来 / 回退说明 | 接受 | 「删了重来」只限 S1，之后用 `replace`；回退写明只对旧镜像有用 |
| C 行数、`tekton-deliver` 建 run | 接受 | 改正 |
| C 本机 bdev | 接受 | §2.1 写明预期行为，不恢复管理员回退 |

新增未决：§1.4 第 10 行（执行任务推的分支经 Dockerfile 刷新影响 STG 构建），§6 第 4 条推荐只认 `main` 和发布标签。

验证：`scripts/test_*.py` 90 条、`test_access_checks.py` + `test_platform_rbac_secrets.py` + `gitea/test_put_reader_token.py` 22 条通过；`check_admission_guards.py` 静态 ok；`kubectl kustomize k8s/platform-rbac` 渲染 8 条策略。CEL 没在本地编译，`--live` 没跑（要 Owner 的身份）。
