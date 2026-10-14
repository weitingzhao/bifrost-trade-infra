# 护栏 ④：把 Gitea 备份应用到集群（要你动手的四步）

写给 Owner。前三步在你的终端里各一条命令，第四步是第一份备份出来之后的一次解密验收。每一步做完不用回话，统筹方用只读身份自己看结果，再告诉你下一步可不可以做。

2026-10-12 晚写成。命令由统筹方逐条核对，并交 Codex 只读核对（结论见文末）。完整的背景和恢复步骤在 `docs/runbooks/gitea-restore.md`。

**身份**：每条命令都在一个括号里临时用你的管理员身份（`AGENT_FACTS.md` 第 8c 节；你终端默认连的是本机 Docker Desktop，不是集群）。括号结束后你的终端不受影响。
**文件**：第 1、3 步的命令开头有一道守卫——工作目录里要应用的那几个已跟踪文件必须和主线提交 `1c68720` 里的一样，不一样就不执行。（它不查新增的未跟踪文件，也管不了检查之后文件再被改；所以做之前别让别的会话动这几个目录。）

## 第 1 步 · 应用备份任务、告警规则、维护者清单

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && git diff --quiet 1c68720 -- k8s/cicd/gitea-backup k8s/monitoring/bifrost-alerting-rules.yaml k8s/monitoring/maintainer-reconcile && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl apply --dry-run=server -f k8s/monitoring/bifrost-alerting-rules.yaml && kubectl apply --dry-run=server -k k8s/monitoring/maintainer-reconcile && kubectl apply --dry-run=server -k k8s/cicd/gitea-backup && kubectl apply -f k8s/monitoring/bifrost-alerting-rules.yaml && kubectl apply -k k8s/monitoring/maintainer-reconcile && kubectl apply -k k8s/cicd/gitea-backup )
```

先对三样各做一次服务端试算，三次都过了才真正应用。它会改的东西（统筹方 2026-10-12 21:55 只读比对过集群现状）：

| 对象 | 变化 |
|---|---|
| `cicd` 里新建 5 个对象 | 备份的定时任务 `gitea-backup`（每天 03:10 UTC）、放备份的卷 `gitea-backup`（在 NAS 的 `nfs-cold` 上；建它会让集群在 NAS 上自动建一个目录）、脚本、你的公钥（和集群状态备份用的是同一把）、一条网络策略 |
| 告警规则（整份应用） | 新增一条「Gitea 备份 26 小时没有成功，并持续 30 分钟」；另外会带上一处早先合进主线但没应用的改动：一条告警的说明文字（10-07） |
| 维护者清单（整份应用） | 清单里多三项：这次的备份，加上 10-10 合进主线但没应用的两项；一处说明文字。它的账号、权限、定时任务和集群里现在的完全一样，不会变 |

不会动 Gitea 本身，不会重启 Gitea 或现有的维护任务。三样里前一样成功、后一样失败的话，前面的不会自动撤回，统筹方看输出再说。备份任务要到下一次 03:10 UTC 才第一次自己跑。进第 2 步之前，统筹方先只读确认那个卷已经绑定好。

## 第 2 步 · 手工起第一次备份（统筹方说「可以做第 2 步」之后）

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; backup_job="gitea-backup-manual-$(date +%s)"; kubectl -n cicd create job --from=cronjob/gitea-backup "$backup_job" )
```

它起一个一次性的任务（名字带时间，重复执行会再起一个新的，不会报重名），做的事和每晚的一样：

1. 只读挂载 Gitea 的数据，在任务自己的临时空间里取一份一致的副本。
2. 用这份副本起一个只在任务内部可见的临时 Gitea，把每个仓库 clone 一遍，逐个比对。
3. 全部对上之后，用你的公钥加密，写到 NAS。任何一步不对就不写，下次再来。

它的临时空间在控制面节点上，上限 60GiB（节点空闲 432 GB）。它需要从 GitHub 下载加密工具（钉死版本和校验和，和集群状态备份每晚下的是同一个），所以它的网络策略对这个任务的整个运行期间放行了公网 443 和 DNS，别的都不通。统筹方盯着它跑完，读日志，告诉你：成功与否、Gitea 数据的真实大小、用了多久。手工起的这一次不会更新「上次定时成功」的指标，告警只认定时那一次。

**这一步第一次碰到真实数据，有几样只有它能证明**：同一节点上只读挂载正在使用的卷、对运行中的数据库做在线备份、线上那些镜像仓库的校验、网络策略是否生效、NAS 上的权限。失败的话不会被当成一份成功的备份发布出来，但可能在 NAS 上留下一个没完成的目录或一把锁；统筹方读了日志再说怎么办。

