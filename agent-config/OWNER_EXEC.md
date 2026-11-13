# 要 Owner 级执行时怎么办（各家 Agent 通用）

2026-11-13 起生效。Owner 定的法：没有一件事是他必须回到电脑前才能做的。
`owner_run_command` 的卡，他在手机的 Console 上看命令、输入验证器的 6 位码、点一下，集群里的执行程序 `owner-exec` 就把这条命令跑掉，结果写回卡。不再需要他回终端。

程序：`bifrost-platform` `api/internal/ownerexec`。PROD 清单和边界：`k8s/owner-exec/README.md`。

## 什么时候用

先看有没有现成的平台动作（`CLAUDE.md` §3 的对照表：`plan_manifest` / `apply_manifest`、`rollout_restart_deployment`、`start_pipeline_run`……）。有就用它，那些不用 Owner 输码。
平台动作做不了、而你确实需要一条集群管理员级的命令时，才建 `owner_run_command` 的卡。它是通用的后路，不是常用的路。

## 怎么建卡

用平台的 `request_action`（PROD 平台；人批的单只在 `ops.bifrost.lan`）：

- `action`: `owner_run_command`
- `params.command`: 要执行的那一条命令的原文。批准的是这段文字的指纹，一个字都不能再改；要改就撤掉重建。
- `params.reason`: 一句话。
- `reason`（卡的理由）：**第一段写「批了会发生什么」**，用白话，写清会改什么、改完是什么样。然后写为什么平台动作做不了、你核对过什么、**哪些检查没做**。
- `rollback`: 出错怎么撤。撤不了就照实写撤不了。
- `work_id`、`requester_thread`: 填上，他要知道是哪条线在要。

他睡觉时不建单。不要替他批，不要调执行程序的接口，不要用浏览器去点：你没有他的码，也不该有。

## 命令在哪里跑、手里有什么

- 在集群里一个专用 Pod 的 `shell` 容器里，用 `bash -c` 跑，工作目录是一个空的临时目录。
- 身份是 `system:serviceaccount:bifrost-owner-exec:owner-exec`：所有资源的读、写、删。`kubectl` 不用带 kubeconfig，直接用。
- 有的工具：`bash`、`kubectl`（1.35）、`git`、`curl`、`python3`、`ssh` 客户端。没有别的。
- **手里没有任何仓库的检出**。命令必须自带内容：清单用 heredoc 写在命令里（`kubectl apply -f - <<'EOF' … EOF`）。`kubectl apply -k 某目录`、`bash scripts/…` 这类引用本机文件的命令在那里跑不了。
- **网络只通三处**：集群的 API 服务器、PROD 的 platform-api、DNS。`git clone`、`curl` 外网或 Gitea、连数据库，都不通。
- 环境变量是固定的几个，不带任何令牌。
- 最长跑 30 分钟，超时会被杀掉并记为失败。
- 卡上只存输出的**最后 2048 字节**。让命令的最后几行就是你要的结论；要看的东西多，就在命令里自己筛。

## 哪些命令会被拒

| 拒在哪 | 什么会被拒 | 你会看到什么 |
|---|---|---|
| 建卡时 | 命令在 apply 平台策略已经覆盖的清单路径 | 400，提示改用 `plan_manifest` / `apply_manifest` |
| 建卡时和认领时 | D10 锁着时，命令文字里点到签名策略 `no_d10_paths` 里的文件，或它上面两级以上的目录（worker 的 daemon 执行代码、`ib_operator`、`k8s/base/worker`、两个 daemon 补丁、`config/ops-context.yaml` 等） | 403 `tier: X`；已批的卡在认领时变成 failed |
| 建卡时 | 读不到 Owner 签名的发布策略 | 403 `tier: X`（宁可拒） |
| 执行时，集群入口 | 以执行身份写、删、exec、端口转发：三个 Trade 命名空间（`bifrost-prod` / `-stg` / `-dev`）里的任何东西；任何名叫 `daemon` 的 Deployment（含扩缩）；`data` 里的 `redis-ib` 和 IB 网关 | 命令自己报错，原话里有 `ValidatingAdmissionPolicy` 和 `D10`；卡记为 failed，退出码非 0 |
| 执行时，网络 | 直接连 Trade 网关、Monitor `/control/*`、Redis | 连接超时 |

交易、钱、D10 相关的一律不要往这里送，也不要想办法绕（换个身份、分几步、先删策略）。那些拒绝是 Owner 明确要的；绕过去的命令他在卡上看得见。

另外四条自己守住的：

