VERDICT: fix first
A SEQUENCE FOR (a)–(g): found
RULES THAT ONLY LACK A TEST: 3

（复核 136，Claude 的子代理，对象 `git diff 1c931da 8c4cdc5` 及结果文件全文；由统筹方按交回的全文存盘。未注明目录的路径相对 `k8s/cicd/gitea-backup/`。证据在 `~/agent-work/claude-review-136/`：`repro/test_repro_136.py`、`run1-baseline.log`、`run2-mutants.log`、`run3-repro.log`。无 Docker、网络、集群、凭据、提交。）

主问题：找到 (d) —— Pod 在 `backup.sh:228`（`mv LATEST`）执行期间收到 SIGTERM（删 Pod、drain、Job 到 1 小时期限）：bash 等 mv 结束才跑 trap，此时 `committed` 仍是 0，`cleanup`（:26–28）把已发布的目录改回 `.partial` 并删 STATUS，LATEST 却已指向它 → LATEST 指向不存在的目录，直到下一次成功。副本实测复现。(a)(b)(c)(e)(f)(g) 未找到。
P1 `backup.sh:136,140–141,155`：库集合按 SQL `ORDER BY` 排，磁盘集合按 `LC_ALL=C sort` 排；名字是「X」和「X-后缀」时两种顺序相反（`-` 小于 `.git` 的 `.`）。live 按 `scripts/k3s/bootstrap-gitea-mirrors.sh:17,22` 是组织 `bifrost` 下的 `bifrost-platform` 与 `bifrost-platform-plugin*` → 每晚死在 :141 `duplicate or unsorted repository paths`，备份永远不成功（不会假 OK；告警 26.5 小时后响）。实测：11 个生产仓库名两种排序不同；夹具放这两个名字即失败。测试和演练的名字（alpha/beta/gamma/createdN）碰不到。最小修复：库集合也过 `LC_ALL=C sort`，重复另查；`verify-stage.sh:100` 同步改。
P2 (d) `backup.sh:226–229,26–28`：序列见上。最小修复：两次 rename 期间 `trap '' TERM INT`，或 cleanup 发现 LATEST 已等于 `$stamp` 就不回滚。
P2 `backup.sh:244–250`：每个 7 天窗口留「最新」一份，窗口每天滑动，第 8 天的那份总被新的第 7 天顶掉。实测连续 18 晚：第 8 晚起恒为 8 份、最老 7 天，「每周一份留 4 周」从未出现（第 1 轮同样）。现有测试一次性种 44 天所以通过。最小修复：窗口内留最老的一份（或按 ISO 周），加一个连续多晚的测试。
P2 `backup.sh:123`：`*.wiki.git` 在 `repository` 表里没有行却被算进磁盘集合；任何仓库建了 wiki 之后三次都不等、每晚失败（实测）。最小修复：集合比较排除 `*.wiki.git`（仍归档），或随主仓库一并核对。
P2 `rehearse.sh:63,134`：种子是公开、用户名下、非镜像的仓库；live 是组织下的私有拉取镜像（`bootstrap-gitea-mirrors.sh:133,147`）。公开仓库不带 token 也能 clone，所以演练 PASS 不证明 `verify-stage.sh:74–80` 的 token 路径，也碰不到上面的 P1 和 wiki。另按阅读（未运行）：`:154,:164` 以 uid 1000 删 root 属主 `/data` 下的 `git`、`gitea` 目录本身会失败，`find -exec +` 非零，脚本在第 4 个 PASS 后中止。最小修复：种一个组织下的私有仓库对 `x` / `x-y` 加一个 wiki；重置时只清两个目录的内容。
P2 `docs/runbooks/gitea-restore.md:130–136`：恢复第 5 步让人在「这棵新数据树」上起隔离 Gitea 并提到 verify-stage.sh；该脚本会把 `HTTP_ADDR=127.0.0.1`、回环 ROOT_URL、关 SSH、关 mirror 写进 app.ini 并留下 token。直接上线则 Gitea 只听回环、镜像同步停。最小修复：写明只在一次性副本上验证，上线卷重新解包。
P2 `backup.sh:60`：在 :60–:68 之间被 SIGKILL 会留下 `.lock-reap`，它没有过期逻辑；之后只要再出现一次陈旧 `.lock`，每晚都死在 `Another run is breaking the stale NAS lock`，要人手删（实测三次都失败；告警会响，所以不算 (e)）。最小修复：`.lock-reap` 超过 3 小时同样破除。
P2-test（植入后 36 个逻辑测试全过）：① STATUS 挪到校验和之前 —— 失败路径的 cleanup 会删 STATUS，只有 SIGKILL 才留下；② 失败的运行也跑保留 —— 所有失败用例种的旧目录不是 LATEST 就在最新 7 份内，`old.exists()` 不可能失败（种 9 份时变异体确实删了一份）；③ 删掉 `verify-stage.sh:92` 的 ref 比较 —— 没有任何用例或演练故障让 clone 与清单不一致。
P3：`fetch-tools.sh:8` 单次 wget 无重试，而仓库记录新 Pod 的策略规则要几秒才生效（`k8s/data/logical-backup/cronjob-backup.yaml:42–48`）；`verify-stage.sh:74` 生成 token 只试一次（第 1 轮重试 10 次，SQLite 与刚启动的 web 并发）；`cronjob-backup.yaml:102–103` `/work` 无 sizeLimit，在控制面节点上要放约 2–3 倍 live 数据；`:38` fsGroup 不必要（emptyDir 本就可写）；stage Gitea 没关 webhook（最小修复 `GITEA__webhook__ALLOWED_HOST_LIST=loopback`）；时钟前跳后修正会一直被 `backup.sh:100` 拒绝，runbook 没写怎么恢复；`verify-stage.sh:98` 不核对 clone 数等于清单行数。
(a)–(g) 其余：(a) 未找到，前提是 NetworkPolicy 真被执行（无法在此核实）；(b) 未找到：NAS 上只有两份密文、SIZES、SHA256SUMS、VERIFIED、STATUS、LATEST 及其 tmp、锁目录，`.partial` 里也只有密文，仓库名只进 Pod 日志；(c) 未找到：以上失败都是不发布，不是假 OK；(e) 未找到不告警的情形，但 `.lock-reap` 和未来时间戳的目录都要人处理；(f) 未找到：`/data` 两层只读，token 只在 shell 变量和 `/work` 下的日志里，归档先于验证；(g) 未找到：`backup.sh:76` 无变量即返回，渲染后的 CronJob 环境只有 PATH/HOME/TMPDIR。
1. 133 的九项全部 closed。
2. Brief：1、2、4（按阅读，私有仓库未证）、5、6、7、8（除 `:226–229` 的信号窗口）、9（除 `:60`）、11、12（runbook `:130–136` 有问题）、13 met；3 not met（`backup.sh:136–141`、`:123`）；10 not met（`:244–250`）。
3. 路径 = `git/repositories/<user.lower_name>/<repository.lower_name>.git`，JOIN user 含组织；大小写用库里已存的小写名；改名、转移以库当前行为准，途中变化即集合不等、重拍；fork 是普通行。错的形状都是假失败：「X」与「X-后缀」的名字对（属主 `a` 与 `a-b`、`a.b` 同理）、`*.wiki.git`、库里没有的孤儿目录。没发现「集合相等但实际不对」。未能确认：1.21 是否按 `repository.owner_name` 取路径、迁移中或损坏状态的行、live 上有没有 wiki。
4. 出站只有两条：kube-system 里 `k8s-app=kube-dns` 的 Pod 的 UDP/TCP 53；10/8、172.16/12、192.168/16 之外任意 IPv4 的 TCP 443。无入站、无 IPv6。Service 10.43/16、Pod 10.42.x、节点和局域网 192.168.10.x 都在排除段内。排除段之外而仓库没说明的：100.64/10、169.254/16、网关的公网地址 :443。放开的 443 对整个 Pod 全程有效。
5. 跳过集合比较 → 被杀死；STATUS 提前 → 存活；失败的运行也跑保留 → 存活；去掉 age 头检查 → 被杀死。
6. 各故障都到了对应的那一行。较弱的是截断（`rehearse.sh:213–218`）：只判非零不看原因，且 96 字节切在 age 头内，没测到载荷截断。「push DURING copy」证明的是库副本与目录树之间的 push，不是拷到一半的仓库。失败时 trap 会删容器和卷。
7. 告警表达式按阅读是合法 PromQL（没有 promtool）；CronJob 存在满 26 小时且从无成功时触发；首次计划时间之前不响。
8. 没有哪一步把私钥带进集群或把明文写上 NAS。有问题的：runbook `:130–136`；`:62` 的 `kubectl wait --for=condition=complete` 在 Job 失败时要等满 3700 秒；`:69–72` 要求确认策略生效却没给命令；`restore.sh:9` 失败时不说原因。macOS 自带 `sha256sum` 对注释行只警告、退出 0。
9. Owner 命令顺序合理。缺：REPORT-2 第 5 步比 runbook 少了 STATUS 和校验和两行；没写「从合并后的 main 执行」（告警规则和 MAINTAINERS 都是整对象）；`maintainer-reconcile` 那条不是仓库写明的做法（`cronjob.yaml:7–8` 是 `kubectl apply -k`）。
10. 合并前：P1 排序；(d) 信号窗口；保留的周档；wiki；演练种子与重置；runbook；补三条缺的测试和一个名字对的测试。apply 前：改过种子的演练通过；`.lock-reap` 过期；fetch 与 token 重试；量过 live 体积后给 `/work` 设 sizeLimit；stage 关 webhook；定下 maintainer ConfigMap 的做法并从 main 执行。只有演练或第一次真实运行能定：只读 URI 对运行中 SQLite 的 `.backup`；BusyBox 工具与 bash 5.2；真 age；Gitea 在 stage 上启动、token、HTTP clone。

