# 你要做的：4.1 S0 一次顺序操作包（Work 564）

本包只准备 4.1 前置，不启用自动合入、不发 PROD。仓库基线 `881253d`；
**TD-432 S5–S7 和 TD-435 已应用，不重做那轮发布，不重建三套 reader。**
本片没有联网或读写 Secret，以下均是给 Owner 在自己的终端执行的步骤。
管理员参数逐字沿用 `OWNER-STEPS-td432-2026-10-24.md` §5：
`kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml`。

全包顺序：确认已有决定 → 检查 reader → 排空旧 run → RBAC/Tekton dry-run 和 apply →
收窄 Gitea 权限并建演练身份 → 五项实测及推送者证据 → 旧凭证收尾 → D-L5 正式单。
任何一步出现未解释的失败即停在该步；本包不让后面的命令掩盖前面的失败。

## 1. 确认范围，检查本片文件

信任假设**已经在 10-24 的 13 点决定中确认**，此处只是操作前核对文字，不要求再批准一遍：
受信主体是经发布单批准的 **PROD 平台代码整体、同一个 SA**。workers-only 挂载不等于进程隔离。
Owner 管理员是恢复根；桌面 Agent 使用的 `bifrost-mbp` 不是这个例外。
最终规则签名、S3 lander 身份、PROD 发布单仍在 S3，不能从这条架构决定推导出已批准。

先让统筹将本片提交整合到正式 infra checkout；不直接拿未复核工作区去操作。然后：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra
git status --short
git log -1 --format='%h %s'
test -f agent-config/work/multi-agent/P0-landing-s0-2026-10-24.md
python3 agent-config/scripts/validate_plan_view.py
```

第一条状态应无输出；log 显示已整合本片的提交；`test` 成功无输出；校验输出
`PASS: 12 nodes; references and blocking graph valid; not adopted`。文件不存在或有未提交更改先停。
读文件与校验无需回退。以下每段都在此 checkout 中执行。

## 2. 复用三套只读身份和 clone 身份

三个 Gitea 登录分别是 `bifrost-platform-reader-stg`、`bifrost-platform-reader-prod`、
`bifrost-ci-reader`。clone、mirror 元数据等待和 GitHub 同步的 Gitea 侧均复用最后一个。
不另建 clone 账号，不把它换成管理员，不把演练写令牌给 CI。

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-stg get secret bifrost-gitea-reader -o name
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-prod get secret bifrost-gitea-reader -o name
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd get secret gitea-ci-reader -o name
```

依次只打印 `secret/bifrost-gitea-reader`、同名 PROD Secret、`secret/gitea-ci-reader`，不打印值。
三个已存在就跳过下面的恢复分支。Gitea 管理页核对三人均非 Admin，`platform-readers`
团队 Code Read，其余 No Access、不能创建仓库；不在任何写团队。

**仅缺失时恢复**：在 `http://192.168.10.73:30300` 用 `weitingzhao` 登录。
账号和团队按 [TD-432 操作包 §1](OWNER-STEPS-td432-2026-10-24.md) 的完整既有步骤建立，
每个 token 选 repository Read、organization Read、user Read，隐藏输入运行对应一条：

```bash
bash scripts/gitea/put-reader-token.sh stg
bash scripts/gitea/put-reader-token.sh prod
bash scripts/gitea/put-reader-token.sh ci
```

只运行缺失的那一条；各自检查所有可见仓库只读、push handshake 被拒，然后先 server dry-run，
成功打印 `ok    Secret server dry-run passed` 和 `==> Secret … created`。
已有凭证需要轮换时，在同一命令末尾加 `replace`，例如：

```bash
bash scripts/gitea/put-reader-token.sh ci replace
```

成功末行为 `Secret cicd/gitea-ci-reader replaced`。新 token 验证失败不替换旧值。
回退用相同 `replace` 流程放回仍有效的只读 token，不能放回管理员 token，也不要删正在使用的 Secret。

## 3. 先排空旧 run，再应用仓库中的最终权限与 CI

