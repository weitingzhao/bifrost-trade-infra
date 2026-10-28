# Owner 操作单：TD-450 轮换 k3s 加入令牌（2026-10-28 夜班统筹准备）

**为什么**：10-25 退回 Amazon 的旧 ubt-k3s-07 盘没擦，`/etc/systemd/system/k3s-agent.service.env` 里存着当初加入用的 **server 令牌**（`/var/lib/rancher/k3s/server/node-token`）。K3s 文档原话的意思是：拿到 server 令牌的人基本等于集群管理员；能连到 `192.168.10.73:6443` 就能加一台节点进来，被调度到它上面的 Pod 的 Secret 都会落到它手里。另外：本机 MacBook 上还有一份 `~/.bifrost-k3s-node-token`（`fetch-join-token.sh` 当年存的），也是这个 server 令牌。

**做完以后**：server 令牌换新（旧的立刻 401）；同时设一个**单独的 agent 令牌**，每台 agent 的 env 里只放它（`K10…::node:…`，只能加 agent，不是管理员）。以后加节点用 1 小时 bootstrap 令牌，`install-agent.sh` 拒收 server 令牌（本分支已改，带测试）。

**花多久**：约 30 分钟，你全程在终端。01 上 k3s 重启时 API 断约 10 秒（10-03 实测：PROD/DEV daemon 丢租约后自己重启，01 上的 kube-vip 重启，CNPG operator 可能 OOM 一次后自恢复，NodePort 网关不断）。agent 重启时**正在跑的 Pod 不受影响**（unit 只杀 k3s 进程，不杀容器）。

**谁做**：你（要 01 和每台节点的 sudo 口令）。Agent 没有执行任何节点命令；所有命令都在 MacBook 上跑，脚本把令牌经 ssh 的 stdin 送到节点上 600 的临时文件，用完即删，屏幕上不显示令牌。

**什么时候做**：不在发布中（先跑 `bifrost-trade-infra/scripts/release/release.sh window`，没有窗口再开始）；最好是美股收盘后。

脚本在 infra 分支 `w31/night-1028-infra`，本机路径 `~/agent-work/night-1028/infra/scripts/k3s/`（推上 main 后也可以从你的 infra 检出跑，路径换成 `bifrost-trade-infra/scripts/k3s/`）。

---

## 0. 只读检查（2 分钟）

在 Claude Desktop 的终端面板（要输口令）里：

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh check
```

会问 node key 的口令和各台的 sudo 口令。看输出：

- 01：`agent-token: link to the server token`（预期：现在没有单独的 agent 令牌）；`probe with the current token: 200`（这是后面「旧令牌 401」的**阳性对照**，不是 200 就停）；`k3s token list` 应该没有还有效的 bootstrap 令牌（07 那张 1 小时的早过期了）。
- 每台 agent：`k3s-agent starts with: SERVER token`（02、04、05、gpu-server 预期如此）；07 预期是 `bootstrap token`（它用 1 小时令牌加入，那张令牌已经过期——**它现在重启 k3s-agent 能不能再连上，文档没写、我们也没验证过**；下面第 2 步会把它也换成 agent 令牌，这个问题随之消失）。
- `leftover: /home/vision/.join-env` 之类：旧的加入文件，里面也是旧令牌，第 3 步删。
- gpu-server 现在是 NotReady（关机）：ssh 不通是正常的，见第 2 步最后。

有任何一行 `STOP`、或与上面预期不同：停下，把输出发到统筹线程。

## 1. 01：轮换 server 令牌、设 agent 令牌（5 分钟）

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh server
```

它在 01 上依次做：确认当前令牌能通过探针（200）→ `k3s etcd-snapshot save --name pre-td450` → 把旧令牌存到 `/root/k3s-old-server-token`（600，恢复旧快照要用）→ `k3s token rotate --new-token <随机>` → 写 `/etc/rancher/k3s/config.yaml.d/50-td450-tokens.yaml`（600，`token:` 新 server 令牌，`agent-token:` 新 agent 令牌）→ `systemctl restart k3s` → 验证。

**要看到**：

```
old token -> 401 (want 401); current token -> 200 (want 200)
agent token: separate, secure format
server done
```

然后脚本打印 `kubectl get nodes`。**各台 agent 此时应仍是 Ready**：已经在跑的 agent 用证书连回，不重新出示令牌；K3s 文档只说「用旧令牌加入的节点要用新令牌重启」，没说重启前会断。**如果有哪台变成 NotReady**，立即对它做第 2 步（先做它）。

脚本最后会删掉 MacBook 上的 `~/.bifrost-k3s-node-token`。

## 2. 逐台 agent（每台约 3 分钟，一次一台，先非 PROD）

顺序：05（STG、CI）→ 04（数据层；CNPG 容器不受 agent 重启影响）→ 07（有 PROD Trade 的 Pod）→ 02（PROD 首选节点）。每台跑完看到 `Ready after = True` 再做下一台：

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh agent ubt-k3s-05 192.168.10.77
```

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh agent ubt-k3s-04 192.168.10.75
```

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh agent ubt-k3s-07 192.168.10.80
```

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh agent ubt-k3s-02 192.168.10.70
```

