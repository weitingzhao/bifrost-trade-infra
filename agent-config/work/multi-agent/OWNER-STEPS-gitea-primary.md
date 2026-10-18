# 你要做的：Gitea 做主（切法 `CUT-gitea-primary-2026-10-17.md`）

每一节做完就停，回线程里说一声，我核对后再给下一节。命令都是原样可跑的，令牌一律 `read -rs` 读入、不上屏、不进对话。

---

## 0　换 Gitea 管理员令牌（TD-365，约 10 分钟；脚本已复核；在第 1 节之后做：它要用第 1 节第 4 条建的探针仓库试写权限）

旧令牌从 2026-06-17 起就在公开的 infra 仓库历史里（`d30ef90`），至今还在用。它在集群里放了**两处**：`gitea-bootstrap`（平台和镜像同步用）和 `gitea-git-credentials` 的密码（Tekton 每次克隆代码用）。原来这一节只换第一处，照做后再删旧令牌，CI、deliver、apply-manifest 的克隆会一起断（10-17 18:3x 发现，已改）。脚本 `scripts/gitea/rotate-admin-token.sh` 两处一起换，不显示任何令牌。

1. 先只核对（不改东西）：

```bash
~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/rotate-admin-token.sh check
```

   应看到两行都是 `admin weitingzhao`，第三行是 `THE SAME token`。
2. 浏览器打开 Gitea（`http://192.168.10.73:30300`），用管理员账号 `weitingzhao` 登录 → 右上角头像 → Settings → Applications → Generate New Token：名字 `bifrost-bootstrap-2026-10-17`；权限选 repository、organization、user 三项的 Read and Write，其余 No access；生成后先复制，**旧的先别删**。
3. 换（提示出现后粘贴新令牌、回车；屏幕上不显示）：

```bash
~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/rotate-admin-token.sh rotate
```

   写之前它先用新令牌试一遍它要干的事（登录成管理员 `weitingzhao`、读仓库、对探针仓库试一次写权限，镜像一个都不碰），过了才写；写完还用克隆凭证按 Tekton 的方式读一次仓库。最后一行是 `==> rotated.` 就换好了；中途它若说「nothing changed」，就是新令牌没通过检查，什么都没改，照它说的补权限再建一个；若说「run rotate again」，就再跑一次同一条命令，用同一个或再建一个新令牌都行。
4. 回线程说「Gitea 令牌换好了」。我核对镜像同步和一次 CI 克隆都用新令牌跑通，再请你删旧令牌。
5. 我说可以了：回 Gitea 的 Applications 页**删掉旧令牌**（今天之前建的那个），然后跑：

```bash
~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/rotate-admin-token.sh revoked
```

   最后一行是 `==> the leaked tokens are refused; both Secrets log in.` 就收尾了。`rotate` 若提示本机那份被忽略的 `k8s/cicd/gitea/secret.yaml` 还是旧值，就把它删掉（集群里的 Secret 才是正本）：

```bash
rm ~/Desktop/stocks/bifrost-trade-infra/k8s/cicd/gitea/secret.yaml
```

---

## 1　第 1 步：账号、团队、探针仓库、模板、GitHub 令牌（约 30 分钟，一次做完）

页面名称按 Gitea 1.21 的英文界面写，可能稍有出入。

1. **推送账号** `bifrost-mbp`（不是管理员）：Site Administration → User Accounts → Create User Account。
   在无痕窗口用它登录 → Settings → Applications → Generate New Token，名字 `mbp-sessions`，权限只给 repository 的 Read and Write。令牌先存好，第 A 批用。
2. **团队 `maintainers`**：组织 `bifrost` → Teams → New Team。Repository access 选 All repositories；Code 单元 Write，其它 Read 或 No Access；不给 Administrator。成员：你的账号、`bifrost-mbp`。
3. **团队 `agentd-write`**：同上，Code 单元 Write，其它 No Access。成员：`agentd-agent-06`、`agentd-agent-06-stg`。
4. **探针仓库** `bifrost/primary-probe`：New Repository，私有，勾「Initialize」生成 main。Settings → Branches → Add New Rule：
   - 规则 `main`：Push 选 Enable Whitelist-restricted Push，团队 `maintainers`，用户：你；**再勾 Enable Merge Whitelist，同样只放 `maintainers` 和你**。保存。
   - 规则 `agent/**`：白名单推送，团队 `agentd-write`，用户：你；合并白名单只放 `maintainers` 和你。保存。
   - Settings → Tags → 新规则：Tag name `*`，Allowed：团队 `maintainers`、你。
