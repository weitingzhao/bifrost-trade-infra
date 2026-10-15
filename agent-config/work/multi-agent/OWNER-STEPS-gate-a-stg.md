# Owner 操作单：W-31 2.2 Gate A 在 STG 上跑之前（O15–O17 + STG 接线）

起草 2026-10-14（统筹线程）。依据：设计 v5 §5.2、§5.7（O15–O20）；平台主线 `bad7fa8`（路由第二批已合）；
2.1 操作单 `OWNER-STEPS-agentrt-21.md`（Secret `agentrt-db-runtime` 已在两个平台命名空间）；agentd 用户操作单 `OWNER-STEPS-agentd-user.md`。

**这张单解决什么**：Gate A 的测试（T01、T02、T22、T34 和 6 道基准题）要一台真的 `agentd` 去领 STG 上的活。现在缺四样：
STG 平台没连运行时库、agentd 没有令牌、没有 Gitea 账号、没装常驻服务。规则签名（O18、O19）等你回了「规则 A/B/C」再出单；PROD 发布单（O20）在 2.2 做完后。

**怎么回**：每一步做完在线程里回一句（写在每步末尾）。第 0 步是一个选择，回字母。

---

## 第 0 步　STG 平台接上运行时库：谁来推（你定）

改动只在 STG：给 `platform-api` 和 `platform-workers` 各加三个环境变量（`AGENTRT_ENV=stg`、`AGENTRT_DSN`、`AGENTRT_DB_PASSWORD` 取自 Secret `agentrt-db-runtime`，可选引用）。
推到 infra 主线后 Argo 自动同步 STG，两个 Deployment 滚动重启一次；Secret 缺了也只是运行时路由回 503，平台别的功能不受影响。回退：撤掉这个提交。

10-14 晚我准备自己推（按你定的分工，可回滚的 STG 变更由我做），被 Claude 的 auto mode 拦下（「受保护范围的基础设施变更」）。我没有绕过。

- **我的建议 A**：你在线程里回「STG 接线 A」，我把补丁写进 `k8s/overlays/platform-stg/`，本地 `kubectl kustomize` 对比后经 `push-main.sh` 推；auto mode 再拦就停下告诉你。
- B：你在 Claude 的权限设置里给这类 STG 清单改动加一条放行规则（以后同类不再问），再回「STG 接线 B」。
- C：先不接，Gate A 往后放。

补丁全文（A 或 B 都用这份）：

```yaml
# k8s/overlays/platform-stg/platform-agentrt-env.patch.yaml（kustomization.yaml 的 patches 里加一行）
apiVersion: apps/v1
kind: Deployment
metadata:
  name: platform-api
spec:
  template:
    spec:
      containers:
        - name: platform-api
          env:
            - name: AGENTRT_ENV
              value: stg
            - name: AGENTRT_DSN
              value: host=bifrost-postgres-rw.data.svc.cluster.local port=5432 dbname=bifrost_platform_stg user=platform_agentrt_stg sslmode=require
            - name: AGENTRT_DB_PASSWORD
              valueFrom:
                secretKeyRef: {name: agentrt-db-runtime, key: password, optional: true}
---
# platform-workers 同样三行（容器名也是 platform-api）
```

做完回：「STG 接线 A」（或 B、C）。

## 第 1 步　agentd 的令牌（O15）

令牌只在你的机器和 STG 的 Secret 里，不进仓库、不进对话。主体名固定 `agentd:mbp-dev`（主机号 `mbp-dev`，角色 `agentd`，平台按主体名把令牌绑定到这台主机）。

1. 生成令牌文件，放到 agentd 用户能读、别人不能读的位置（agentd 用户见 `OWNER-STEPS-agentd-user.md` 第 1 步）：

```bash
sudo -u bifrost-agentd sh -c 'umask 077; mkdir -p "$HOME/.config/agentd" && [ -s "$HOME/.config/agentd/platform-token" ] || openssl rand -hex 32 | tr -d "\n" > "$HOME/.config/agentd/platform-token"; ls -l "$HOME/.config/agentd"'
```

2. 平台这边要两处配合，**由我起草、你批**：`config/platform-auth.yaml`（STG）加一行 `name: agentd:mbp-dev, role: agentd, token_env: PLATFORM_AGENTD_MBP_DEV_TOKEN`；
   Secret `bifrost-platform-role-tokens`（STG）加同名的键。Secret 那一步要你在自己的终端跑（管理员身份）；命令等第 0 步定了、我把配置改动推上去之后给你，原样可运行。

做完回：「agentd 令牌好了」（只说好了，不要贴令牌）。

## 第 2 步　Gitea 账号与分支保护（O16）

agentd 只推 `agent/<任务号>/a<n>` 分支，不能推 `main`、不能打标签。

1. 在 Gitea（`http://192.168.10.73:30300`，用你的管理员账号）建用户 `agentd-mbp-dev`，加入 `bifrost` 组织、只给要用到的仓库写权限（第 2 轮只有 `bifrost-platform`）。
2. 在 `bifrost-platform` 仓库的「分支保护」里：`main` 禁止 `agentd-mbp-dev` 推送；「标签保护」里所有标签禁止它创建。
3. 用这个账号生成一个访问令牌（只勾仓库读写），存到 agentd 用户下：

```bash
sudo -u bifrost-agentd sh -c 'umask 077; cat > "$HOME/.config/agentd/git-token"; ls -l "$HOME/.config/agentd"'
```

（运行后把令牌粘贴进去，回车，再按 Ctrl-D；终端不回显到别处。）

做完回：「Gitea 好了」。

## 第 3 步　同意装 agentd 的常驻服务（O17）

系统级 launchd 服务、以 `bifrost-agentd` 用户运行（安装脚本 `bifrost-platform/agent/deploy/install-agentd.sh`，模板里没有本机路径）。
它连 STG 平台 `http://192.168.10.73:30878`，并发 1，只提供 `deterministic` 执行者（codex、cursor 等本机 MCP 隔离定了再加，见 A8）。

- **我的建议**：同意；安装命令等第 0–2 步做完、我在 STG 上用一次性的 agentd 进程（不常驻）先跑通一件确定性任务之后给你。
- 不同意就回「agentd 先不装」，Gate A 改成我手动起停 agentd 来跑（T01 的「launchd 拉起」那一项测不了）。

做完回：「同意装 agentd」。

---

## 之后

- 第 0–2 步齐了：我在 STG 上跑 Gate A 里不需要规则的部分（T02、T05、T06、T08、T22、T25、T32 经接口、T34），结果写回 WORK.md。
- 规则格式定了（「规则 A/B/C」）：出 O18（签名私钥）、O19（签初始规则）的单；T10、T35 和 6 道基准题要它们。
- 2.2 全部做完：PROD 发布单（O20），走审批单，三条前提成立才建。