S7 期间 applier 临时能读新旧两份 clone 凭证；本片最终 Role 只读 `gitea-ci-reader`。
先选没有发布/CI 在途的窗口，检查所有现存 run 已终结：

```bash
bash -euo pipefail <<'SH'
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd get pipelineruns,taskruns -o json |
python3 -c 'import json,sys
rows=json.load(sys.stdin)["items"]
pending=[r["kind"]+"/"+r["metadata"]["name"] for r in rows if not r.get("status",{}).get("completionTime")]
print("\n".join(pending) if pending else "PASS: all existing runs completed")
sys.exit(bool(pending))'
SH
```

只应打印 `PASS: all existing runs completed`。否则打印未完成对象，等它们终结后再跑；
不为通过检查删除或中止正在运行的任务。此检查只读，无需回退。

保留 **CI Pipeline** 的无凭证回退副本（不备份 Secret）；文件已存在则拒绝覆盖：

```bash
bash -euo pipefail <<'SH'
umask 077
mkdir -p ~/.bifrost-owner/landing-s0-2026-10-24
test ! -e ~/.bifrost-owner/landing-s0-2026-10-24/ci-platform.before.yaml
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd get pipeline bifrost-ci-platform -o yaml > ~/.bifrost-owner/landing-s0-2026-10-24/ci-platform.before.yaml
echo 'Saved previous ci-platform Pipeline (no Secret)'
SH
```

输出 `Saved previous ci-platform Pipeline (no Secret)`。这是本包唯一的 CI 回退基线，不覆盖它。
接着两个 server dry-run **全部无错**才做真实 apply：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/platform-rbac --dry-run=server
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/pipeline-ci-platform.yaml --dry-run=server
```

每个对象一行，以 `(server dry run)` 结尾，不能有 error。再执行：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -k k8s/platform-rbac
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f k8s/cicd/tekton/pipeline-ci-platform.yaml
```

RBAC 大部分 `unchanged`，`bifrost-applier-read configured`；Pipeline 为 `configured`。
`apply -k` 不会删除已从清单移除的对象。S6 已删过，以下幂等确认防止漂移遗留：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd delete rolebinding bifrost-platform-gitea-creds-stg bifrost-platform-gitea-creds-prod --ignore-not-found=true
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml delete clusterrole bifrost-platform-gitea-creds --ignore-not-found=true
```

正常无输出；若有漂移会显示 `deleted`。不要重跑旧版 S7 脚本，它会暂时放宽 applier Role。
核对：

```bash
KUBECONFIG=~/.bifrost-owner/kube/admin.yaml python3 scripts/check_platform_rbac.py --live
KUBECONFIG=~/.bifrost-owner/kube/admin.yaml /usr/bin/python3 scripts/check_admission_guards.py --live
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secret/gitea-bootstrap -n cicd --as=system:serviceaccount:bifrost-platform-stg:bifrost-platform
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secret/gitea-bootstrap -n cicd --as=system:serviceaccount:bifrost-platform-prod:bifrost-platform
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secret/gitea-git-credentials -n cicd --as=system:serviceaccount:cicd:bifrost-applier
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i get secrets -n cicd --as=system:serviceaccount:cicd:default
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml auth can-i create pods -n cicd --as=system:serviceaccount:cicd:default
```

两个脚本退出 0，无 FAIL；准入脚本末行 `ok: admission files match the actuation policy`。
五条 can-i 都应 `no`（`no` 本身退出非 0，是预期；不要用 `&&` 串这五条）。
`yes` 或连接/权限检查错误均不是通过。

**回退**：CI Pipeline 本身应用后异常，可先检查再恢复存下的对象：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply --dry-run=server -f ~/.bifrost-owner/landing-s0-2026-10-24/ci-platform.before.yaml
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply -f ~/.bifrost-owner/landing-s0-2026-10-24/ci-platform.before.yaml
```