5. **模板仓库** `bifrost/repo-template`：同第 4 条建好、设好同样的两条分支规则；Settings → Webhooks 加一个 Gitea 钩子，地址 `http://el-bifrost-ci.cicd.svc.cluster.local:8080`、JSON、只要 Push；Settings 里勾「Template Repository」。
6. **GitHub 同步令牌**（9.12 选了 B）：github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token：
   名字 `bifrost-github-sync`，过期一年，Resource owner `weitingzhao`，Repository access 选 **All repositories**（选了它下面才有仓库权限）；Permissions → **+ Add permissions** → Repositories → 勾 Contents，右边改成 **Read and write**（Metadata 自动只读）。生成后马上做第 7 条。
7. **放进集群**：线程里的 `!` 或终端标签页都行（10-17 21:1x 原来那行命令失败，是因为你的 shell 是 zsh，zsh 的 `read -p` 意思是读协进程；脚本是 bash 写的）。出现提示后粘贴令牌回车，屏幕上不显示。写入前先问 GitHub：令牌是 `weitingzhao` 的、11 个仓库都能推（只做推送握手，不推东西），有一条不对就什么都不写；已有 `github-sync` 也不写。最后一行应为 `==> Secret cicd/github-sync created (key: token)`：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/put-github-sync-token.sh
```

8. **核对探针仓库的保护**（你的终端，用你的节点钥匙登 06；以 `agentd-agent-06-stg` 的身份逐条试：推 main、建标签、经合并请求合进 main、强推和删除它自己的 `agent/` 分支都要被拒，建 `agent/_probe/<时间>/a1` 要成功；每条只认 Gitea 那条规则的原话，认不出就算没过）：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh probe-protection
```

   最后一行是 `all as expected` 就过了；它会留下那条 `agent/_probe/…` 分支和一个已关闭的合并请求，你在页面上删不删都行。有 `FAIL` 行就把输出贴回线程（日志也在 `~/agent-work/agent-06-logs/`，我会去读）。以 `bifrost-mbp` 推 main 能成功，在第 A 批第 6 步存好它的令牌之后再试。

做完回「第 1 步做完了」。

---

## 2　装上第 0 步的集群部分（0a、0e；复核已过，10-17 16:1x 起可以做，约 5 分钟）

0a 改的是镜像同步任务，0e 是新的 GitHub 同步（任务、触发器、每 15 分钟的对账、两条告警、维护者清单）。今天每个仓库都还是镜像，装上之后什么都不变；对账每次空跑成功。10-17 15:0x 我用只读身份核过：集群和仓库的差别正好就是这几样（多一个 `github-sync` 触发器、镜像同步任务换版、两条告警、维护者清单多一条），其余对象一字不差；触发器的服务账号本来就能建 TaskRun，不用改权限。

脚本 `scripts/gitea/apply-step0.sh` 先确认这几份清单就是复核过的版本（`1de78f6`），不是就停；全部在服务器上 dry-run 过了才真 apply，出错即停。它自己用你的管理员 kubeconfig，不读也不打印任何 Secret。

1. 先只核对（不改任何东西）：

```bash
~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/apply-step0.sh check
```

2. 最后一行是 `check passed` 就装：

```bash
~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/apply-step0.sh apply
```

3. 回线程说「第 0 步装好了」。我用只读身份核对：触发器有 6 个、镜像同步任务是新版、CronJob 在、两条告警在，并等第一次对账空跑成功。

---

## 3　第 A 批：`bifrost-platform`、`bifrost-ui` 改由 Gitea 做主，加 agentd 切换（你约 25 分钟，一次做完）

先备好：第 1 节第 1 条存下的 `bifrost-mbp` 令牌（`mbp-sessions`，40 位十六进制）。丢了就用无痕窗口登 `bifrost-mbp` 重建一个（Settings → Applications，repository 读写），旧的删掉。

和切法 §4 的两处不同（10-17 22:0x）：① `push-main.sh` 只要窗口开着就拒推，持窗口的人也一样，所以窗口只罩住第 1–7 条，我推 infra 和平台都在放窗口之后；放窗口之前我先把本机检出换到 Gitea（第 8 条），空档里谁推 platform、ui 都推到 Gitea，不会推到 GitHub。② W-68 B1 第 5 步（服务文件里的 `.73` 改 VIP）不合进来：06 的出站防火墙只放行 `.73`，那一步跟 B1 一起做。

每条命令都在线程里用 `!` 跑或在终端里跑都行；出 `ERROR`、`FAIL`、`DIFFERENT`、`STOPPED` 就停下，把输出贴回线程。

**0（我）** 持窗口 `release.sh hold --what bifrost-platform,bifrost-ui`，确认没有在跑的 deliver / CI、平台上没有进行中的尝试；在线程里说「窗口拿到了」你再开始。

