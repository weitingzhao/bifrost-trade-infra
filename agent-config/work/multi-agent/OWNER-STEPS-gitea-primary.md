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
   名字 `bifrost-github-sync`，过期一年，Resource owner `weitingzhao`，Repository access 选 **All repositories**，Repository permissions → Contents: Read and write（Metadata 自动只读）。生成后马上做第 7 条。
7. **放进集群**（粘贴 GitHub 令牌后回车；最后一行只打印键名，应为 `['token']`）：

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; read -rs -p 'GitHub sync token: ' t; echo; [ -n "$t" ] || { echo "empty; nothing created"; exit 1; }; printf '%s' "$t" | kubectl -n cicd create secret generic github-sync --from-file=token=/dev/stdin; unset t; kubectl -n cicd get secret github-sync -o json | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)["data"]))' )
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

## 3　第 A 批起（platform、ui，加 agentd 切换）

等 0f 的四个脚本复核过、第 1 步核对完再给。