输出 Pipeline `(server dry run)` / `configured`。若 resourceVersion 冲突，停止并重新核对，不强覆盖。
RBAC 收窄不回退成 admin 可读：reader 不通按第 2 节修凭证；旧 run 遗漏则保持落地关闭、完成旧 run 排障。
不可直接 apply `881253d` 的整套 RBAC，否则会重新授予管理员读取权限。

## 4. 收窄 main/PR/tag，创建唯一的 STG 演练身份

先在 Gitea 两仓 `bifrost-platform`、`bifrost-trade-infra` 的 Settings → Branches：
截图保存原规则（规则里只有名字，不含 token），main 的 push/merge whitelist 移除 `maintainers`
及所有 Agent 可用账户，仅保留 `weitingzhao` 恢复根；不启用 force push 或 deploy-key push。
Settings → Tags 的 `*` 规则同样只留 Owner；标签规则没有可复用 API，必须在页面核对。
确认没有更早匹配 main 的重叠规则。S3 才给 platform 加 `agentrt-lander`；infra 等 S6。
现在不要运行 `store-mbp-token.sh` 恢复桌面权限。

建立 `landing-drill` 团队：只选这两个仓库，不选 All repositories，不准建仓库；General Access，
Code Write，Pull Requests Write（为了执行真实 PR merge 拒绝探针），其余 No Access，不选 Administrator。
新账号 `agentrt-landing-stg`、邮箱 `agentrt-landing-stg@bifrost.invalid`，非管理员，
只加这个团队，不加 `maintainers`。密码可用既有流程生成：

```bash
openssl rand -base64 24 | tr -d '\n' | pbcopy
```

无终端输出，密码在剪贴板。无痕窗口用该账号登录，在 Settings → Applications 建 token
`landing-drill-2026-10-24`：repository Read and Write、organization Read、user Read，其余 No Access。
复制 token 后运行已有安装脚本的新固定模式：

```bash
bash scripts/gitea/put-reader-token.sh drill
pbcopy < /dev/null
```

隐藏输入不会上屏；先验证非管理员、仅两仓可写、main user_can_push=false、全分页无额外写仓，
再 server dry-run，末行 `Secret bifrost-platform-stg/agentrt-landing-drill created`；清剪贴板无输出。
此时没有 Pod 使用它，S2 才挂载。若 Secret 已存在，先核对来源，需要轮换时运行：

```bash
bash scripts/gitea/put-reader-token.sh drill replace
```

输出 `replaced`；它不能替代五项实测。回退本节：在 Gitea 撤销这个 token、移除新账号的团队成员关系，
并在尚未挂载的 S0 删除 Secret：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-stg delete secret agentrt-landing-drill
```

输出 `secret "agentrt-landing-drill" deleted`。main 白名单保留 Owner-only，安全回退是暂停落地；
若需恢复旧人员授权，要 Owner 明确另定，不能自动恢复 `maintainers` 来让 Agent 绕过 P0。

## 5. 五项权限、真实推送者和 CI 验收

先核对页面规则，再做**真实拒绝探针**。该探针会尝试推一个空提交到 main、建 tag、合 PR；
规则错误时可能真的成功，所以仅在第 4 节收窄并读回后运行。成功时清分支、关闭 PR，保留一张关闭的 PR。
演练 token 只写 Owner 私有临时文件，退出自动删除，不能把该文件、命令输入或 token 放进线程。

```bash
bash -euo pipefail <<'SH'
set +x
umask 077
landing_probe_dir=$(mktemp -d)
trap 'rm -rf "$landing_probe_dir"' EXIT
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-stg get secret agentrt-landing-drill -o json |
python3 -c 'import base64,json,sys; sys.stdout.write(base64.b64decode(json.load(sys.stdin)["data"]["password"]).decode())' > "$landing_probe_dir/token"
for landing_repo in bifrost-platform bifrost-trade-infra; do
  PROBE_TOKEN_FILE="$landing_probe_dir/token" PROBE_REPO="bifrost/$landing_repo" PROBE_BRANCH_PREFIX=land/stg/_probe bash scripts/agent-host/probe-gitea-protection.sh
