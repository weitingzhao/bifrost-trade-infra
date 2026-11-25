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

这一节是全仓库唯一的清单。除第 5 条外，每一条都是系统的缺陷，不是规矩（Owner 2026-11-13：要他动手的事手机上要办得完，LAW-6）。

1. **集群或 Console 自己挂了**。执行程序在集群里，跟着没了。这时用卡上不带码的 Approve，加他终端里的执行脚本（老路一直保留）。
2. **命令必须用到他那台 Mac 上的东西**：本机文件、本机的凭据、局域网里集群够不着的机器。在 Mac 上执行的那一种还没做（TD-578）。
3. **解冻**（`release.sh unfreeze`）：现在还只能用他电脑上那把钥匙签。集群里的第二把钥匙平台也认解冻的签名，但带解冻文字的执行卡还没做（TD-578）。重签发布策略、重签运行时规则已经不用回电脑，见下面两节。
4. **重放钥匙**：换手机、验证器丢了、或要升级执行程序自己的清单时，重跑 `scripts/owner-exec/enroll.sh`。执行程序换镜像不用回电脑，可以走一张它自己执行的卡。
5. **交易相关的一切**。这扇门对它们是关着的，D10 解锁也不会自动打开。
6. **一次性库步骤**（`scripts/release/db-steps.d/` 的 `commit:` 行）：卡批完后，命令现在还是他在电脑上跑。执行口能不能跑这类命令没验证过（TD-578）。
7. **装进集群的自举清单**（`docs/RELEASE.md` 里写明不走 apply 流水线的那几个：冻结检查的 Task、PROD 平台流水线的检查）：现在还是他在电脑上 apply。能不能改成一张带清单的执行卡没验证过（TD-578）。
8. **PROD 的 agentrt 迁移 Job：已不用回电脑（2026-11-21 起）**。都由平台的 `run_agentrt_migration` 跑：只增不删的由 Agent 用 `run_agentrt_migration` 直接调，签名规则放行（Owner 2026-11-18，LAW-6）；会删表等不在那一类的，同一个动作建成 C 级卡，Owner 在 Console 批，平台自己起 Job（第一次：#671，0042 `DROP TABLE`，结果 `applied=[42]`）。号码留着是为了别处按号引用的条目不错位。
9. **应用 auto mode 规则**（`apply-auto-mode.sh`）：写的是他本机的设置文件（TD-578）。

碰到这张清单以外、却发现非他回电脑不可的事，当作系统的缺口报给统筹并登记进 `TECH_DEBT.md`，不要默默给他派一条终端命令。

## 要进某台集群节点（2026-11-18 起，LAW-6）

用途：Owner 不在电脑前，也能让一张卡在某一台集群节点上读东西或做事，不用他回去。工具是 `scripts/owner-exec/node-run.sh`，带版本。**它是生成器，不执行任何东西**：执行口没有仓库检出，卡里没法调用仓库里的脚本，所以它在本地拼出一段完整、自包含的命令全文，你把这段文字放进 `owner_run_command`，Owner 读卡、输验证码，执行口跑。卡首行带 `node-run v1`、档位、节点和运行部分的 sha256。没有新的长期凭证，没有常驻的特权进程，没有 SSH 密钥：每次一个 Pod、钉一个节点、有超时、跑完删。

```bash
bash scripts/owner-exec/node-run.sh render --tier device --node ubt-k3s-05 --recipe nvme-smart
bash scripts/owner-exec/node-run.sh render --tier host --node <节点> --cmd '<写死的命令>' --pods-file <该节点存活 Pod 的清单>
bash scripts/owner-exec/node-run.sh selftest   # 不需要集群
```

引用哈希时用平台口径：命令全文去掉首尾空白后的 sha256（命令文件末尾的换行平台会去掉，卡面哈希和平台记的 `command_sha256` 才一致）。

**两档，能用设备档或平台动作就不用主机档。**

| | 设备只读档 | 主机档 |
|---|---|---|
| 能做什么 | 只能跑命名的固定配方（现在只有 `nvme-smart`：对 `/dev/nvme0` 发 Identify 和 SMART 日志两个 NVMe 管理命令，读 PCIe 链路，不打印序列号），不接受自由命令 | 自由命令，在该节点的主机命名空间里（hostPID + nsenter）以 root 跑 |
| Pod | 特权（只为打开设备节点）；无 hostPID、hostNetwork、hostIPC、hostPath、chroot、nsenter；不挂令牌，无 env、无 volume | 同上，但开 hostPID 并 nsenter 进 PID 1 的命名空间 |
| 卡首行 | 「DEVICE TIER…」 | **「THIS IS THE NODE'S ROOT…」** |
| 生成时 | 节点名只许集群节点；配方名要在白名单里 | 同左；**必须给 `--pods-file`，卡面前几行列出该节点上存活的 Trade、redis-ib、IB 网关、daemon Pod**，并写明 D10 不解除；命令文本命中字面关卡就拒绝生成 |
| 运行时 | 节点必须存在且 Ready（关机的 gpu-server 会被拒，先用平台的唤醒动作） | 同左，并再打印一次该节点上存活的 Trade/IB Pod |

**说清楚的边界**

