# 你要做的：TD-432 平台和 CI 的 Gitea 凭证（切法 `CUT-td432-gitea-credentials-2026-10-24.md`）

一共 6 次，约 75 分钟（理想操作时间，不含排障）；第 1 次最长（约 35 分钟），第 2 节可以紧接着做（约 8 分钟）。每一节做完回线程说一声，我核对后再请你做下一节。令牌只在你自己的终端里出现：脚本用隐藏输入读，不上屏、不进 shell 历史、不进对话。

**什么时候开始**：我在线程里说「TD-432 第 1 节可以做了」时，脚本已经在 infra main 上、你的 infra 目录已更新。先确认它在：

```bash
ls -l ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/put-reader-token.sh
```

做完会看到一行 `-rwxr-xr-x … put-reader-token.sh`。看到 `No such file` 就先别做，回线程说一声。

---

## 1　建三个只读账号，把令牌放进集群（S1，约 35 分钟，一次做完）

三个账号：`bifrost-platform-reader-stg`（STG 平台）、`bifrost-platform-reader-prod`（PROD 平台）、`bifrost-ci-reader`（CI 克隆和同步任务，S7 才用，这次一起建省一趟）。都不是管理员，只能读 `bifrost` 组织的代码。页面名称按 Gitea 1.21 英文界面写，可能稍有出入。

### 1.1　建团队 `platform-readers`（约 3 分钟）

1. 浏览器打开 `http://192.168.10.73:30300`，用管理员账号 `weitingzhao` 登录。
2. 组织 `bifrost` → Teams → New Team：
   - Team Name：`platform-readers`；Description：`TD-432 read-only accounts`
   - Repository access：**All repositories**
   - **不勾** Create repositories
   - Permission 选 General Access（不是 Administrator Access）；单元表里 **Code 选 Read**，其余全部 **No Access**
   - Create Team
3. 做完会看到团队页：`platform-readers`，成员 0，仓库栏写 All repositories。

### 1.2　每个账号做同样五步（每个约 10 分钟）

先做 `bifrost-platform-reader-stg`，最后一步的命令末尾写 `stg`；再做 `bifrost-platform-reader-prod`（`prod`）；最后 `bifrost-ci-reader`（`ci`）。下面写的是第一个；另外两个只换账号名和命令末尾那个词，三条命令都在第 5 步写全了。

1. **生成一个密码放进剪贴板**（终端标签页；这个密码之后用不到，只用一次登录；忘了也没关系，管理员能重设）：

```bash
openssl rand -base64 24 | tr -d '\n' | pbcopy
```

   做完什么都不显示，剪贴板里是密码。
2. **建账号**（管理员窗口）：右上角头像 → Site Administration → User Accounts → Create User Account：
   - Authentication Source：Local
   - Username：`bifrost-platform-reader-stg`
   - Email：`bifrost-platform-reader-stg@bifrost.invalid`
   - Password：粘贴（⌘V）
   - **不勾** Require user to change password
   - Create User Account
   做完会看到账号列表多一行 `bifrost-platform-reader-stg`，Admin 一栏没有勾。
3. **加进团队**：组织 `bifrost` → Teams → `platform-readers` → Add Team Member → 输入 `bifrost-platform-reader-stg` → Add。做完会看到成员数加 1。
4. **生成令牌**（无痕窗口，⇧⌘N）：打开 `http://192.168.10.73:30300/user/login`，用 `bifrost-platform-reader-stg` 和剪贴板里的密码登录 → 右上角头像 → Settings → Applications → Generate New Token：
   - Token Name：`td432-reader-2026-10-24`
   - Select permissions：**repository 选 Read，organization 选 Read，user 选 Read**，其余 No access
   - Generate Token → 页面顶部出现令牌（40 位十六进制，只显示这一次）→ 点旁边的复制按钮
5. **放进集群**：在**终端标签页**里跑（不要用线程里的 `!`：脚本要终端才能读隐藏输入）。出现 `Gitea token of … (input hidden):` 后 ⌘V、回车，屏幕上不显示。三个账号依次是这三条：

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/put-reader-token.sh stg
```

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/put-reader-token.sh prod
```

```bash
bash ~/Desktop/stocks/bifrost-trade-infra/scripts/gitea/put-reader-token.sh ci
```

   写之前它先用令牌问 Gitea：令牌是不是这个账号的、账号不是管理员、能列组织的仓库、11 个主仓库都只能读（拉取握手 200、推送握手被拒）、搜得到的仓库没有一个能写。都对才建 Secret，建完读回键名。`stg` 做完会看到：