done
SH
```

每仓应八条 `ok`，包含 main push refused、tag protected、PR merge refused、创建/删除 `land/stg/_probe/…`、
main unchanged、no new tag，末行为 `all as expected; left behind: closed pull request #…`。
其他 HTTP 错误、没达到可 merge 状态、或误合入都报 FAIL，不能当“拒绝通过”。
**回退**：正常探针自清；失败则根据输出的具体 ref/PR 在页面关闭 PR、删除测试分支。
main 若移动，先停止验收并记录 SHA，由 Owner 审核 revert；不能重置或强推 main。

对每个身份还必须记录“改保护”返回 401/403；仓库权限元数据 admin=false 只作辅助。
用该身份访问 Gitea 保护设置/提交无变化的保护编辑，记录拒绝应答，不能用 Owner 浏览器的登录态冒充。
三套 reader 的写握手应拒绝；06 两用户也必须分别做真实 main/PR/tag 负测。
既有的 06 基础探针可先跑：

```bash
bash scripts/agent-host/agent-06-owner.sh probe-protection
```

它只覆盖 **STG 用户与 primary-probe**，会输出同类八条 ok，不能代替本轮两仓、两用户全矩阵。
两仓、两用户用同一脚本从 stdin 发送，在各自用户环境里读自己的 token：

```bash
bash -euo pipefail <<'SH'
for landing_user in bifrost-agentd-stg bifrost-agentd; do
  for landing_repo in bifrost-platform bifrost-trade-infra; do
    ssh -F /dev/null -o IdentitiesOnly=yes -o ConnectTimeout=15 -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 \
      "sudo -u $landing_user -H env PROBE_REPO=bifrost/$landing_repo bash -s" < scripts/agent-host/probe-gitea-protection.sh
  done
done
SH
```

每组打印用户、仓库、八条 ok 和关闭 PR 号；四组都通过才覆盖 06。回退同上面的探针，
不复制 PROD token 给 STG、不把 token 上传。桌面 `bifrost-mbp` 的 main/PR 拒绝也须留证据。

在两个仓库的 **Activity** 中找到上面的 `land/stg/_probe/…` push，保存真实登录名、ref、
before/after SHA、时间及事件页面引用。应为 `agentrt-landing-stg`，不是 commit author 或 Work 尾注。
若 Activity 或现有审计无法给出实际推送者，本项写 `unverified`，不得以作者名补足 ★。
只读看 Activity 不需回退。

CI：统筹后续用受控 platform 测试分支做 vet 种错及修复，参照仓库
`scripts/cicd/test_landing_s0.py` 的 `context.WithCancel` 丢弃 cancel 用例；
build/普通 test 绿而完整 vet 红，修复后 CI 绿。S0 本次只跑了离线实际脚本，不伪造集群 run。
最近成功的 platform CI 结果可这样读（参数分支名不能代替实际 SHA）：

```bash
bash -euo pipefail <<'SH'
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd get pipelineruns -l tekton.dev/pipeline=bifrost-ci-platform -o json |
python3 -c 'import json,re,sys
rows=[r for r in json.load(sys.stdin)["items"] if any(c.get("type")=="Succeeded" and c.get("status")=="True" for c in r.get("status",{}).get("conditions",[]))]
if not rows: sys.exit("STOP: no successful platform CI")
r=max(rows,key=lambda x:x["metadata"]["creationTimestamp"])
values={v["name"]:v["value"] for v in r["status"].get("results",[])}
print(r["metadata"]["name"])
for key in ("platform-commit","ui-commit","infra-commit"):
 value=values.get(key,"")
 if not isinstance(value,str) or not re.fullmatch("[0-9a-f]{40}",value): sys.exit("STOP: missing actual clone result: "+key)
 print(key,value)'
SH
```

