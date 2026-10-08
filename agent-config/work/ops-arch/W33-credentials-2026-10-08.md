# W-33 讨论材料：第 5 阶段收口（以凭证收口为主）

2026-10-08 晚，全部只读实测。凭证只看文件名和键名，没有读值。本文件给 Owner 讨论用，Owner 定之前不写道、不落地。

## 一、退出条件怎么读

第 5 阶段的退出条件是「对账 0 漂移；Agent 侧没有管理员凭证」。对账 10-08 已经 0 漂移。

「Agent 侧」按 ADR 议题 2 的原话包括：
- 这台 Mac 上的 Claude Code 和 Cursor 会话；
- 两台 mini 上替 Agent 干活的服务（remediation runner、Hermes）。

Owner 本人留着管理员凭证兜底。ADR 定的做法是「先把写收进动作目录，最后换只读」，并保留「Owner 批准执行这条命令」作为兜底动作。

## 二、现状

### Mac Pro（Claude / Cursor 会话）

| 凭证 | 权限 | 30 天实际使用 |
|---|---|---|
| `~/.kube/bifrost-k3s.yaml` | `system:admin`，`system:masters`（集群管理员） | 65 个会话做过写操作，按每次调用去重：`apply` 清单 407、`create` 清单 372（PipelineRun、Job 等）、`cp` 109、`run` 临时 Pod 103、`rollout restart` 79、`delete` 约 170（pod 70、job 56、pipelinerun、configmap、cronjob、pvc、namespace 等）、`patch` 约 15；另有 `exec` 2,764 次，其中 1,430 次是只读 `psql` |
| `~/.ssh/bifrost_deploy` | 登录 k3s 节点，**免密 sudo**（等于节点 root） | 节点调查、A7 滚动重启脚本 |
| infra `.env` 里 PROD / STG 的各级令牌，以及 MCP 的令牌文件 | PROD / STG 的 viewer、operator、admin | MCP 进程从令牌文件读；preflight 拦 Agent 读 admin 令牌和令牌文件 |
| `bifrost-platform/.env` | 本机 api 的 operator、admin 等令牌 | 本机开发用，也被部署脚本同步到 mini |

### 两台 mini

| 服务 | 用到的凭证 | 实际在做什么 | 30 天活动 |
|---|---|---|---|
| 环境（`env.sh`） | `KUBECONFIG` 指向同一份集群管理员 kubeconfig，**全局导出** | 下面每个服务都继承 | — |
| remediation runner（两台，:8781） | 管理员 kubeconfig、Cursor API key、本机 api 的 operator 令牌；`PLATFORM_API_URL` 指向 **STG**（`:30878`） | 接 `/run`，起修复 Agent | .50 0 次，.52 1 次 |
| hermes-gateway（.52，:8782） | 继承管理员 kubeconfig | 定时跑 `stale-pipeline-triage`：发现卡住的流水线就 **POST runner `/run` 起修复 Agent** | 定时在跑，153ms 结束 |
| Nous Hermes（.50，ai.hermes.gateway 与 dashboard） | DeepSeek API key（非空）；MCP 用本机 api 的 operator 令牌，连 **STG** | L2 Agent | 0 次会话（最近一次 08-08） |
| operator-plane（两台，:8783） | 自己按设计不碰集群；令牌来自 `config/.env`：本机 api 的 operator、admin，加 PROD viewer（10-08 加的） | 带外面、告警中转（.50） | 在用 |
| peer-watchdog | 两台互相 SSH | 互看 | 在用 |
| SSH | mini 的 `id_ed25519` | 登不上 k3s 节点（实测拒绝） | — |

`config/.env` 两台都有：本机 api 的 operator 和 admin 令牌、Cursor API key、ntfy 地址与主题、告警中转令牌、runner 令牌、PROD viewer 令牌、git-bridge 地址。这些是部署脚本每次部署时同步上去的。

## 三、关键发现

1. **Agent 的写操作主要靠集群管理员 kubeconfig。** 30 天约 1,100 次写，大头是 `apply` / `create` 清单，动作目录里没有对应的动作。动作目录现在有 31 条：B 10 条、C 10 条、D 11 条，覆盖发版、Argo 同步、节点 cordon、重启、扩缩容、备份等，**但没有「按 git 里某个提交 apply 清单」「从 CronJob 起一次 Job」「清理 Job」「起探针 Pod」这几类**。
2. **mini 上有一条无人看守的自动修复链**：.52 的 hermes-gateway 定时巡检 → runner `/run` → 带管理员 kubeconfig 和 Cursor key 的 Agent。30 天只触发过 1 次，但权限是全集群。W-32 已经删掉 Console 上的入口，这条链不受 W-32 影响。
3. **.50 的 Nous Hermes 处于休眠**：30 天 0 次会话，却配着 DeepSeek key 和 operator 令牌。之前 PHASE3-review 写「没有 LLM key」，不对，key 是有的。
4. **节点 SSH 密钥 `bifrost_deploy` 免密 sudo**：拿到它就等于每台节点的 root，权限和集群管理员一样大。
5. **② 可能不需要给 mini 发 PROD operator 令牌**：W-32 之后，plane 上只剩 3 个 operator 级路由：`PUT /patrol/skills/{id}/enable`、`POST /patrol/trigger/{id}`、`POST /patrol/webhook/{event}`。patrol 循环实际跑在 PROD workers，但 PROD api 把 `/patrol/*` 转发给了 .50 的 plane，而 .50 的 autopilot 是关的，所以 Console 看到的 patrol 状态其实是 .50 的空状态（10-08 实测 `last` 全空）。让 PROD 自己提供 `/patrol/*`、不再转发，比给 mini 发 operator 令牌更对。