```
ok    token of bifrost-platform-reader-stg, not an administrator
ok    it can list the repositories of bifrost
ok    11 primaries: read only (fetch 200, push refused)
ok    it sees 11 repositories and can write none
==> Secret bifrost-platform-stg/bifrost-gitea-reader created (keys password username, type kubernetes.io/basic-auth; account bifrost-platform-reader-stg).
```

   （第四行的数字是它看得到的仓库数，比 11 大也对。）`prod` 的最后一行是 `Secret bifrost-platform-prod/bifrost-gitea-reader created`，`ci` 的是 `Secret cicd/gitea-ci-reader created`。

   中途出现 `ERROR: …` 和 `Nothing was written.` 就是什么都没写：照提示改（最常见的是令牌少勾了 organization 或 user 的 Read：回 Applications 删掉这个令牌，按第 4 步重建一个），再跑同一条命令。
6. **收尾**：关掉无痕窗口；清空剪贴板：

```bash
pbcopy < /dev/null
```

三个都做完，回线程说「TD-432 第 1 节做完了」，接着就可以做第 2 节，不用等我。我同时把 STG 平台的挂载和新代码发到 STG（S2、S3，不用你动手），核对完再请你做第 3 节。

**要重来某一个**（比如令牌建错了账号）：**只在这一节、还没有任何 Pod 读它时**这样做——脚本只建不改，先删掉那个 Secret 再跑。平台用上它之后（我说 STG 发好之后）不要删：换令牌用同一条命令末尾加 `replace`（例如 `… put-reader-token.sh stg replace`），它先验新令牌，验过才原地替换，删了再建会让平台中间缺凭证。三条删除命令分别是：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-stg delete secret bifrost-gitea-reader
```

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-prod delete secret bifrost-gitea-reader
```

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd delete secret gitea-ci-reader
```

做完会看到 `secret "…" deleted`。

---

## 2　三条准入策略和两处入口（S3b、S3c、S3d、TD-435、复核 545 F1；约 8 分钟；第 1 节做完就可以做）

第一条：三条准入策略。它们管住平台在 `cicd` 里能写哪些 ConfigMap、能怎么改 Deployment、起流水线时能用哪个身份和什么参数（TD-434、TD-436、TD-435）。我在线程里说「准入策略已在 main」之后再做。先让集群只检查、不生效：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git pull --ff-only && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/platform-rbac --dry-run=server
```

做完会看到每个对象一行，结尾是 `(server dry run)`，没有 `error`。有 `error` 就停下，把那几行贴给我。没有错再真正应用：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/platform-rbac
```

做完会看到 `bifrost-cicd-configmap-writers` 和 `bifrost-platform-deployment-restart-scale` 两条策略及其绑定 `created`，`bifrost-platform-pipelinerun` 和 `bifrost-platform-taskrun` 为 `configured`，其余 `unchanged`。然后跑核对（要扮演平台身份，所以用同一份 kubeconfig）：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && KUBECONFIG=~/.bifrost-owner/kube/admin.yaml python3 scripts/check_admission_guards.py --live > /tmp/td432-admission.txt 2>&1; echo "exit=$?"; tail -n 5 /tmp/td432-admission.txt
```

做完会看到 `exit=0`，最后一行是 `ok: admission files match the actuation policy`。看到 `exit=1` 或 `FAIL` 开头的行，**这一节先停在这里，不做下面两条**，回线程说一声；我读 `/tmp/td432-admission.txt` 决定是改规则还是删掉刚加的策略（回退命令在本节末尾）。

**第二条：CI 的 webhook 入口（TD-435，约 1 分钟）**。它不核对是谁发来的，所以过滤条件改成只收 40 位十六进制的提交号和普通字符的分支名。同样先检查再应用：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/trigger-trade-ci.yaml --dry-run=server
```

做完会看到几行 `… (server dry run)`，没有 `error`。再应用：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/trigger-trade-ci.yaml
```

做完会看到 `eventlistener.triggers.tekton.dev/bifrost-ci configured`，其余 `unchanged`。之后我推一次分支，看 CI 照常起；不起就是过滤写错了，回退是在上一个提交上重新 apply 这个文件。

**第三条：清单应用流水线（复核 545 F1，约 1 分钟）**。C、D 级的改动（例如 `cicd` 里的 Task、Pipeline）只能从 main 应用，调用方不能用 `requireOnMain=false` 绕过。平台自己的代码对 C、D 级一直传 `true`，所以正常的单不受影响：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/cicd/tekton/apply-manifest --dry-run=server
```

做完会看到三行 `… (server dry run)`，没有 `error`。再应用：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/cicd/tekton/apply-manifest
```

做完会看到 `pipeline.tekton.dev/bifrost-apply-manifest configured`，两个 ConfigMap `unchanged`。

做完这三条，回线程说「TD-432 第 2 节做完了」。我读这几条策略的类型检查结果（只读身份就能读），再用 Console 发一次 STG 重启核对平台照常。

