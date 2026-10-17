# Owner 操作单：06 出集群，当 Agent 主机

起草 2026-10-17 01:00（统筹线程）。切法和理由：`CUT-agent-host-06-2026-10-17.md`。装到 06 上的文件：`bifrost-trade-infra/scripts/agent-host/`。

**在哪做**：都在你 Mac Pro 自己的 Terminal 里（要用管理员 kubeconfig 和节点密钥，我不能执行）。每条 SSH 会问一次节点密钥的口令。命令可以原样运行，输出都写进 `/tmp` 下的文件，我读完删掉。

**怎么回**：每段末尾写了回什么。只回那句话，不要贴输出。

**两段**：A（出集群）现在就可以做，建议周末做（US 休市），约 40 分钟。B（变成 Agent 主机）等我在线程里说「B 的脚本复核过了」再做。

---

## A　出集群

### A1　确认没有发布、没有在跑的流水线，然后 cordon（1 分钟）

没有发布窗口、也没有在跑的 PipelineRun，才会 cordon；否则打印原因，什么都不改，过一会儿再跑。

```bash
cd /Users/vision-mac-trader/Desktop/stocks && bifrost-trade-infra/scripts/release/release.sh window && ( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; kubectl get pipelineruns -n cicd -o jsonpath='{range .items[?(@.status.conditions[0].reason=="Running")]}{.metadata.name}{"\n"}{end}' | grep . && echo "STOP: a pipeline is running, try again later" || kubectl cordon ubt-k3s-06 )
```

看到 `node/ubt-k3s-06 cordoned` 就接着做 A2。

### A2　备份 event-radar 的卷到 Mac Pro（1–3 分钟）

```bash
mkdir -p ~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6 && ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo tar -C /var/lib/rancher/k3s/storage -czf - pvc-6bf6eca6-5968-4874-ae93-22b8a2a23fab_research_event-radar-input-pvc' > ~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6/event-radar-input-pvc.tar.gz && tar -tzvf ~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6/event-radar-input-pvc.tar.gz > /tmp/node06-backup.txt 2>&1; echo exit=$? >> /tmp/node06-backup.txt
```

### A3　删掉 06 上的 local-path 卷（约 1 分钟，最多等 5 分钟）

列出绑在 06 上的卷对应的 PVC（应该是 event-radar 那 1 个和 cicd 的几个 CI 工作区），逐个删掉，等清理完。只删 PVC，不删 PipelineRun。

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; kubectl get pv -o json | python3 -c '
import json, sys
for pv in json.load(sys.stdin)["items"]:
    terms = ((pv["spec"].get("nodeAffinity") or {}).get("required") or {}).get("nodeSelectorTerms") or []
    nodes = [v for t in terms for e in t.get("matchExpressions") or [] for v in e.get("values") or []]
    c = pv["spec"].get("claimRef") or {}
    if "ubt-k3s-06" in nodes and c.get("name"):
        print(c["namespace"], c["name"])
' > /tmp/node06-pvcs.txt && cat /tmp/node06-pvcs.txt && while read -r ns name; do kubectl -n "$ns" delete pvc "$name" --wait=false; done < /tmp/node06-pvcs.txt; for i in $(seq 1 30); do left=$(kubectl get pv -o jsonpath='{range .items[*]}{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]}{"\n"}{end}' | grep -cx ubt-k3s-06); [ "$left" -eq 0 ] && break; sleep 10; done; echo "PVs left on ubt-k3s-06: $left" ) > /tmp/node06-pvs.txt 2>&1; echo exit=$? >> /tmp/node06-pvs.txt
```

### A4　两个 PDB 不许驱逐的 Deployment 先滚动重启（约 5 分钟）

它们的 PDB 是 `maxUnavailable: 0`，drain 会一直卡住。06 已经 cordon，新 Pod 只会落到别处。

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; kubectl -n plugin-market-data rollout restart deployment/polygon-worker-options deployment/polygon-worker-stocks && kubectl -n plugin-market-data rollout status deployment/polygon-worker-options --timeout=15m && kubectl -n plugin-market-data rollout status deployment/polygon-worker-stocks --timeout=15m ) > /tmp/node06-polygon.txt 2>&1; echo exit=$? >> /tmp/node06-polygon.txt
```

### A5　drain（约 5 分钟）

