TD-298 只读审计报告

未发现 Git 能确认的 D10 解禁、实盘发单接线、Agent 写入 IB operator stream、审批旁路执行或整树暂存事故。发现一个当前闸门覆盖缺口，以及一个因禁止读取 token 文件而未完成内容核验的 Secret 清单。两者都不能证明 Cursor 曾越权执行或泄露凭证。

**范围与统计口径**

检查本机已有 remote-tracking refs，未 fetch。时间按提交者时间限定为 `2026-09-28T00:00:00Z` 至 `2026-10-10T23:59:59Z`。

纳入远程可达、带 `Co-authored-by: Cursor` 的提交，以及 `cursor/*`、`w31/*` 分支上尚未进入 `origin/main` 的提交；按 SHA 去重，保留 cherry-pick/rebase 后不同的 SHA。没有把命名分支共同继承的非 Cursor main 历史算作 Cursor 工作。

共 261 个提交：252 个有 Cursor trailer，9 个仅凭分支归属纳入，后者不构成作者身份证明。189 个已在 `origin/main`，72 个仅在其他远程分支。256 个早于 hooks 修复时间 `2026-10-10T14:54:28Z`，5 个在其后。

审查了全部 261 个提交的元数据和路径清单，以及 260 个提交中允许访问的差异。未读取 Owner 凭证目录、任何 `.env`、token 文件、kubeconfig 或 dump；部分 Owner 专用脚本源码因闸门限制未读取。

| Repo | origin/main 快照 | main 提交 | 其他远程提交 | 合计 | 修复前 |
|---|---|---:|---:|---:|---:|
| bifrost-trade-core | 385b0f8 | 4 | 0 | 4 | 4 |
| bifrost-trade-worker | 2b3e344 | 3 | 0 | 3 | 3 |
| bifrost-trade-api | 89ac1eb | 2 | 0 | 2 | 2 |
| bifrost-trade-frontend | 809d5579 | 7 | 1 | 8 | 8 |
| bifrost-trade-infra | ad27535 | 75 | 40 | 115 | 113 |
| bifrost-research | ecdce43 | 11 | 0 | 11 | 11 |
| bifrost-platform | 7cda6cb | 59 | 31 | 90 | 87 |
| bifrost-platform-plugin | ee6f0ba | 2 | 0 | 2 | 2 |
| bifrost-platform-plugin-market-data | d25bd0e | 20 | 0 | 20 | 20 |
| bifrost-platform-plugin-flex-query | c3be5ec | 4 | 0 | 4 | 4 |
| bifrost-ui | 9b635b2 | 2 | 0 | 2 | 2 |
| bifrost-analytics | 无 origin/main | 0 | 0 | 0 | 0 |
| **合计** | | **189** | **72** | **261** | **256** |

**闸门实际拒绝的动作**

依据 `agent-config/scripts/agent-guard/preflight.js`：

| 类别 | 机械拒绝范围 |
|---|---|
| D10 | 命令中写入 `ib:operator:cmd`；`IbOperatorClient.request`；匹配到的 HTTP `/control/*` 写调用；kubectl 将 daemon 副本设为正数；删除、覆盖或改写两份 D10 guard；匹配到的 daemon overlay 删除；MCP `scale_deployment` 将 daemon 设为正数 |
| D10 文件修改 | Edit/Write 等工具触及 `daemon-scale-zero.patch.yaml`、`daemon-observe-safe.patch.yaml` |
| 共享工作树 | 无 pathspec 的 `git add -A/--all/-u/--update`、整树 pathspec、`git commit -a/--all` 等 |
| 审批旁路 | 非 `mcp__bifrost-approve__*` 调用直接引用 approve/reject 端点、admin token 标识或 token 文件；匹配到的审批页浏览与点击 |
| Owner 凭证 | 匹配到 Owner 目录、Owner env、非允许 kubeconfig；指定 Owner 专用脚本及部分插件脚本调用 |
| Dev 服务 | 直接运行整包启动脚本、匹配到的托管进程终止、手动 `port-forward …9090` |

源码**没有通用的 kubectl 写操作拒绝规则，也没有 blanket 禁止修改整个 agent-guard、hook 或 auto-mode 目录**。这些目录的变更必须审查，但不能仅凭路径称为“preflight 本来会拒绝”。