**回退**（只在平台的正常操作因此被拒时）：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml delete validatingadmissionpolicybinding,validatingadmissionpolicy bifrost-cicd-configmap-writers bifrost-platform-deployment-restart-scale
```

做完会看到四行 `… deleted`（两条策略和它们的绑定）。

`40-admission.yaml`、webhook 过滤和应用流水线的回退：我在线程里给你上一个提交号，你在那个提交上重新跑对应的 `apply`。

---

## 3　撤掉 STG 平台读管理员令牌的权限（S4，约 3 分钟；第 2 节做完、我说 STG 核对过了再做）

这时 STG 平台已经用自己的只读账号跑过一轮，不再读 `gitea-bootstrap`。仓库里的清单已经去掉了这条绑定，但 `kubectl apply -k` 不会删已有的对象，所以要你删一次：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd delete rolebinding bifrost-platform-gitea-creds-stg
```

做完会看到 `rolebinding.rbac.authorization.k8s.io "bifrost-platform-gitea-creds-stg" deleted`。再问一次集群：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secret/gitea-bootstrap -n cicd --as=system:serviceaccount:bifrost-platform-stg:bifrost-platform
```

做完会看到 `no`。回线程说「STG 绑定删了」，我跑 `check_platform_rbac.py` 核对全部 148 项。

**回退**（只在 STG 的 Gitea 页因此坏掉、并且 STG 跑的还是旧镜像时；新代码不用这条权限，加回来也修不好新代码的问题——新代码坏了多半是挂载或令牌，回线程说，我查挂载、用 `replace` 换令牌）：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd create rolebinding bifrost-platform-gitea-creds-stg --clusterrole=bifrost-platform-gitea-creds --serviceaccount=bifrost-platform-stg:bifrost-platform
```

做完会看到 `rolebinding.rbac.authorization.k8s.io/bifrost-platform-gitea-creds-stg created`。

---

## 4　PROD：先挂载、再批发布单（S5，约 3 分钟）

先在线程里回我一句同意推 PROD 的挂载提交（只加 `bifrost-platform-prod/bifrost-gitea-reader` 的只读挂载，推上 main 后 Argo 自动生效；旧代码不读它）。我推完核对 PROD 两个 Pod 里文件都读得到，再建发布单。

然后在 Console 的审批页（For you）会有一张 `start_pipeline_run`、流水线 `bifrost-deliver-platform-prod` 的单。理由第一段写：批了之后 PROD 平台换成自己的只读 Gitea 账号读 Gitea，并挂上 `bifrost-platform-prod/bifrost-gitea-reader`；它跑的是 STG 已核对过的同一个提交。批了就是同意（Owner 10-11），不用再在线程里说。发完我核对 PROD 的分支标签列表、发布策略和血缘，再请你做第 5 节。

---

## 5　撤掉 PROD 平台读管理员令牌的权限和那个角色（S6，约 3 分钟）

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd delete rolebinding bifrost-platform-gitea-creds-prod
```

做完会看到 `rolebinding.rbac.authorization.k8s.io "bifrost-platform-gitea-creds-prod" deleted`。

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml delete clusterrole bifrost-platform-gitea-creds
```

做完会看到 `clusterrole.rbac.authorization.k8s.io "bifrost-platform-gitea-creds" deleted`。

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secret/gitea-bootstrap -n cicd --as=system:serviceaccount:bifrost-platform-prod:bifrost-platform
```

做完会看到 `no`。回线程说「PROD 绑定删了」。

**回退**（同第 3 节：只在 PROD 跑的还是旧镜像时有用，正常不需要）：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml create clusterrole bifrost-platform-gitea-creds --verb=get --resource=secrets --resource-name=gitea-bootstrap
```

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd create rolebinding bifrost-platform-gitea-creds-prod --clusterrole=bifrost-platform-gitea-creds --serviceaccount=bifrost-platform-prod:bifrost-platform
```

---

## 6　之后两次（S7、S8，到时单独发你）

- **S7**：CI 克隆、镜像同步、GitHub 同步改用 `gitea-ci-reader`，凭证不再写进 `.git/config`。Tekton 任务不归 Argo，我用 `plan_manifest` / `apply_manifest` 建单，你在 Console 上批（约 5 分钟）。
- **S8**：克隆凭证 `gitea-git-credentials` 退役、`gitea-bootstrap` 搬出 `cicd`，最后换一次管理员令牌（STG 平台此前一直读得到它；用 `rotate-admin-token.sh`，S7 里会先改掉它往克隆凭证写管理员令牌的那一步），并在 Gitea 后台吊销切换前的旧令牌（旧管理员令牌、旧克隆凭证的令牌），再用每个旧令牌各试一次、都要被拒。约 15 分钟。