会发生的事见切法第 3 节的表：coredns 换节点时 DNS 断几秒，redis-live-prod 和 redis-dev 的缓存清空，STG 平台重启一次。

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; kubectl drain ubt-k3s-06 --ignore-daemonsets --delete-emptydir-data --timeout=15m ) > /tmp/node06-drain.txt 2>&1; echo exit=$? >> /tmp/node06-drain.txt
```

做完回：「06 drain 完了」。我读 A2–A5 的四个文件，核对搬走的负载都在别处就绪、06 上只剩 DaemonSet，然后告诉你可以做 A6。

### A6　在 06 上卸 k3s 并重启（约 3 分钟）

最后会因为重启断开连接，`exit=255` 是正常的。

```bash
ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo /usr/local/bin/k3s-agent-uninstall.sh && sudo systemctl reboot' > /tmp/node06-uninstall.txt 2>&1; echo exit=$? >> /tmp/node06-uninstall.txt
```

### A7　删节点对象（1 分钟）

要在 A6 之后：agent 还在跑时删对象，它会把节点重新注册回来。

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; kubectl get node ubt-k3s-06 && kubectl delete node ubt-k3s-06 ) > /tmp/node06-delete.txt 2>&1; echo exit=$? >> /tmp/node06-delete.txt
```

做完回：「06 出集群了」。我核对集群（5 个节点、负载就绪、没有 06 的卷），再改仓库里写着 06 的几处（切法第 7 节）。

---

## B　变成 Agent 主机（等我说「B 的脚本复核过了」）

### B1　把文件拷到 06（1 分钟）

拷两样：`scripts/agent-host/` 这个目录，和我编好的 Linux 版 agentd（平台 f69e8c6，指纹记在目录里的 `agentd.sha256`，准备脚本会核对）。

```bash
scp -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node -r /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host /Users/vision-mac-trader/agent-work/agentd-build/agentd-f69e8c6-linux-amd64 vision@192.168.10.79:
```

### B2　跑准备脚本（约 10 分钟）

**这一步会下载**：Ubuntu 包、go.dev 的 Go 1.25、nodejs.org 的 Node 22（两者按官方 SHA-256 校验）、npm 上的 codex 和 claude、cursor.com 的安装脚本。跑它就算同意。它建两个用户、打开出站规则、装工具和两个 agentd 服务（装好不启动），并为两个 agentd 各生成一个平台令牌（只留在 06 上）。

```bash
ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo bash ~/agent-host/prepare-agent-06.sh' > /tmp/agent-06-prepare.txt 2>&1; echo exit=$? >> /tmp/agent-06-prepare.txt
```

做完回：「06 准备好了」。我读 `/tmp/agent-06-prepare.txt`。

### B3　登录和凭证（约 15 分钟）

**codex 登录，两个用户各一次**：会打印一个网址和一个代码，在浏览器里打开、输入代码、用你的 ChatGPT 账号确认。

```bash
ssh -t -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -u bifrost-agentd -H bash -c "cd ~ && PATH=\$HOME/.local/bin:/usr/local/lib/nodejs/current/bin:\$PATH codex login --device-auth"'
```

```bash
ssh -t -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -u bifrost-agentd-stg -H bash -c "cd ~ && PATH=\$HOME/.local/bin:/usr/local/lib/nodejs/current/bin:\$PATH codex login --device-auth"'
```

**Claude 和 Cursor 的凭证**：把 Mac Pro 上 `bifrost-agentd` 现有的两份原样拷给 06 的 PROD 用户（同一个账号，不重新生成；值不经过屏幕）。先问一次你 Mac 的 sudo 密码，再问两次节点密钥口令。

```bash
sudo -v && for f in claude-oauth.token cursor-api.key; do sudo cat "/Users/bifrost-agentd/.config/bifrost/$f" | ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 "sudo -u bifrost-agentd sh -c 'umask 077; cat > /home/bifrost-agentd/.config/bifrost/$f'" || break; done
```

**两个 Gitea 账号**（在 `http://192.168.10.73:30300`，用你的管理员账号；和 10-15 建 `agentd-mbp-dev` 一样）：

1. 建用户 `agentd-agent-06` 和 `agentd-agent-06-stg`。
2. 两个都加成 `bifrost-agents/bifrost-platform` 的协作者，权限「写」；再加成 `bifrost/bifrost-platform`（镜像）和 `bifrost/bifrost-ui`（镜像，Console 的检查要克隆它）的协作者，权限「读」。别的仓库不给。`bifrost-agents/bifrost-platform` 原有的 `main` 禁推和标签保护对新账号同样生效。
3. 用每个账号各生成一个访问令牌（只勾仓库读写），存到 06 上对应的用户下。运行后把令牌粘贴进去，回车，再按 Ctrl-D：