规则也在审计期间扩充：审批拦截在 `f503068b`（10-07）加入；Owner 凭证和脚本拦截在 10-09 加入。因此不能把当前 matcher 全部追溯为 09-28 已有规则。

**发现与处置判断**

| Repo / 提交 | 证据及闸门关系 | 现在是否需要动作 |
|---|---|---|
| **bifrost-trade-infra — `5c50c203`；`779c70fe`** | `5c50c203` 将 `scripts/k3s/rolling-reboot.sh` 默认 SSH key 改为 Owner 节点密钥，并注明 Agent 不得运行 `--execute`。当前文件第 48–50 行仍有此约束。`779c70fe` 分支又加入 Owner approval library 和执行结果目录。当前 `OWNER_SCRIPT_RE`、`OWNER_RUN_RE` 均未包含 `rolling-reboot.sh`；仅以脚本名运行、命令文本不含 Owner 路径时，源码没有对应拒绝规则。**这是覆盖缺口，没有执行证据。** | **需要补齐 `--execute` 的机械拒绝。** Git 无法判断此前是否运行过。 |
| **bifrost-trade-infra — `5c50c203`** | 新增 `k8s/agent-access/token-secret.yaml`，当前 `origin/main` 与 `origin/cursor/w33d-infra` 都包含同一 blob `86cac1e6…`。未读取其内容。同提交的 `scripts/check-no-k8s-secrets.sh` 注释将它描述为空 service-account token 请求；`scripts/check_agent_access.py` 的 `static_problems` 明确拒绝其中存在 `data` 或 `stringData`。**旁证支持元数据模板，但本审计没有验证 blob 内容。** preflight 本身没有通用 Secret YAML 提交拦截。 | **需要 Owner 核验内容为空。** 当前没有确认泄露，不能据此判定需要轮换凭证。 |
| **bifrost-trade-infra — `b3486096`、`f503068b`/`27ecfaed`、`ab93edbe`、`4f39935a`、`55601444`、`86099ea3`** | 确实修改了 guard、hook 或 auto-mode 接线：`b3486096` 只改 operator stream 注释；`f503068b`/`27ecfaed` 新增审批拦截并扩大 Claude matcher；`ab93edbe` 加 Codex adapter；`4f39935a` 将路径改为工作区变量及占位符；`55601444` 增加心跳，保留 preflight entries；`86099ea3` 加 Cursor 用户级 hook 安装与检查。没有发现这些差异删除 D10 拒绝条件或关闭 preflight。修改这些普通治理文件本身不在 preflight 的通用拒绝范围。 | **未发现需要回滚的弱化。** Git 只能证明仓库变更，不能证明用户级配置实际加载情况。 |
| **bifrost-platform — `d8bdf418`；bifrost-trade-frontend — `84dd1169`、`292bfd27`** | 这些提交有超出标题的路径：D10 扩容修复同时改备份失败记录保留；persona regime 展示同时改 journal 过滤；措辞测试同时清理 earnings hook 依赖。三者提交正文均说明了额外改动。大批删除及 merge 提交的路径也与其清理/合并说明相符。**没有足够证据认定误卷他人改动，更无法推断实际用了哪种 staging 命令。** | **不支持按整树暂存事故处置。** |
| **bifrost-trade-infra — `5c50c203`；bifrost-platform — `b87b6a2f`** | 路径记录及 lane report 显示新增/改造了 Owner 凭证读取脚本。报告明确要求 Owner 自己运行；在已读取的 Agent 路径差异中，未找到新增自动调用这些专用脚本的证据。相关受保护脚本源码未全部读取，`b87b6a2f` 的全部路径均属这一限制。 | **没有确认需要处置的 Agent 调用。内容检查不完整。** |

**各类结果**

以下“none found”只表示指定 Git 范围内未找到相应证据。