**1（你）停 06 上两个 agentd**，最后一行 `stopped: bifrost-agentd.service bifrost-agentd-stg.service`：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh stop
```

**2（你）比对**：两个仓库先同步一次镜像，再逐条比 GitHub 和 Gitea 的分支与标签；两行都是 `…: same (…)` 才往下：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/compare-refs.sh bifrost-platform bifrost-ui
```

**3（你）页面上转成普通仓库**，两个仓库各做一次：Gitea → `bifrost/bifrost-platform` → Settings → 页面最下面 Danger Zone → **Convert to Regular Repository** → 输入仓库名 → 确认。`bifrost/bifrost-ui` 同样。

**4（你）搬 Agent 分支**（只复制 `bifrost-agents/bifrost-platform` 的 `agent/*` 到 `bifrost/bifrost-platform`，不删原处；必须在第 5 条之前），最后一行 `bifrost-platform: N copied, 0 already there, 0 not copied`：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/copy-agent-branches.sh bifrost-platform
```

**5（你）设保护**：两条分支规则经 API 设好再读回，每条一行 `… set and read back`：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/protect-repo.sh --owner weitingzhao bifrost-platform bifrost-ui
```

然后两个仓库各在页面上加标签规则（和第 1 节第 4 条一样）：Settings → Tags → Tag name `*`，Allowed users `weitingzhao`，Allowed teams `maintainers` → Add Rule。

**6（你）把 `bifrost-mbp` 的令牌存进钥匙串**：出现 `Gitea token of bifrost-mbp (input hidden):` 后粘贴令牌回车（屏幕上不显示）。它先问 Gitea（是 `bifrost-mbp` 的、能在 `primary-probe` 上推送握手），存完再读回 git 会用的那条；最后一行 `==> git now pushes to http://192.168.10.73:30300 as bifrost-mbp.`。若说钥匙串里另有一条先答了（10-17 第 A 批就是：一条 `weitingzhao` 先答），不用删它，先跑 `git config --global credential.http://192.168.10.73:30300.username bifrost-mbp` 再跑一次（第 B 批起这条已经在你的全局配置里）：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/store-mbp-token.sh
```

**7（你）全局 `insteadOf`**：`~/agent-work` 下那些从 GitHub 地址克隆的独立检出改走 Gitea（每个仓库 SSH、HTTPS 两条；先在 `~/.gitconfig` 旁边留一份 `.before-gitea-primary`），四行 `ok    … → http://192.168.10.73:30300/bifrost/….git`：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/global-insteadof.sh add bifrost-platform bifrost-ui
```

做完回「第 A 批 1–7 做完了」。

**8（我）** 本机两个检出换远端（`switch-local-remotes.sh bifrost-platform bifrost-ui`：`origin` → Gitea，GitHub 留作推不出去的 `github`）→ 名单 `agent-config/gitea-primary.txt` 加这两个、STG overlay `AGENTRT_GIT_ORG=bifrost`、两个服务文件去掉 `AGENTD_GIT_PUSH_BASE`，提交 → 放窗口 → `push-main.sh` 推 infra → `gitops_sync_app` STG 平台，核对 Pod 上的值。PROD overlay 同样改好、单独一个提交，**等你回「推 PROD 接线」**。

**9（你）装新服务文件、只开 STG 的 agentd**（`copy` 把 `scripts/agent-host` 和 agentd 拷到 06，`prepare` 装服务文件，`start stg` 只开 STG；最后一行 `running: bifrost-agentd-stg.service`）：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh copy && bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh prepare && bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start stg
```

**10（我）核对**：STG 派一件确定性的小任务，分支落在 `bifrost/bifrost-platform` 的 `agent/<任务>/a1`、平台记 persisted、血缘归到任务；经 `push-main.sh` 推一个平台提交，CI 由钩子起、`bifrost-github-sync` 把它推到 GitHub（GitHub main 等于这个提交）；起一次 `bifrost-deliver-platform`（STG），克隆到的是刚推的提交。

**11（你）回「推 PROD 接线」**之后：我推 PROD overlay、同步 PROD 平台、核对；然后你开 PROD 的 agentd（最后一行 `running: bifrost-agentd.service`）：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start prod
```

在那之前 PROD 的 agentd 停着：PROD 平台还读 `bifrost-agents`，这时开它，交来的结果会被 409 永久拒收。

**回退**（按做到哪）：见切法 §4「第 A 批」末尾。另加：第 6 条在「钥匙串访问」里删 `192.168.10.73` 那条；第 7 条 `bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/global-insteadof.sh remove bifrost-platform bifrost-ui`。