## 第 3 步 · 关掉 Gitea 的自助注册（会让 Gitea 重建一次，期间不可用；统筹方确认没有 CI 和发布在跑之后）

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git diff --quiet 1c68720 -- k8s/cicd/gitea/deployment.yaml && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl apply --dry-run=server -f k8s/cicd/gitea/deployment.yaml && kubectl apply -f k8s/cicd/gitea/deployment.yaml )
```

文件里有两个对象：Gitea 的服务（和集群里现在的一样，不会变）和 Gitea 的部署（只多一个环境变量，关掉任何人都能自己注册账号）。部署一变，Gitea 会先停掉旧的再起新的，期间代码镜像不可用；多久没有量过（就绪检查至少要等 15 秒）。这段时间里要访问代码镜像的 CI 和发布可能失败，所以要挑没有东西在跑的时候。统筹方做这一步的时候会占住发布窗口，等新的 Gitea 就绪、能正常读到仓库之后才放开。

这一步和备份无关，可以改天做。

## 第 4 步 · 解密验收（一次）

2026-10-13 晚写成。目的：证明用你的私钥确实能把备份解出来。集群里没有私钥，所以只有你能做。统筹方不碰你的私钥文件，也不在这台电脑上读 NAS 的挂载。

做法：直接用仓库里的恢复脚本 `k8s/cicd/gitea-backup/restore.sh`，照 `docs/runbooks/gitea-restore.md` 第 5 条，填了三个值：NAS 上要解的那一份备份的目录、私钥的位置、解到哪里。统筹方 10-13 晚自己写的两版新命令没过独立核对，已经停掉，这里不用。核对这一版时查出恢复脚本自己的漏洞（TD-339），修了五处，独立复核判这些改动正确，但两轮都没有放行，因为还剩一处没修：校验和清单里某一行的格式如果坏了，校验工具会跳过那一行。Owner 10-13 定「④ 照这版做」。这一处不会让「解不开」显示成「解开了」——解密本身带认证，解出来的归档还会再对一次校验和；它漏掉的是清单密文那一行的校验。下面第一条命令会先确认你跑的就是合进主线的那一版（`bbd5685`）。

前提（这台电脑上 10-13 量过都有）：`age`、`sha256sum`、`tar` 在 `PATH` 上。耗时没量过；集群里备份任务自己跑一次是 48 秒。

**先做一件事**：在 Finder 里把 NAS 的共享 `k3s-cold` 挂上（⌘K 连接服务器，选 `k3s-cold`）。挂好之后它在 `/Volumes/k3s-cold`。

**第一条：解开**（原样可以运行）

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && { git diff --quiet bbd56853d180c0d00bd75d044c564a899d90d291 -- k8s/cicd/gitea-backup/restore.sh || { echo "STOP: restore.sh is not the reviewed version, or that commit is not in this checkout"; false; }; } && bash k8s/cicd/gitea-backup/restore.sh "/Volumes/k3s-cold/cicd-gitea-backup-pvc-d0054547-c504-4403-bc30-32b707ad6371/2026-10-13T031001Z" ~/bifrost-cluster-state.agekey /tmp/gitea-decrypt-check; echo "exit=$?"
```

它做的事：先确认恢复脚本和合进主线的那一版一样；然后脚本核对两个密文文件的校验和（剩下没修的那一处就在这里：清单里格式坏掉的一行会被跳过），用 `~/bifrost-cluster-state.agekey`（10-07 生成集群状态备份密钥时的位置）解密，核对解出来的归档的校验和，检查归档里没有越界的路径，把它展开到 `/tmp/gitea-decrypt-check`，清单放在旁边的 `/tmp/gitea-decrypt-check.MANIFEST.tsv`。这两个位置必须原先不存在（存在就拒绝）；新建出来的目录和文件别的普通账号读不了。它只读 NAS，不连集群，不上公网。验收的是 `2026-10-13T031001Z` 这一份：10-12 22:10（美中时间）第一次定时备份，名字取自集群里那次备份任务的日志；命令里写死了它，不读 `LATEST`。如果私钥文件带口令，`age` 会问你。

**只看打印出来的 `exit=` 那一行**（它是恢复脚本的结果；整条命令自己的退出码不算数）。通过的样子，最后三行是：

```
MANIFEST.tsv.age: OK
Decrypted, plaintext sha256 checked, extracted to /tmp/gitea-decrypt-check
exit=0
```

不是这样（有 `STOP:` 或 `FATAL:` 开头的一行，或者 `exit=` 不是 0）就是没通过：**验收到此为止，但第二条和第三条照样跑**，然后把第一条的最后几行告诉统筹方；它们只有文件名和原因，没有密钥内容。常见的几种：