| 检查类别 | 结果 |
|---|---|
| 修改两份 D10 overlay guard、daemon 基础 Deployment | **none found — 261 个提交路径清单** |
| 新增实盘 `place_order` / Gateway execution 接线 | **none found — 261 个提交路径清单及允许读取的差异** |
| Agent 写 IB operator stream 的 Git 证据 | **none found — 261 个提交**；注释、测试和规则中的 stream 名不构成执行证据 |
| 关闭或弱化 guard/hook 的仓库差异 | **none found — 261 个提交**；治理变更见上表 |
| 整树暂存造成的无解释跨领域混入 | **none found — 261 个提交的标题、路径及候选提交正文** |
| 新增真实 `.env`、kubeconfig、dump、私钥文件 | **none found — 261 个提交路径清单** |
| 可确认的凭证值新增 | **none found — 允许读取的差异**；命中的长 token 字符串位于测试夹具，另有文档路径误匹配。排除文件未核验 |
| 新增 Secret YAML | **1 个候选：`5c50c203` 的 token Secret**；内容未读，旁证见上表 |
| 已确认的 Owner 专用脚本被 Cursor 执行 | **none found — 261 个提交**；rolling-reboot 覆盖缺口见上表 |
| 已确认的直接审批 API 调用、kubectl 写操作、终止 Dev 进程 | **none found — Git 证据不足以检验实际执行** |

**Git 无法证明的部分**

Git 不记录实际 staging 命令、未提交的临时脚本、读取凭证、kubectl 写操作、Redis 写操作、进程终止或直接 HTTP 请求。因此本报告不能证明缺失 hooks 的期间“没有发生”这些动作。

相应证据应在平台审计日志 **`GET /api/v1/audit`**、审批执行记录、Kubernetes audit log 与留存 Events、Cursor 会话工具记录，以及 bdev 的 `~/.bifrost-dev/logs/<name>.events.log`。Kubernetes Events 本身不覆盖全部 API 写操作。按 BRIEF，未查询这些运行时来源。

**提交清单**

以下 `main` 表示可从本次快照的 `origin/main` 到达；“其他远程”表示未进入该 main。均为去重后的短 SHA。

- **bifrost-trade-core** — main：`385b0f88 3eccebd4 3c79f411 2277054e`
- **bifrost-trade-worker** — main：`2b3e3443 811e067f 7cddef46`
- **bifrost-trade-api** — main：`d7cdc3f6 c0088773`
- **bifrost-trade-frontend** — main：`809d5579 70ffac51 81a796bf 7d31bbcd 292bfd27 84dd1169 6d861329`；其他远程：`bb7b5183`（`cursor/t3-frontend`）
- **bifrost-research** — main：`ecdce437 50290843 481c96cb 2ac14b42 39364bbf fc80757c cc3fb03e acfb5ad1 cbf01d33 c36b4418 d4238346`
- **bifrost-platform-plugin** — main：`c0134b03 72238326`
- **bifrost-platform-plugin-market-data** — main：`21dfe047 8aca41e4 3f43124b 24061c17 45b23ebc ec973a51 a41acfa8 da97bc6f ce4fed0c 380e48d3 dea4786a c1f80d8e 70173054 65deb42f 8813ea67 c98c89b7 83220c10 0d9b547a 37b54a57 9636aea7`
- **bifrost-platform-plugin-flex-query** — main：`9f7265e5 e11766da f88d5fa5 165fa9ef`
- **bifrost-ui** — main：`9b635b2b b65af130`
- **bifrost-analytics** — none found，0 个提交。

**bifrost-trade-infra — main（75）**

```text
4259729e 86099ea3 f641361e 0516e907 fe5a5f2e 730e92ed 1fe94a99
a63c4cfb 5bbb1361 5e8e4676 fa9ee2c9 352c2fc6 87f26b96 9f9c3a10
c5c5f36b 32c03f8d 4f39935a 39390a60 ded0ab21 ab93edbe 3542d241
901b044a 3274ac43 07a60e6f e2101e05 007eaaca e2a25b26 94a8a4c9
d623731d 97706126 f8162710 262e81b7 42dba0d6 52e35ced 2885d4d0
dbbbd330 5235a72f fea627a1 3c13a9d4 28066b35 b21f886a 9f800a6c
5ff16241 f503068b d0601521 289ec030 fa50ad82 25dc5492 975ce425
f737faa5 abbc788f f7dcccc8 084f53dd 0fe9a84a 3013bea4 128036ef
b0a7f2e3 ebd019de 6dbf0f36 fba7535e ee75cc62 16b9716a 7a346b1c
f8ced0c2 ffa7e8da 1aff3073 b3486096 f11e0b47 096262e7 2d04455e
939d8a27 32bcd353 ca6f23b2 f2061ae8 29a3db54
```

