# 你接下来要做的（Gate A 在 STG 上跑起来之前），按顺序

起草 2026-10-14 23:05（统筹线程）。取代 `OWNER-STEPS-gate-a-stg.md` 第 1、2 步里的命令（那里的令牌路径和安装脚本对不上，以本页为准）。

**现在的状态**：STG 上的平台已经是新代码，运行时连上了自己的库（22:47）。规则、计划变更、进度投影、主机首次登记都在平台主线上。下面几步做完（第 6 步 10-15 加的：装 agentd），我就能在 STG 上让 agentd 真的领活、跑 Gate A。

每一步做完在线程里回一句（写在每步末尾）。命令都能原样运行；令牌、口令不进仓库、不进对话。

---

## 1. STG 运行时库补上第 5 个迁移（约 1 分钟）

STG 的库是下午迁移的，只到第 4 个；第 5 个（`attempt_cancelled`，保全采纳要用）在新镜像里。

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git pull -q --ff-only && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl create -f k8s/agentrt-migrate/stg/job.yaml )
```

做完回：「迁移跑了」。我用只读账号核对迁移表变成 5 行。

## 2. agentd 的系统用户（只在还没建时做）

先看有没有：

```bash
id bifrost-agentd
```

报「no such user」就按 `OWNER-STEPS-agentd-user.md` 第 1 步建，**连同 codex 的三行**（建 `.local/bin`、链接 codex、`codex login --device-auth`），**再做它的第 3 节（cursor-agent 安装和登录）**。

（10-15 10:36 补：Gate A 的 6 道基准题按设计是「Cursor 写、Codex 复核」；评审不能由作者同一家做（T08），codex 写的活只有 codex 能评审，走不完。所以规则草稿改了两处（你签之前，见 `agentrt-rules/stg/`）：`job-implementer.yaml` 里 Cursor 从「资格考核中」改成「试用」（能领活、受观察），常备授权的执行者加上 Cursor。第 3 节要从 cursor.com 下载安装脚本，是你的决定：**我的建议是装**；不装的话基准题这一项过不了，Gate A 其余各项不受影响。）

（10-15 10:03 更正：原来写「Gate A 第一批只用确定性执行者，codex 登录以后再做」是错的。规则草稿里实现类任务唯一在岗的执行者是 codex（`job-implementer.yaml`），确定性执行者只做验收；不登录 codex，agentd 一件实现活都领不到。）

## 3. agentd 的令牌（O15，约 2 分钟）

生成令牌文件（属主 bifrost-agentd，权限 600；已有就不覆盖）：

```bash
sudo -u bifrost-agentd -H sh -c 'umask 077; mkdir -p "$HOME/.config/bifrost" && [ -s "$HOME/.config/bifrost/agentd.token" ] || openssl rand -hex 32 | tr -d "\n" > "$HOME/.config/bifrost/agentd.token"; ls -l "$HOME/.config/bifrost"'
```

把同一个令牌放进 STG 的 Secret（平台按名字 `agentd:mbp-dev` 把它绑定到主机 `mbp-dev`；这一项的配置 infra `052a5ee` 已上 STG）：

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; f=$(mktemp) && sudo -u bifrost-agentd -H sh -c 'cat "$HOME/.config/bifrost/agentd.token"' | python3 -c 'import json,sys; print(json.dumps({"stringData":{"PLATFORM_AGENTD_MBP_DEV_TOKEN":sys.stdin.read().strip()}}))' > "$f" && kubectl -n bifrost-platform-stg patch secret bifrost-platform-role-tokens --type merge --patch-file "$f"; rm -f "$f" )
```

做完回：「agentd 令牌好了」。我重启 STG 的 platform-api 让它读到新键。

## 4. Gitea 账号与分支保护（O16，约 8 分钟）——**等你回「Gitea A / B」再做**

（10-15 10:07 更正：`bifrost/bifrost-platform` 是 GitHub 的拉取镜像，不接受推送，原来这一步照做也推不上去。下面按建议 A 写；你选 B 我改这一节。）