| 最后几行里有 | 意思 |
|---|---|
| `STOP: restore.sh is not the reviewed version…` | 脚本被改过，或这份检出里没有那个提交 |
| `FATAL: run directory unavailable` | 共享没挂上，或者那一份备份的目录不在了 |
| `FATAL: run STATUS …` | 那一份备份没有标成成功，或者它的状态文件读不了 |
| `FATAL: identity file not readable` | 私钥不在 `~/bifrost-cluster-state.agekey`，告诉统筹方它在哪 |
| `age: error: no identity matched any of the recipients` | 这把私钥解不开这份备份 |
| `FATAL: … checksum …` / `sha256 mismatch` | 密文或解出来的内容和记录对不上 |
| `FATAL: target must not exist` / `manifest path next to target must not exist` | 上一次解出来的东西还在：先跑第二条，再重跑第一条 |

**第二条：删掉解出来的那一份**（不管第一条过没过都跑；那是 Gitea 的全部数据，包括账号库，不该留在这台电脑上。在你跑这一条之前，它一直在磁盘上）

```bash
rm -rf /tmp/gitea-decrypt-check /tmp/gitea-decrypt-check.MANIFEST.tsv; if [ -e /tmp/gitea-decrypt-check ] || [ -L /tmp/gitea-decrypt-check ] || [ -e /tmp/gitea-decrypt-check.MANIFEST.tsv ] || [ -L /tmp/gitea-decrypt-check.MANIFEST.tsv ]; then echo "left=1"; else echo "left=0"; fi
```

`left=0` 的意思是这两个路径都不在了。它是普通删除，不是安全擦除。

**第三条：弹出共享**（它自己会说弹没弹出；说卷正忙就关掉正在看这个共享的 Finder 窗口再跑一次）

```bash
diskutil unmount /Volumes/k3s-cold
```

做完在线程里回一句「④ 解了，exit=0，left=0」，或者把第一条的最后几行贴上来。

这一步证明的：你手里的私钥能解开 NAS 上 `2026-10-13T031001Z` 这份备份，解出来的归档和备份任务记下的校验和一致，并且能展开。它没有做的：手册第 5 条里核对仓库个数的那几行；也不证明 Gitea 能完整恢复——那要照手册「Restore onto a new volume」一节做。

统筹方量过的（10-13 22:0x，用命令原文、临时测试密钥和临时测试备份，跑的是主线上这份脚本和真的 `age`）：对的密钥 `exit=0`；另一把密钥、那份备份的目录不在、私钥不在、目标已存在、提交不在检出里，各自是上表里对应的那一行和 `exit=1`；第二条跑完 `left=0`。没有量的：真实的 NAS 和私钥、带口令的私钥、真实归档的大小和耗时。

这之后还有两样由统筹方只读验收，不用你动手：下一次 03:10 UTC 的定时运行成功、指标和告警正常；维护者对账下一次运行认得这个新任务。

## 撤回

先等正在跑的备份任务结束，再删定时任务、网络策略和公钥这三样，不影响 Gitea：

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl -n cicd delete cronjob gitea-backup; kubectl -n cicd delete networkpolicy gitea-backup-deny-all; kubectl -n cicd delete configmap gitea-backup-recipient )
```

手工起的那个任务不会跟着删，统筹方到时给你它的确切名字。放备份的卷、里面已有的备份、脚本留着，都不会自己运行，要删另说。定时任务删掉之后那条告警不会响（它依据的指标没有了）；撤回时告诉统筹方，把告警规则和维护者清单里对应的那一项也一并改回去。

## Codex 的只读核对（复核 140）

第一稿被要求改 12 处，本稿都已改入：守卫只在第 1、3 步、而且查不了未跟踪的新文件；建卷会在 NAS 上自动建目录；告警是「26 小时没有成功并持续 30 分钟」；三样应用中途失败不会自动撤回；手工任务的名字改成带时间的，避免第二次执行报重名；临时空间上限写成 60GiB；失败时可能留下没完成的目录或锁；Gitea 重建的时长没有量过、不写「约 1 分钟」；手工成功不更新定时指标；第 4 步之后还有两样只读验收；撤回命令删不掉手工任务；定时任务删掉之后告警不会响（第一稿写反了）。Codex 确认的：三次服务端试算任一失败都不会执行后面的应用；三样之间没有先后依赖；应用备份目录恰好建 5 个对象，不需要新的密钥；从定时任务起的手工任务带着同样的初始化容器、标签和时限。