## 四、分步方案

### 方案 A（推荐）：三步，按风险从低到高

1. **先清 mini**（一条道，加一次重部署）：
   - mini 删掉管理员 kubeconfig，`env.sh` 不再导出 `KUBECONFIG`；
   - 部署脚本不再同步 kubeconfig、admin 令牌、本机 operator 令牌、Cursor API key；
   - **撤掉 runner、.52 hermes-gateway 和那条定时巡检链**（30 天 1 次，后端在 W-32 时刻意留到这里定）；
   - .50 的 Nous Hermes：MCP 降为 viewer 令牌、改连 PROD，或者停掉（休眠中，第 6 阶段的 Agent 虚拟机由 W-31 重做）；
   - plane 只留 PROD viewer 和告警中转用的令牌；
   - PROD 不再把 `/patrol/*` 转发给 mini，由 workers 自己提供，这样 ② 就不用发 operator 令牌。
2. **把 Agent 的写收进动作目录**（platform 一条道）：按 30 天实测补 4–5 个通用动作，覆盖九成以上的写：
   - `apply_manifest`：参数是 git 里的路径加提交号；审批单里附服务端 dry-run 的 diff；PROD 命名空间和集群级对象是 C 级，dev / stg 是 B 级；
   - `create_job_from_cronjob`：B 级；
   - `delete_finished_jobs` / 清理类：B 级；
   - `run_probe_pod`：固定镜像白名单，B 级；
   - 兜底的 `owner_run_command`：D 级，审批单里写原样命令，Owner 批后由平台用管理员身份执行。

   数据库只读查询改用一个只读数据库账号，不再 `kubectl exec psql`。现有的 `role_matrix_reader` 只有连库权限，查不了数据，所以要新建账号（新增角色，要 Owner 批）。
3. **换只读**：
   - Mac 上的 Agent 改用只读 kubeconfig：ServiceAccount 绑 `view`，可读日志，读不了 Secret；
   - 管理员 kubeconfig 和 `bifrost_deploy` 搬到 Owner 专用的位置，preflight 拦 Agent 引用这两个路径；
   - 滚动重启这类必须动节点的，走第 2 步的动作或 Owner 亲手执行；
   - Cursor 同样只读。

做完满足退出条件。第 1 步可以马上做；第 2 步要新增动作，属于架构级改动（新增公开接口）；第 3 步依赖第 2 步。

### 方案 B：只清 mini，Mac 暂不动

只做 A 的第 1 步。mini 侧干净了，但 Mac 上的 Agent 还拿着管理员凭证，退出条件只满足一半，作为接受的风险记进 ADR。改动最小。

### 方案 C：Mac 立刻换只读，写操作全部交给 Owner 手工

A 的第 2 步不做，Agent 要写时把命令写给 Owner 去跑。按 30 天约 1,100 次写算，Owner 每天要手工执行几十条，摩擦太大，不推荐。

## 五、要 Owner 定的事

1. 「Agent 侧」是否包括这台 Mac 上的 Claude 和 Cursor 会话？（推荐：包括，按 ADR）
2. 选方案 A、B 还是 C？（推荐 A，第 1 步先做）
3. mini 上的 runner、.52 hermes-gateway、定时巡检链：撤，还是降权保留？（推荐撤）
4. .50 的 Nous Hermes：停，还是降为 viewer 并改连 PROD？（推荐停，等 W-31 的 Agent 虚拟机）
5. 如果选 A：第 2 步的通用动作清单（上面五个）够不够？兜底的 `owner_run_command` 要不要？
6. 管理员 kubeconfig 和 `bifrost_deploy` 在 Mac 上放在哪、怎么挡住 Agent？（推荐放到 Owner 专用目录，由 preflight 按路径拦；Owner 定过不要 Face ID / passkey）

## 六、W-33 其余两件（不需要讨论，随第一步一起做）

- **③** Console ⑥ 显示「待重启节点」（读 `/var/run/reboot-required`，或用节点的 kernel 版本对比已装版本），滚动重启做成审批动作（D 级，周末窗口规则留在脚本里）。补上第 3 阶段去向表里「Cluster 没有待重启信号」那一行。
- **④** ⑤ 页给 Research 和插件也显示 STG / PROD 两列版本，补上去向表的另一行「部分」。