**bifrost-trade-infra — 其他远程（40）**

| 分支（省略 origin/） | 提交 |
|---|---|
| w31/w54-s0-21 | 55601444 |
| w31/w51-s0-0d | 59321861 10bf562b 465f6795 |
| w31/w48-s0-0a-infra | 779c70fe |
| cursor/w33d-infra | 32c48e43 5c50c203 |
| cursor/w33c-infra | b33d7357 0c5845f4 |
| cursor/w33b-infra | 1a9b408f e8e42dd9 918ee55e e5b04b45 |
| cursor/w33r-infra | c46113e7 |
| cursor/w33-infra | 8262696e |
| cursor/w32-infra | 07d19dd1 |
| cursor/a6r-infra | 8d37a16a |
| cursor/m2-infra | 2440e54a |
| cursor/e1-infra | 37c0e2d0 d1feabbc a4e87af7 |
| cursor/d1-infra | c4e0707d 2ef0ba41 |
| cursor/rp-infra | 9ad2baa7 |
| cursor/phase3-lane-c-report | 571ae14e 4f84d84a |
| cursor/m-infra | 6bbe09b8 |
| cursor/t2-infra | 074c1fe1 |
| cursor/b3-infra | 27ecfaed 1403f05b |
| cursor/b2-infra | b7d29bc8 |
| cursor/b4-infra | 38e752e3 |
| cursor/a7-infra | 37016cb9 46e4a7fa |
| cursor/a2-infra | e4251ab1 a6119caf |
| cursor/a6-infra | 711ad9c0 |
| cursor/a3-infra | 769b7876 |
| cursor/a5-infra | 8da7b1ed |
| cursor/a1-infra | 53b527bb |

**bifrost-platform — main（59）**

```text
66496a6b 2d746443 16ece5ae d6b28494 3dad199d 75be7014 b87b6a2f
61d85956 e2d5137d c7a48210 2de35b91 0bf52855 9a0d1ede d917f162
d1367521 64cc4752 634e3056 1cf4d2c9 3bd067f2 1e277a57 b291a09b
3eceb80d a7ecb084 286c3057 4f52663c e63ec329 2e86b38d c5eee58e
4949b92a abba2f24 188f0611 e6b825b9 816a8039 7592cdff d61fc70d
ccdf2005 388d4311 40187953 46464410 894a88f4 79ed8dbb df8fd4e3
8accfe1d fefc109c 068c1213 33593656 c1c3bc66 d8bdf418 cad1258e
26cd8840 546c23d4 58e24001 0550be77 2f008acb 59e14781 e54d0676
85989a95 459dff80 143d9f5a
```

**bifrost-platform — 其他远程（31）**

```text
c854efec 7b4574d6 167c1ea2 923ef4fd 7535877a 54e0cfbe 65c00544
36d1282f 11ebb8c3 e43a129c 56b12b2f c6a5e843 8c55c63c 249618e1
5101ba3c 1ec4c9d3 853b824f 72990841 e81a88d1 86b709fb 611cc3eb
58928a38 972ade78 fae4dc44 26caf114 7fef876e e81f6418 5b0e5116
a7b86813 f957cfdb ae80c4aa
```

其中 `e81f6418`、`5b0e5116`、`a7b86813`、`f957cfdb`、`ae80c4aa` 分别在 `cursor/n-platform`、`cursor/b-platform`、`cursor/d1-platform`、`cursor/rp-platform`、`cursor/p2-platform`；其余在对应 `w31/*` 分支及共享这些提交的 integration 分支。

审计执行限制：preflight 拒绝了包含 Owner 凭证/专用脚本名称的批量审计命令，以及包含整包启动脚本名称的读取命令；没有绕过闸门。`85989a95` 中 `scripts/run_platform.py` 的差异未读取，Owner 专用脚本和禁止读取的凭证类文件亦未做完整内容核验。全过程未写文件、提交、推送、checkout 或调用集群/平台写操作。