测试运行 3 次：基线 44 passed；五个变异体 180 例，5 failed / 175 passed；复现 8 passed。

---

## 确认轮（同一位复核方，2026-10-12，对象第 3 轮 `62fa586` 和统筹方改演练脚本的 `9dac94f`）

VERDICT: safe to merge。上一轮点名的各项全部 closed；复核方重种的六处错和另加的两处全部被测试杀死；改动处没有找到 (a)–(g) 的序列。演练里「解密、恢复、把每个仓库 HTTP clone 一遍」确实走的是令牌路径（三个种子仓库都是私有的，容器没有网络、没有已存凭据）；每个故障都到了它说的那一行。应用前必须做的只有一件：量线上数据的体积和控制面节点的空闲盘，再起第一个任务（`/work` 没有大小上限，可能造成节点磁盘压力）。不阻塞的小修四处：发布前检查目标目录不存在；锁里的开始时间文件为空时回退到目录时间；下载重试的总时长短于新 Pod 网络策略生效的约 15 秒；两处过期文字。首次真实运行要盯的：真实体积下的占用和用时、拉取镜像仓库（含 GitHub 的 `refs/pull/*`）的 fsck 和比对、网络策略是否执行、init 容器在 alpine 里以 uid 1000 写 `/tools`、同节点只读挂线上卷时的在线备份、NFS 上的锁和改名、线上 `app.ini` 的形状、Owner 的真钥解密、真实的告警。

统筹方的处理：四处小修都改了并各加一条测试（种回去各自会失败），不用 Docker 的测试 67 条通过，Docker 演练重跑通过；合并：infra `15becc5`。集群里没有应用。


END OF REPORT