```bash
ssh -t -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -u bifrost-agentd sh -c "umask 077; cat > /home/bifrost-agentd/.config/bifrost/agentd-git.token"'
```

```bash
ssh -t -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo -u bifrost-agentd-stg sh -c "umask 077; cat > /home/bifrost-agentd-stg/.config/bifrost/agentd-git.token"'
```

**核对**（只读；只打印文件的权限和大小，不打印内容）：

```bash
ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo bash ~/agent-host/check-agent-06.sh' > /tmp/agent-06-check.txt 2>&1; echo exit=$? >> /tmp/agent-06-check.txt
```

做完回：「06 凭证好了」。我读 `/tmp/agent-06-check.txt`：出站探测全部 `ok`、三家已登录、`codex mcp list` 是 `[]`、凭证文件都是 600。

### B4　两个平台令牌放进 Secret（2 分钟）

令牌从 06 上读一次，直接写进对应平台的 Secret，不经过屏幕和对话。PROD 一条、STG 一条：

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; f=$(mktemp) && ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo cat /home/bifrost-agentd/.config/bifrost/agentd.token' | python3 -c 'import json,sys; print(json.dumps({"stringData":{"PLATFORM_PROD_AGENTD_AGENT_06_TOKEN":sys.stdin.read().strip()}}))' > "$f" && kubectl -n bifrost-platform-prod patch secret bifrost-platform-role-tokens --type merge --patch-file "$f"; rc=$?; rm -f "$f"; exit $rc )
```

```bash
( export KUBECONFIG=/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml; f=$(mktemp) && ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo cat /home/bifrost-agentd-stg/.config/bifrost/agentd.token' | python3 -c 'import json,sys; print(json.dumps({"stringData":{"PLATFORM_AGENTD_AGENT_06_STG_TOKEN":sys.stdin.read().strip()}}))' > "$f" && kubectl -n bifrost-platform-stg patch secret bifrost-platform-role-tokens --type merge --patch-file "$f"; rc=$?; rm -f "$f"; exit $rc )
```

做完回：「06 令牌放好了，推 PROD 接线」。我推 STG 的配置（`agentd:agent-06-stg`，我的范围），再推 PROD 的配置（`agentd:agent-06`，你这句话就是对这一个提交的同意）；两边 platform-api 各滚动一次，读到新键。

### B5　启动两个 agentd（1 分钟）

等我说「接线推上去了」再跑。

```bash
ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 'sudo systemctl enable --now bifrost-agentd.service bifrost-agentd-stg.service && sleep 20 && sudo bash ~/agent-host/check-agent-06.sh' > /tmp/agent-06-check.txt 2>&1; echo exit=$? >> /tmp/agent-06-check.txt
```

做完回：「06 的 agentd 起来了」。我核对两边 Console 上主机在线、已登记，然后起草两份放宽规则。

### B6　签放宽规则（2 分钟）

我把 `agent-config/agentrt-rules/{prod,stg}/standing-envelope-dev.yaml` 改好（PROD 的 `hosts` 加 `agent-06`，STG 的加 `agent-06-stg`，版本各加 1）并推上去之后，你跑：

```bash
cd ~/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/stg/standing-envelope-dev.yaml > /tmp/agent-06-rules.txt 2>&1 && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/prod/standing-envelope-dev.yaml --env prod >> /tmp/agent-06-rules.txt 2>&1; echo exit=$? >> /tmp/agent-06-rules.txt
```

（会问签名密钥的口令，在密码管理器「bifrost 签名密钥口令」里。）做完回：「06 规则签好了」。

### B7　停掉 Mac Pro 上的 agentd（1 分钟）

等我在线程里报 STG 两件、PROD 一件演练都走完再跑。

```bash
sudo launchctl bootout system/com.bifrost.agentd; sudo launchctl print system/com.bifrost.agentd > /dev/null 2>&1; echo "launchctl print exit=$? (113 = gone)"
```

做完回：「Mac Pro 的 agentd 停了」。我交收紧规则（去掉 `mbp-dev`，STG 上同时去掉 `gate-b`），撤掉两边配置里的 `agentd:mbp-dev` 和 `agentd:gate-b`。之后合盖 30 分钟看 PROD 上的活还在走，是验收的最后一项。Mac Pro 上的 `bifrost-agentd` 用户和它的凭证文件要不要删，到时再问你。