每台：从 01 读 agent 令牌（01 的 sudo）→ 送到节点 → 节点上 `k3s-agent.service.env` 的 `K3S_TOKEN` 换成它（原文件留一份 `.bak-td450`）→ `systemctl restart k3s-agent` → 等节点 Ready（最多 3 分钟）。看到 `k3s-agent now starts with: agent token` 和 `Ready after = True` 才算这台做完。

**gpu-server**：它现在关机。它下次开机时 k3s-agent 会拿旧 server 令牌去连、被拒（节点保持 NotReady，GPU 任务排不上）。开机后（Console 的唤醒，或电源管理器自己唤醒）立刻跑：

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh agent gpu-server 192.168.10.60
```

**以后加新节点**（例如 07 这种）：用 1 小时 bootstrap 令牌加入（`join-07.sh` 的做法），Ready 之后马上对它跑一次 `agent <节点> <IP>`，把 env 里的 bootstrap 令牌换成 agent 令牌——bootstrap 令牌过期后 agent 能否重启，文档没说，不赌。

## 3. 收尾（2 分钟）

全部 Ready 后：

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh finish
```

列出 01 上还有效的 bootstrap 令牌（不认识的用 `sudo k3s token delete <id>` 删），删掉各台的 `.bak-td450` 和残留的 `~/.join-env`（都含旧令牌）。

**7 天后**（11 月 4 日以后，那时 01 上自动的定时快照都已是新令牌之后的）：删掉旧令牌副本和轮换前的手动快照：

```bash
bash ~/agent-work/night-1028/infra/scripts/k3s/td450-rotate-token.sh forget-old
```

在此之前，**恢复轮换前的任何 etcd 快照都要用旧令牌**（K3s 文档的明确警告），所以旧令牌副本要留到那时。

## 4. 验收（TD-450 的「验收」一节）

- 第 1 步的输出：旧令牌 `401`、新令牌 `200`（同一个探针，轮换前 `200` 是阳性对照）。
- `check` 再跑一遍：每台 `k3s-agent starts with: agent token`；01 `agent-token: separate file`。
- 仓库防线：`bash bifrost-trade-infra/scripts/k3s/test_install_agent_token.sh` 全部 `ok`（统筹已跑：新脚本 6/6；旧 `install-agent.sh` 上 3 项红，阳性对照成立）。

## 5. 出问题怎么办

| 现象 | 处理 |
|---|---|
| 第 0 / 1 步在 `rotate` 之前 `STOP` | 什么都没改。把输出发到统筹线程。 |
| `STOP: the server already sets a token …` | 01 的 config 或 service env 已经写了令牌（与 install-server.sh 不符），脚本不替你合并。发输出，统筹改脚本。 |
| 第 1 步 `old token -> 200`（没被拒） | 先**不要**做第 2 步。在 01 上看 `sudo journalctl -u k3s -n 100`，发给统筹。此时 agents 都还在用旧令牌，集群照常。 |
| 01 重启后 API 起不来（`kubectl get nodes` 一直报错超过 2 分钟） | 在 01 上：`sudo journalctl -u k3s -n 100`。回退：删掉 drop-in 让 server 回到令牌文件：`sudo mv /etc/rancher/k3s/config.yaml.d/50-td450-tokens.yaml /root/ && sudo systemctl restart k3s`；再不行用快照 `pre-td450` 恢复（需要旧令牌 `/root/k3s-old-server-token`，按 K3s 文档 etcd-snapshot restore）。 |
| 某台 agent `Ready after` 不是 True | 在那台：`sudo journalctl -u k3s-agent -n 50`。`401`/`unauthorized` = 令牌没对上，重跑那台的 `agent` 步骤。别的错误发给统筹。那台的 Pod 在节点 NotReady 5 分钟后才会被驱逐到别处，有时间处理。 |
| 某台节点的 k3s 配置里写了 `token:` | 脚本拒绝（`STOP: a k3s config file sets token:`），不替你改；发输出。 |

**没有回退到旧令牌这条路**：旧令牌已泄露，回退只用于「01 起不来」的应急，之后要重新做第 1 步。

## 6. 本单依据与没核实的

- 依据：K3s 文档 `docs.k3s.io/cli/token`（`k3s token rotate`：旋转后 server 与用旧令牌加入的 agent 都要用新令牌重启；旋转前的快照恢复要旧令牌；agent 令牌可在集群启动后设置，未设时 `agent-token` 文件是 server 令牌的链接；server 令牌等同管理员）。集群事实（只读查询 10-28 00:xx CDT）：单 server 01，嵌入式 etcd，所有节点 `v1.35.5+k3s1`；01 由 `install-server.sh` 安装，没有显式令牌（随机生成）。
- **没核实**：(1) 已在运行的 agent 在 server 轮换后、自己重启前是否一直保持连接——文档没写，第 1 步后的 `kubectl get nodes` 就是检查点；(2) 用 bootstrap 令牌加入的 agent 在令牌过期后能否重启——第 2 步把 07 换成 agent 令牌后不再依赖它；(3) 探针路由 `/v1-k3s/server-bootstrap` 对 `server:<密码>` 的应答——脚本先要求轮换前 200（阳性对照）才继续，不成立就停。
- 不在本单：节点的 SSH 主机密钥、kubelet 证书（不受令牌轮换影响）；06 已出集群。