1. **设备档是特权 Pod。** 它能看到该节点的全部设备、带 CAP_SYS_ADMIN，原则上能挂载宿主盘（可读可写）、借盘上的节点凭证以节点身份读调度到该节点的 Pod 引用的 Secret。限制它只读的是配方文本，不是内核。控制靠「命令写死 + 全文在卡上 + Owner 读卡再输码」。不要写「它读不了任何 Secret」。
2. **主机档就是该节点的 root。** Owner 2026-11-18 决定它可以用在有 Trade 或 IB 服务的节点（逐卡由他读卡输码；RULE，执行 CORE-1、LAW-6），所以工具不再因节点上有这些 Pod 而拒绝，只把它们列在卡面前几行。D10 不解除：不下单、不改交易服务、不动这些 Pod 及其卷和 Secret。
3. **命令文本的字面关卡是绊线，不是栅栏。** 它拦 `bifrost-prod/stg/dev`、`redis-ib`、`ib-gateway`、`ib:operator`、`daemon`、`kubernetes.io~secret`、`/var/lib/kubelet/pods`、`/run/secrets`、`serviceaccount/token` 这些字面，拦的是手滑。root 命令可以把同样的意思拼成任何正则看不出来的写法。真正的控制是 Owner 读卡；卡要短到手机上读得完。
4. **不在范围内：** 集群外的机器（Mac mini、NAS、ubt-k3s-06）。这条路是集群里的 Pod，够不着它们。
5. **验过什么：** 设备档在 ubt-k3s-05 上真跑过一次（卡 #602，2026-11-18，exit 0，执行结果的 `command_sha256` 与卡面一致）。主机档**从未在集群上跑过**。`selftest`（24 个用例，不需要集群）还没进 CI：quick 清单由 platform 的 `api/cmd/infracheck` 生成，加进去要改 platform，见 TD-585。

**没有「要他回电脑」清单里可以因此减掉的条目**：这类事本来就不在那张清单里，新增的是一个能力，不是消去一个缺口。

## 重签发布策略：一张执行卡（2026-11-15 起）

Owner 2026-11-15（LAW-6）：重签不该非回到放钥匙的电脑不可。输码批准的卡已经证明他同意的是那一份精确内容。

平台认两把钥匙签的发布策略：他 Mac 上原来那把，和集群里 Secret `bifrost-owner-exec/release-policy-signer` 那把
（`bifrost-platform` `api/internal/releasepolicy/anchor.go` 的 `ClusterSignerFingerprint`；卡 #572 生成，#573 编进生产）。
集群里那把只有他输码批准的执行卡摸得到；Agent 和平台自己的身份都读不到那个命名空间的 Secret。

改了 `agent-config/release-policy/` 的两份源文件并进了 main 之后：

1. 在工作区根跑 `bifrost-trade-infra/scripts/release/release.sh policy stage`（先把那份检出快进到 main）。
   它渲染规则、交给平台存成「待签稿」（不生效，`release.sh policy status` 照旧是原来那版），打印 `sha256`，并把卡的命令写进一个文件。
2. 自己核对：集群里待签稿的 sha256 等于打印的那个；待签稿的内容是你要的那版。
3. 建 `owner_run_command` 的卡，`params.command` 原样用那个文件的内容，不要手改。卡的理由第一段写「规则换成哪一版、相对现行版改了哪几条」，用白话，
   并写上全文的 sha256；照常写「改了什么：」「批了以后谁因此能做什么新事：」两行、怎么撤、没验什么。
4. 他输码之后，执行口核对 sha256（不对就停，什么都不改）、签名、自己验一遍、装上。你用 `release.sh policy status` 确认 `policy` 是新号、`valid True`。

规则全文不写进命令：全文里列着 D10 的文件路径，带着它的命令会被判成禁区（tier X）。不要用编码绕。
改「平台认哪把钥匙」本身（`anchor.go`）是立法：那一版发布的卡要用白话写清多了或少了哪把钥匙、在哪、谁能驱动、怎么撤。
撤掉集群里那把：把 `ClusterSignerFingerprint` 改成空、发一版；它签的规则随即失效，用 Mac 那把重签。

## 重签运行时规则：一张执行卡（2026-11-25 起）

Owner 2026-11-25：「任何需要重签的话，可以通过我这个就是 Ops 里面的验证码的那种 ticket 的形式来去签，不要我非要回到电脑上才能签。这种回到电脑上的签的这种东西，都是属于这个系统的 failure。」

运行时规则（`agent-config/agentrt-rules/README.md`，例如 `plan-standing`）和发布策略认同样两把钥匙（`bifrost-platform` `api/internal/releasepolicy/anchor.go` 的 `RuleAnchors`）。在这之前运行时规则只认 Mac 那把，重签要回电脑；这一处缺口没登记在上面的清单里。

1. 从线上取正文（README §1），存成文件，改好、版本号加 1；`bash bifrost-trade-infra/scripts/agentrt/rule.sh check <文件> --env prod` 看平台读成什么、是不是放宽。
2. `python3 bifrost-trade-infra/scripts/owner-exec/rule_sign_card.py --text <文件> > card-command.txt`：打印卡的命令，stderr 给出全文的 sha256。正文原样写进卡（here-document），他在卡上看到的就是要签的字节；正文要以换行结尾。
3. 建 `owner_run_command` 的卡，`params.command` 原样用 `card-command.txt` 的内容，不要手改。理由第一段用白话写「规则换成哪一版、相对现行版多给了或收回了什么」，写上 sha256；照常写「改了什么：」「批了以后谁因此能做什么新事：」两行、怎么撤、没验什么。
4. 他输码之后，执行口核对 sha256、用集群那把钥匙签名、验一遍，把签名打印在卡的输出里；它不装任何东西。
5. 把正文和卡输出里的签名交给 `POST /api/v1/agentrt/rules/<rule_id>/sign`（平台认的是签名，不是谁交的）；`rule.sh show <rule_id> --env prod` 确认是新版。

