# 你要做的：Gitea 做主（切法 `CUT-gitea-primary-2026-10-17.md`）

每一节做完就停，回线程里说一声，我核对后再给下一节。命令都是原样可跑的，令牌一律 `read -rs` 读入、不上屏、不进对话。

---

## 0　先换 Gitea 管理员令牌（TD-365，约 5 分钟，越早越好）

旧令牌从 2026-06-17 起就在公开的 infra 仓库历史里（`d30ef90`），至今还是在用的那个。

1. 浏览器打开 Gitea（`http://192.168.10.73:30300`），用管理员账号登录 → 右上角头像 → Settings → Applications → Generate New Token：
   名字 `bifrost-bootstrap-2026-10-17`，权限照旧令牌的选（不确定就全选 write），生成后先复制，**旧的先别删**。
2. 你的终端跑这一条（粘贴新令牌后回车；不是 40 位十六进制就什么都不改）：

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; read -rs -p 'New Gitea admin token: ' t; echo; case "$t" in ''|*[!0-9a-f]*) echo "not a Gitea token (hex only); nothing changed"; exit 1;; esac; [ ${#t} -eq 40 ] || { echo "not 40 characters; nothing changed"; exit 1; }; printf '{"stringData":{"gitea_admin_token":"%s"}}' "$t" | kubectl -n cicd patch secret gitea-bootstrap --type merge --patch-file /dev/stdin; unset t )
```

3. 回线程说「Gitea 令牌换好了」。我核对平台的镜像同步、CI 钩子都还能用。
4. 我说可以了，你再回 Gitea 的 Applications 页**删掉旧令牌**。本机那份被忽略的 `bifrost-trade-infra/k8s/cicd/gitea/secret.yaml` 里还是旧值：要么把值改成新的，要么直接删掉这个文件（集群里的 Secret 才是正本，脚本都先读它）。

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

做完回「第 1 步做完了」。我在探针仓库上核对保护（在 06 上以 `agentd-agent-06-stg` 推 main 被拒、经 PR 合进 main 被拒、建标签被拒、建 `agent/_probe/1` 成功、删它和强推它被拒；以 `bifrost-mbp` 推 main 成功），命令到时给你。

---

## 2　装上第 0 步的集群部分（0a、0e；等我说「复核过了」再做，约 5 分钟）

0a 改的是镜像同步任务，0e 是新的 GitHub 同步（任务、触发器、每 15 分钟的对账、两条告警、维护者清单）。今天每个仓库都还是镜像，装上之后什么都不变；对账每次空跑成功。命令到时在这里补上（先 `--dry-run=server` 过了才真 apply）。

---

## 3　第 A 批起（platform、ui，加 agentd 切换）

等 0f 的四个脚本复核过、第 1 步核对完再给。