agentd 从镜像克隆、只往 `bifrost-agents/bifrost-platform` 推 `agent/<任务号>/a<n>` 分支，不能推 `main`、不能打标签。

1. 在 Gitea（`http://192.168.10.73:30300`，你的管理员账号）建组织 `bifrost-agents`，在里面建一个**空的私有仓库** `bifrost-platform`（不要初始化 README，不要设成镜像）。
2. 建用户 `agentd-mbp-dev`；把它加成 `bifrost-agents/bifrost-platform` 的协作者，权限「写」；再加成 `bifrost/bifrost-platform`（镜像）的协作者，权限「读」（克隆用）。别的仓库不给。
3. `bifrost-agents/bifrost-platform` 的「分支保护」：加一条规则，分支名 `main`，禁止推送；「标签保护」：标签名 `*`，不允许任何人创建。
4. 用 `agentd-mbp-dev` 生成访问令牌（权限只勾 repository 的读写），存进 agentd 用户下（运行后粘贴令牌，回车，Ctrl-D）：

```bash
sudo -u bifrost-agentd -H sh -c 'umask 077; mkdir -p "$HOME/.config/bifrost"; cat > "$HOME/.config/bifrost/agentd-git.token"; ls -l "$HOME/.config/bifrost"'
```

做完回：「Gitea 好了」。

## 5. 签名密钥和指纹（O18，约 1 分钟）

规则和发版策略共用这把密钥（发版策略从 10-10 起也在等它）。没有就生成（已有会跳过）：

```bash
test -f ~/.ssh/bifrost_release_owner || ssh-keygen -t ed25519 -C bifrost-release-owner -f ~/.ssh/bifrost_release_owner
```

```bash
ssh-keygen -lf ~/.ssh/bifrost_release_owner.pub
```

做完回：「指纹 SHA256:……」（把输出里 `SHA256:` 开头那段贴进线程；它是公开的）。

## 6. 把 agentd 装成系统服务（O17，约 1 分钟；第 2–4 步做完就能做，按「Gitea A」写）

agentd 以 `bifrost-agentd` 用户运行，从镜像 `bifrost/…` 克隆、往 `bifrost-agents/…` 推，连 STG 平台。二进制是平台主线 `296468b` 编的（`~/agent-work/build/agentd-296468b/SHA256SUMS` 记了指纹）。规则还没签时它只会空转（平台不派活），不碍事。

```bash
sudo install -d -m 755 /usr/local/libexec/bifrost && sudo install -m 755 ~/agent-work/build/agentd-296468b/agentd /usr/local/libexec/bifrost/agentd && sudo AGENTD_GIT_PUSH_BASE=http://192.168.10.73:30300/bifrost-agents bash ~/agent-work/build/agentd-296468b/install-agentd.sh bifrost-agentd /usr/local/libexec/bifrost/agentd http://192.168.10.73:30878/api/v1/agentrt mbp-dev exec:codex=openai,exec:cursor=cursor-mix,exec:deterministic=local http://192.168.10.73:30300/bifrost
```

最后一行打印 `agentd installed: …` 就是装好了。做完回：「agentd 装好了」。我从平台这边看它是否在轮询（主机 `mbp-dev` 出现在进展的主机列表里）。

---

## 这五步之后

1. 我：把指纹编进平台（信任锚变更），发 STG（约 30 分钟）。
2. 你：签 8 份规则，一条命令（O19，`OWNER-STEPS-rules-o18-o19.md` 第 2 步）。没有签过的并发规则，平台一件活都不派——这是我们定的最严默认，所以这一步必须在 agentd 跑活之前。
3. （已并入上面第 6 步：把 agentd 装成系统服务。10-15 更正：原来写「我用一次性的 agentd 进程跑通」做不到——agentd 以 `bifrost-agentd` 用户运行、令牌只有它能读，起进程要 sudo。）
4. 我：在 STG 上提一件小 mission，看 agentd 领活、跑、交、验收走通一遍，再跑 Gate A，结果写回 WORK.md。
