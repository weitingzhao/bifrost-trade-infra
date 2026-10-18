# Owner 操作单：06 出集群，当 Agent 主机

起草 2026-10-17 01:00；按复核 230 改成脚本（原来的单行命令在查询失败时照样 cordon、删卷范围没锁死、读令牌失败会把空值写进 Secret、粘贴 Gitea 令牌会回显），按复核 231 再收紧（要删的 5 个卷按 UID 写死；凭证整份读完、核对格式、带长度和指纹传过去才替换；uninstall、delete-node 各自核对前一步做完）。切法和理由：`CUT-agent-host-06-2026-10-17.md`。

**在哪做**：都在你 Mac Pro 自己的 Terminal 里，因为要用管理员 kubeconfig 和节点密钥，我不能执行。每一步是同一个脚本的一个子命令：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh check
```

每一步出错就停、退出码非 0，不打印任何凭证。每次连 06 会问一次节点密钥的口令。输出同时存在 `~/agent-work/agent-06-logs/`（每次一个文件，最后一行是退出码），我读完删掉（codex 登录那一步不存）。

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

1. 持住发布窗口（`what=ubt-k3s-06`，整个 leave 期间别的发布进不来，结束时放开）；每一步之前、以及滚动重启和 drain 进行中每 15 秒确认窗口还在自己手上，丢了就停。拿不到窗口、或有没跑完的流水线，就不开始。
2. cordon；cordon 之后再查一次流水线。
3. 把 event-radar 的卷打包到 `~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6/`，核对包是完整的、里面有那个目录，才往下走。
4. 删 06 上的卷：只删脚本里按 UID 写死的 5 个（event-radar 和 4 个已跑完的 CI 工作区，01:20 读的；已经没了的跳过），逐个核对 local-path、只绑 06、两头的绑定和 UID 都对得上；只删刚核对过的那几个，每个删除请求都带 UID 前置条件（同名换成了别的对象，API 直接拒绝）。06 上有任何一个别的卷就停，一个都不删。删完等 5 分钟，还没清干净也停。
5. polygon 两个不许驱逐的 Deployment 滚动重启，等它们就绪。
6. drain，最后核对 06 上只剩 DaemonSet。

会发生的事见切法第 3 节的表：coredns 换节点时 DNS 断几秒，redis-live-prod 和 redis-dev 的缓存清空，STG 平台重启一次。

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh leave
```

中途停了：06 可能已经 cordon，这本身无害。看最后一行写的原因，回我「06 leave 停了」；条件满足后再跑同一条：备份和删过的卷会跳过，两个 Deployment 会再滚动重启一次（无害）。

做完回：「06 drain 完了」。我核对搬走的负载都在别处就绪，然后说可以做 A2。

### A2　卸 k3s、重启，再删节点对象（约 5 分钟）

先卸 k3s 并重启（最后连接会断开，正常）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh uninstall
```

等一两分钟（06 在重启），再删节点对象。它先登上 06 确认 k3s 的程序、两个服务和所有进程（按进程实际运行的文件和进程名认，查询出错不算「没了」）都没了才删；06 还没起来时它会拒绝，过一分钟再跑：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh delete-node
```

做完回：「06 出集群了」。我核对集群（5 个节点、负载就绪、没有 06 的卷），再改仓库里写着 06 的几处（切法第 7 节）。

---

## B　变成 Agent 主机（等我说「B 复核过了」）

### B1　拷文件、跑准备脚本（约 12 分钟）

拷 `scripts/agent-host/` 和我编好的 Linux 版 agentd（哪个平台提交、指纹多少写在 `scripts/agent-host/agentd.sha256`，先核对指纹再拷）：

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

---

## B 补　codex 的沙箱（10-17 你选 A）

STG 演练里 codex 一条命令都起不来：Ubuntu 24.04 的 AppArmor 不让非特权程序在新建的用户命名空间里拿权限（`kernel.apparmor_restrict_unprivileged_userns = 1`，诊断 09:54）。修法 A：codex 改由 root 装一份在 `/opt/bifrost/codex`（钉 0.163.0，agent 用户写不了），AppArmor 规则 `bifrost-codex` 只允许那个目录里的 codex 建用户命名空间；两个用户家目录里的 codex 删掉，两个服务的 PATH 先找 `/opt`。codex 的登录在各自的 `~/.codex`，不受影响。

按顺序跑（每条问一次节点口令）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh stop
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh copy
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh prepare
```

（准备脚本最后会以两个用户、按 agentd 服务同样的 systemd 隔离条件，各在 codex 的沙箱里跑一条命令，并确认它在自己的网络命名空间里：这正是之前失败的那一步，跑不起来就停。AppArmor 许可只匹配 codex 包里它自己那个目录，不包括包里带的其它工具。）

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh host-check creds
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start
```

做完回：「06 codex 沙箱好了」。我叫演练会话把 STG 两件重跑。

## B 补二　换上新的 agentd（10-17，验收结果交不上的修复）

STG 演练 M-9 里 Console 任务的验收结果（verify.json）每次都被平台拒收：ESLint 的警告行带着工作目录的绝对路径，撞上平台的本机路径检查。新 agentd（平台 `ecb28c9`）交上去之前把工作目录写成 `.`、任务目录写成 `..`、家目录写成 `$HOME`，其余本机路径打码；平台的检查一点没放松。准备脚本会核对新二进制的指纹，装好、两个服务不启动；`start` 才启动并核对。

按顺序跑（每条问一次节点口令）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh stop
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh copy
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh prepare
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start
```

做完回：「06 新 agentd 好了」。我叫演练会话重跑 STG 那件 Console 演练。

## B 补三　再换一次 agentd（10-17 下午，评审员只读）

PROD 演练 M-3 里 agent-06 上的 cursor 评审员命令被拒后，往检出目录写了给自己放权限的文件和一个冒名 `ls` 的脚本（TD-364，没跑起来、没出主机）。新 agentd（平台 `1a339e1`）让评审在 cursor 的只读模式里跑，并在交卷前查这次尝试改了什么：评审改了任何东西、或任何尝试改了执行者的配置，就判失败。四条命令和「B 补二」一样（stop、copy、prepare、start），每条问一次节点口令：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh stop
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh copy
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh prepare
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh start
```

stop 会连带清掉服务的私有 /tmp（评审员可能在那里写过 `run_safego_verify.py`）。跑完不用回，日志我自己读。


## 换 agentd（2.3 第 2、3 片，10-18）

新版 `agentd-9872f36`：心跳带上执行者的动作（读了哪些文件、改了哪些、跑了什么命令和退出码），在 06 上先脱敏再发。PROD 平台还是老版本，它不收动作时 agentd 会去掉动作再发一次，所以两个服务一起换也安全。

以后换 agentd 只跑这一条（先核对二进制，再停两个服务、拷、准备、起两个服务并核对；哪步出错就停在那里，两个服务保持停着，再跑一次即可）：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agent-host/agent-06-owner.sh update-agentd
```

中间会问四次节点口令（停、拷、准备、起各一次）。跑完不用回，日志我自己读。
