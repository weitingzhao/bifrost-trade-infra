# Owner 操作单：06 出集群，当 Agent 主机

起草 2026-10-17 01:00，01:50 改成脚本（复核 230：原来的单行命令在查询失败时照样 cordon、删卷范围没锁死、读令牌失败会把空值写进 Secret、粘贴 Gitea 令牌会回显）。切法和理由：`CUT-agent-host-06-2026-10-17.md`。

**在哪做**：都在你 Mac Pro 自己的 Terminal 里，因为要用管理员 kubeconfig 和节点密钥，我不能执行。每一步是同一个脚本的一个子命令：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh check
```

每一步出错就停、退出码非 0，不打印任何凭证。每次连 06 会问一次节点密钥的口令。输出同时存在 `/tmp/agent-06-<步骤>.txt`，我读完删掉（codex 登录那一步不存）。

**怎么回**：每段末尾写了回什么，只回那句话，不要贴输出。

**两段**：A（出集群）建议周末做（US 休市），约 40 分钟。B（变成 Agent 主机）等我在线程里说「B 复核过了」再做。

---

## A　出集群

### A0　先看一眼（只读，1 分钟）

列出发布窗口、没跑完的流水线、06 上的卷（每个标明为什么可以删）、06 上的 Pod。不改任何东西。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh check
```

### A1　出集群的前半：cordon、备份、删卷、重启、drain（约 20 分钟）

一条命令按顺序做完，任何一步不对就停：

1. 有发布窗口、或有没跑完的流水线，就不开始。
2. cordon；cordon 之后再查一次流水线。
3. 把 event-radar 的卷打包到 `~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6/`，核对包是完整的、里面有那个目录，才往下走。
4. 删 06 上的卷：只删两种，event-radar 那个，和已经跑完的流水线的 local-path 工作区（逐个核对 local-path、只绑 06、PVC 对得上）。有任何一个别的卷就停，一个都不删。删完等 5 分钟，还没清干净也停。
5. polygon 两个不许驱逐的 Deployment 滚动重启，等它们就绪。
6. drain，最后核对 06 上只剩 DaemonSet。

会发生的事见切法第 3 节的表：coredns 换节点时 DNS 断几秒，redis-live-prod 和 redis-dev 的缓存清空，STG 平台重启一次。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh leave
```

中途停了：06 可能已经 cordon，这本身无害。看最后一行写的原因，回我「06 leave 停了」；条件满足后再跑同一条，做过的步骤会跳过或照样通过。

做完回：「06 drain 完了」。我核对搬走的负载都在别处就绪，然后说可以做 A2。

### A2　卸 k3s、重启，再删节点对象（约 5 分钟）

先卸 k3s 并重启（最后连接会断开，正常）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh uninstall
```

等一分钟，再删节点对象（节点还报 Ready 时它会拒绝：说明 agent 还在跑）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh delete-node
```

做完回：「06 出集群了」。我核对集群（5 个节点、负载就绪、没有 06 的卷），再改仓库里写着 06 的几处（切法第 7 节）。

---

## B　变成 Agent 主机（等我说「B 复核过了」）

### B1　拷文件、跑准备脚本（约 12 分钟）

拷 `scripts/agent-host/` 和我编好的 Linux 版 agentd（平台 f69e8c6，先核对指纹再拷）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh copy
```

跑准备脚本。**它会下载**：Ubuntu 包、go.dev 的 Go 1.25、nodejs.org 的 Node 22（两者按官方 SHA-256 校验）、npm 上的 codex 和 claude、cursor.com 的安装脚本（你 01:0x 已同意）。它建两个用户、打开出站规则、装工具和两个 agentd 服务（装好不启动），为两个 agentd 各生成一个平台令牌（只留在 06 上）。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh prepare
```

再核对一遍（出站规则逐项探测，每项都和 root 的结果对比，证明是规则挡住的，而不是对面本来就不通）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh host-check base
```

做完回：「06 准备好了」。

### B2　登录和凭证（约 15 分钟）

**codex，两个用户各登一次**：会打印一个网址和一个代码，在浏览器里打开、输入代码、用你的 ChatGPT 账号确认。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh codex-login prod
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh codex-login stg
```

**Claude 和 Cursor 的凭证**：把 Mac Pro 上 `bifrost-agentd` 现有的两份原样拷给 06 的 PROD 用户（同一个账号，不重新生成；值不经过屏幕）。会问一次你 Mac 的 sudo 密码。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh vendor-creds
```

**两个 Gitea 账号**（在 `http://192.168.10.73:30300`，用你的管理员账号；和 10-15 建 `agentd-mbp-dev` 一样）：

1. 建用户 `agentd-agent-06` 和 `agentd-agent-06-stg`。
2. 两个都加成 `bifrost-agents/bifrost-platform` 的协作者，权限「写」；再加成 `bifrost/bifrost-platform` 和 `bifrost/bifrost-ui`（两个镜像，Console 的检查要克隆 bifrost-ui）的协作者，权限「读」。别的仓库不给。`bifrost-agents/bifrost-platform` 原有的 `main` 禁推和标签保护对新账号同样生效。
3. 每个账号各生成一个访问令牌（只勾仓库读写）。下面两条会提示你粘贴，输入不显示，回车即可：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh git-token prod
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh git-token stg
```

核对：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh host-check creds
```

做完回：「06 凭证好了」。

### B3　两个平台令牌放进 Secret（2 分钟）

从 06 上读一次，核对是 64 位十六进制才写进对应平台的 Secret，不经过屏幕和对话：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh secret prod
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh secret stg
```

做完回：「06 令牌放好了，推 PROD 接线」。我推 STG 的配置（`agentd:agent-06-stg`，我的范围），再推 PROD 的配置（`agentd:agent-06`，你这句话就是对这一个提交的同意）；两边 platform-api 各滚动一次，读到新键。

### B4　启动两个 agentd（1 分钟）

等我说「接线推上去了」再跑。启动后 20 秒自动跑一遍核对：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start
```

做完回：「06 的 agentd 起来了」。我核对两边 Console 上主机在线、已登记，然后起草两份放宽规则。

### B5　签放宽规则（2 分钟）

我把 `agent-config/agentrt-rules/{prod,stg}/standing-envelope-dev.yaml` 改好（PROD 的 `hosts` 加 `agent-06`，STG 的加 `agent-06-stg`，版本各加 1）并推上去之后，你跑（会问签名密钥的口令，在密码管理器「bifrost 签名密钥口令」里）：

```bash
cd ~/Desktop/stocks && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/stg/standing-envelope-dev.yaml > /tmp/agent-06-rules.txt 2>&1 && bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/prod/standing-envelope-dev.yaml --env prod >> /tmp/agent-06-rules.txt 2>&1; echo exit=$? >> /tmp/agent-06-rules.txt
```

做完回：「06 规则签好了」。

### B6　停掉 Mac Pro 上的 agentd（1 分钟）

等我在线程里报 STG 两件、PROD 一件演练都走完再跑。会问你 Mac 的 sudo 密码：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh retire-mac
```

做完回：「Mac Pro 的 agentd 停了」。我交收紧规则（去掉 `mbp-dev`，STG 上同时去掉 `gate-b`），撤掉两边配置里的 `agentd:mbp-dev` 和 `agentd:gate-b`。之后合盖 30 分钟看 PROD 上的活还在走，是验收的最后一项。Mac Pro 上的 `bifrost-agentd` 用户和它的凭证文件要不要删，到时再问你。