输出 run 名和三行 40 位 SHA；旧 run 缺字段会 STOP，须等新 CI。这只是审计读取，
S3 还要按正确 P、prepared 之后最新一次 CI 与资格判定选 run，不能直接用“最近成功”放行。
同时核对新 CI TaskRun 实际使用 default、测试步骤没有凭证挂载及 `.git/config` 没有凭证；
只记录布尔结论和对象引用，不把 config/环境全文打印。任何测试回滚仅关闭测试 PR、删除受控分支。

## 6. 旧凭证不能因 S7 切换就算失效（TD-432 S8）

完成 run 排空后，旧 `gitea-git-credentials`、旧管理员 token 的副本仍要按 TD-432 S8 清点、吊销。
S7 切新 reader 不是撤销凭证；这也是 P0 的必需证据。复用已有轮换脚本，不新建第四套 reader：

```bash
bash scripts/gitea/rotate-admin-token.sh check
```

它只打印身份及可读性，不能有 NOT DONE。Owner 在 Gitea 的 `weitingzhao` Applications 建新的管理员 token，
按既有 TD-432 操作规则复制后运行（隐藏输入）：

```bash
bash scripts/gitea/rotate-admin-token.sh rotate
```

输出 admin/reader 分别核验的结果与 `==> rotated…`；脚本不写 reader。按其提示先确认新管理员与三套 reader 可用，
然后在 Gitea 吊销本次盘点里的**每个旧 token**，不只吊销公开历史那两个。
再运行历史泄漏检查：

```bash
bash scripts/gitea/rotate-admin-token.sh revoked
```

输出旧历史 token `HTTP 401`、当前 admin 与 reader 可用。这个脚本只证明历史 blob 中的 token 已拒绝，
本次盘点额外 token 也须各自试一次并得到 401；任何未盘点副本都使 P0 保持未验证。
此步骤**不能靠回滚到旧管理员 token恢复**；新 token 有问题再走 rotate，不复活已吊销 token。

最后才退役旧 clone Secret：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd delete secret gitea-git-credentials --ignore-not-found=true
```

存在则 `deleted`，不存在无输出。该删除没有复原旧泄漏凭证的回退；修复用第 2 节只读身份。
`gitea-bootstrap` 搬出 cicd 是 TD-432 S8 的独立剩余项：当前 `lib.sh` 和轮换脚本仍读取 cicd，
不能只移动 Secret 让 Owner 恢复脚本失效。本片没有冒造一个不存在的搬迁脚本；
在对应 S8 消费方切换、回退与实证就绪前，记录该缺口，P0 不签完成，不打开 S2/S3。

## 7. D-L5：先完整归档，再批 mission 级单

使用 [D-L5 票据草案](TICKET-D-L5-landing-s0-2026-10-24.md)。
它列出 13 个 mission 的边界和 19/20 计数差异，**不是已经创建的 Console 审批单**。
本次任务禁止联网，不能虚构审批号、归档位置、SHA 或执行结果。

统筹按草案补齐每个 mission 的全部任务、accepted attempt、SHA、归档位置和校验值，
归档读回通过后用现有 C/D 审批入口建具体单，Owner 在 Console **For you** 核对后批准。
批准理由第一段必须写：这会给所列整个 mission 设置 no_merge，下一轮 agentd 就可能删除分支，
不会再等 24 小时；没有执行自动合入。不要在终端手写 UPDATE，也不批“全部旧任务”的通配单。

预期结果是审批对象有正式 ID、批准与执行事件，mission 的 no_merge 理由可读，归档仍可验证。
“按推荐”的设计回答不能代替这张写库审批。
回退：尚未批准可拒绝/取消；已标记但未清理须另走更正单；分支被删则从已验归档恢复，不能仅清空 no_merge。

## 8. 收口记录

P0 表每行补实测引用；保留 run UID、实际 SA、三仓 clone SHA、真实推送者和拒绝应答。
S0 完成必须同时具备全部 P0、CI 阳性对照、D-L5 处置记录；不能用一条 pytest PASS 代替。
本片交付仅仓库准备；S2/S3、lander Secret/白名单和规则签名不会自动开始。