- **不要让命令打印秘密**。卡的结果所有 Agent 都读得到。不要 `kubectl get secret -o yaml`，不要 `cat` 令牌。要核对 Secret 就只打印键名或长度。
  脱敏认得的是请求里登记的精确值和常见的令牌形状；写在引号里带空格的、被换行拆开的、只输出了一部分就超时的、经过编码或转义的，可能盖不住。所以这一条不能靠脱敏兜底。
- **不要让命令起后台进程**。不要用 `&`、`nohup`、`setsid` 之类把东西留在后台；卡结束或超时后它们可能还在跑，结果里看不到。
- 命令要能重跑不出事。执行程序如果中途没了，卡会变成 unknown（不知道跑没跑），由 Owner 判断；写命令时就让「再跑一次」是安全的。
- 一张卡一件事。别把几件不相干的事用 `&&` 串成一条让他一次批。

## 结果从哪读

用 `wait_for_request`（等）或 `get_request`（读）看这张卡：

- `status`: `pending`（还没批）→ `executed`（退出码 0）或 `failed`（退出码非 0、超时、被拒）。`approved` 表示他点了不带码的批准，命令还没跑。`unknown` 表示执行程序没报结果。
- `execution.exit_code`、`execution.output_tail`（脱敏后最多 2048 字节；超过完整缓冲上限时是一句固定的省略文字）、`execution.output_sha256`（有的时候，是结果接收时最终存下来的这段文字的 SHA-256，不是原始输出的哈希）、`execution.duration_ms`、`execution.executor_id`（`owner-exec:<pod>` 表示是执行程序跑的）。这个行为在 STG 已生效，PROD 的执行口要等换镜像之后才生效。
- `result.message` 里那句「Run: bash scripts/owner/…」是旧文字，对已经由执行程序跑完的卡不适用，以 `status` 和 `execution` 为准（已记债）。

读到结果后自己核对它真的生效了（对象在不在、Pod 起没起），再往下走。`executed` 只说明命令退出码是 0。

## 发布之后的核对

执行口复核类的修复改的是 runner 和 shell 里的代码。PROD 的执行口不随平台发布换镜像，所以每次有这类改动上了 PROD 平台之后，都要只读核对三处镜像的完整摘要是否一致：PROD 的 platform-api、执行口的 runner、执行口的 shell。不一致就说明执行口还是旧的，修复在 PROD 没生效，要另走一张执行卡去换。STG 的执行口跟着平台发布自动换。

带只读身份运行下面这一条命令，读三处正在运行的容器的完整 `imageID`（滚动期间可能有多行，逐行核对）：

```bash
kubectl get pods -A -l 'app.kubernetes.io/name in (platform-api,owner-exec)' -o json | python3 -c 'import json,sys; data=json.load(sys.stdin); [print(p["metadata"]["namespace"], p["metadata"]["name"], c["name"], c.get("imageID", "MISSING")) for p in data["items"] for c in p.get("status", {}).get("containerStatuses", []) if (p["metadata"]["namespace"] == "bifrost-platform-prod" and c["name"] == "platform-api") or (p["metadata"]["namespace"] == "bifrost-owner-exec" and c["name"] in ("runner", "shell"))]'
```

三处有任何一处没输出或没有摘要，都算没核对完，不能当作一致。

## 他那一侧是什么样

卡上有一块「Approve and run here」：命令原文、6 位码输入框、一个按钮。码错了卡保持 pending，什么都不发生；连错 5 次锁 15 分钟。同一个码只能用一次。执行程序重启后 90 秒内不收码。
批过但没跑的卡（`approved`），24 小时内他可以在同一张卡上输码点 Run。

## 还有哪些情况要他回电脑

1. **集群或 Console 自己挂了**。执行程序在集群里，跟着没了。这时用卡上不带码的 Approve，加他终端里的执行脚本（老路一直保留）。
2. **命令必须用到他那台 Mac 上的东西**：本机文件、本机的凭据、局域网里集群够不着的机器。在 Mac 上执行的那一种还没做。
3. **重签发布策略、解冻**（`release.sh policy sign` / `unfreeze`）：签名用的钥匙在他的电脑上。
4. **重放钥匙**：换手机、验证器丢了、或要升级执行程序自己的清单时，重跑 `scripts/owner-exec/enroll.sh`。执行程序换镜像不用回电脑，可以走一张它自己执行的卡。
5. **交易相关的一切**。这扇门对它们是关着的，D10 解锁也不会自动打开。

碰到第 1、2 种以外、却发现非他回电脑不可的事，当作系统的缺口报给统筹，不要默默给他派一条终端命令。
