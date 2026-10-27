# 4.1 P0 剩余权限负测：Owner 操作包（2026-10-26，Work 610 / 615 / 621 修订）

本包补 P0-01、P0-05 及 P0-06 的凭据/tag/临时分支检查。P0-06 main push/merge 拒绝证据仍未验证：禁止向 main 推送或请求合并，不能凭 writer PASS 关闭这两项。依据是
[S0 清单](P0-landing-s0-2026-10-24.md)、
`REPORT-landing-s0-evidence-handoff-2026-10-24.md` 和
`REPORT-landing-s0-evidence-supplement-2026-10-25.md`（后两份在正式 infra checkout）。
已完成的演练/06 main、PR merge、tag 拒绝不重做。本包完成也不等于全部 P0 完成，不自动开启 S2/S3。
以下由 Owner 在 Mac 终端执行；本片编写时没有执行线上探针、读取凭据或改动集群。

## 1. 执行前核对

先复核本工作树的脚本改动，再顺序运行下面各完整代码块。任一 FAIL、非零退出码或身份不符即停止；
不扩大权限来“修好”负例。管理员参数逐字沿用 S0 文件：
`kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml`。

- Gitea 两仓 main push/merge 和 `*` 标签白名单仍只保留 `weitingzhao`；Owner 在页面核对。
- 三套 reader 是 Code Read；演练身份和 06 两身份非管理员，只有既定分支及 PR 权限。
- Reader 和演练通过 `/user` 核对真实登录名，使用已安装的 user Read scope。06 旧 token 按原安装包只有 repository scope：下文显式启用 installed-file 来源核验，确认当前 Unix 用户和读入内存的 token 与该用户已安装文件逐字相同；若 `/user` 仅因缺 read:user 返回 403，记录来源证据并继续。401、错误登录名、其他 403 均停止，不更换被测 token。所有模式另验仓库 admin=false；来源核验不能冒充 `/user` 登录名验证。
- 桌面身份使用真实 checkout 的 Git credential lookup；只接受钥匙串返回的 `bifrost-mbp`，不调用 `store-mbp-token.sh`，不写入或更换凭据。
- Reader PR 负例会由演练身份建立临时空提交分支；桌面探针也会建立分支和 PR，可能触发 CI。选择无并行权限调整的窗口，预留 CI 容量。tag 保护错误时创建可能成功，探针判 FAIL 并清理读回；main 没有写请求。
- `python3`、Git、kubectl、SSH 均须在 PATH；06 两系统用户已有 python3。token 只经捕获管道、内存变量和子进程环境传递，不生成磁盘副本；06 既有凭据只读。无秘密的临时脚本/clone 使用 0700 目录与 umask 077，EXIT 清理，INT/TERM 转为退出。不要用调试跟踪、打印环境、cat 凭据文件或上传临时目录。

```bash
cd ~/agent-work/p0-remaining
git branch --show-current
git show 531016b -- scripts/agent-host/probe-gitea-protection.sh scripts/agent-host/test_probe_gitea_protection.py agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md
git diff 531016b HEAD -- scripts/agent-host/probe-gitea-protection.sh scripts/agent-host/test_probe_gitea_protection.py agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md
git diff HEAD -- scripts/agent-host/probe-gitea-protection.sh scripts/agent-host/test_probe_gitea_protection.py agent-config/work/multi-agent/OWNER-STEPS-p0-remaining-2026-10-26.md
bash -n scripts/agent-host/probe-gitea-protection.sh
PATH=/opt/anaconda3/bin:$PATH python3 -m pytest -q scripts/agent-host/test_probe_gitea_protection.py
```

分支应为 `w31/p0-remaining`；依次查看原提交、从原提交到 HEAD 的已提交修复（含 `726b342`）、工作树额外改动。
语法检查无输出；pytest 全部通过。此处无提交操作。

## 2. P0-01：三个 reader × 两仓

从各自 Secret 解码 username/password，并逐一核对 username；不会从 Owner 或演练 token 代测。
演练 token 仅用于搭建和清理真实 PR 分支。每个拒绝请求均使用该 reader 自己的 token。

```bash
bash -euo pipefail <<'SH'
{ set +x; } 2>/dev/null
umask 077
cd ~/agent-work/p0-remaining
ulimit -c 0
trap 'unset p0_reader p0_drill' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
read_secret() {
  kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n "$1" get secret "$2" -o json |
  python3 -c 'import base64,json,sys
d=json.load(sys.stdin)["data"]
u=base64.b64decode(d["username"],validate=True).decode()
t=base64.b64decode(d["password"],validate=True).decode().strip()
if u != sys.argv[1] or not t or "\n" in t or "\r" in t:
    sys.exit("STOP: Secret identity or token format mismatch")
sys.stdout.write(t)' "$3"
}
p0_drill=$(read_secret bifrost-platform-stg agentrt-landing-drill agentrt-landing-stg)
while read -r p0_ns p0_secret p0_login; do
  p0_reader=$(read_secret "$p0_ns" "$p0_secret" "$p0_login")
  for p0_repo in bifrost-platform bifrost-trade-infra; do
    date -u '+START P0-01 %Y-%m-%dT%H:%M:%SZ'
    PROBE_MODE=reader PROBE_EXPECT_LOGIN="$p0_login" \
      PROBE_TOKEN="$p0_reader" PROBE_SETUP_TOKEN="$p0_drill" \
      PROBE_REPO="bifrost/$p0_repo" bash scripts/agent-host/probe-gitea-protection.sh
  done
done <<'READERS'
bifrost-platform-stg bifrost-gitea-reader bifrost-platform-reader-stg
bifrost-platform-prod bifrost-gitea-reader bifrost-platform-reader-prod
cicd gitea-ci-reader bifrost-ci-reader
READERS
echo 'PASS P0-01 matrix: 3 identities x 2 repositories; exit=0'
SH
```

每组输出真实身份和仓库，`identity/read` 为非管理员、HTTP 200；以下四项各一行 `ok`：

| 检查行 | 实际请求 | 通过条件 |
|---|---|---|
| `push handshake` | GET Git `info/refs?service=git-receive-pack`，Basic auth | HTTP 403 + 端点对应的已知原因 |
| `PR open` | POST `/pulls`，head 为刚创建且领先 main 的测试分支 | HTTP 403 + 端点对应的已知原因 |
| `tag create` | POST `/tags`，唯一 `probe-…`，target 为 main | HTTP 403 + 端点对应的已知原因 |
| `protection edit` | PATCH `/branch_protections/main`，body 为 `{}` | HTTP 403 + 端点对应的已知原因 |

另须 `PR cleanup` 查询 404、`branch cleanup` 查询 404、`tag cleanup` 查询 404，末行
`VERDICT PASS mode=reader repo=… identity=…`。全矩阵应有六条 PASS verdict；仓库/身份是实际值，不需填写参数。
401 一律 FAIL，包括身份检查后 token 被撤销。空正文、未知原因、CSRF、200/201、302、404、422、5xx、连接错误均不通过。
`repository ACL denial` 表示端点对应的仓库权限拒绝；`token scope; repository ACL unverified` 只表示 token scope 拒绝，不能证明仓库 ACL。
scope 拒绝必须完整匹配 `token does not have at least one of required scope(s): [write:repository]`；Git handshake 若只返回泛化 `insufficient scope`、HTML 或空正文仍 FAIL/未验证，不能靠状态码补齐证据。PR 没有可识别的 ACL 原因时保留未验证。固定版本依据：
[API 权限中间件](https://github.com/go-gitea/gitea/blob/v1.21.11/routers/api/v1/api.go)、
[Git HTTP 权限检查](https://github.com/go-gitea/gitea/blob/v1.21.11/routers/web/repo/githttp.go)。
脚本不输出应答正文或凭据。Reader 正常拒绝时没有 PR 被创建，不留分支或标签。

## 3. P0-05：演练与 06 两身份的保护编辑

只发无字段的 PATCH，不创建分支、PR 或标签。Gitea 1.21 的
[EditBranchProtection 实现](https://github.com/go-gitea/gitea/blob/v1.21.11/routers/api/v1/repo/branch.go#L655)
仅修改显式设置的字段，未设置的列表也保留原值；`{}` 在无并发修改时保留策略字段。
服务端仍执行读改写，不能保证并发修改不被覆盖，执行时不得并行调整权限。意外 HTTP 200 仍然 FAIL，服务端可能更新规则时间戳/触发重检，
不能将其计作成功。若 Gitea 已升级，先核对当前实现仍保持该 PATCH 语义。

演练 Secret：

```bash
bash -euo pipefail <<'SH'
{ set +x; } 2>/dev/null
umask 077
cd ~/agent-work/p0-remaining
ulimit -c 0
trap 'unset p0_token' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
p0_token=$(kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n bifrost-platform-stg get secret agentrt-landing-drill -o json |
python3 -c 'import base64,json,sys
d=json.load(sys.stdin)["data"]
if base64.b64decode(d["username"]).decode() != "agentrt-landing-stg":
    sys.exit("STOP: wrong drill Secret identity")
t=base64.b64decode(d["password"],validate=True).decode().strip()
if not t or "\n" in t or "\r" in t:
    sys.exit("STOP: invalid drill token format")
sys.stdout.write(t)')
for p0_repo in bifrost-platform bifrost-trade-infra; do
  date -u '+START P0-05 drill %Y-%m-%dT%H:%M:%SZ'
  PROBE_MODE=protection PROBE_EXPECT_LOGIN=agentrt-landing-stg \
    PROBE_TOKEN="$p0_token" PROBE_REPO="bifrost/$p0_repo" \
    bash scripts/agent-host/probe-gitea-protection.sh
done
echo 'PASS P0-05 drill: 2 repositories; exit=0'
SH
```

06 的 token 不复制回 Mac，不跨系统用户共用；只把本片脚本发送到对应用户的临时目录。
远端只读自己的 `~/.config/bifrost/agentd-git.token`，不复制 token；0700 临时目录只放脚本，退出即删，原凭据不动。
SSH 参数沿用 S0 的 Owner 专用 node key：

```bash
bash -euo pipefail <<'SH'
{ set +x; } 2>/dev/null
umask 077
cd ~/agent-work/p0-remaining
p0_dir=$(mktemp -d)
chmod 700 "$p0_dir"
trap 'rm -rf "$p0_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 - "$p0_dir/remote.sh" <<'PY'
from pathlib import Path
import sys
source=Path('scripts/agent-host/probe-gitea-protection.sh').read_text()
delimiter='P0_PROBE_SOURCE_610'
assert delimiter not in source.splitlines()
prefix='''{ set +x; } 2>/dev/null
set -euo pipefail
umask 077
p0_remote=$(mktemp -d)
chmod 700 "$p0_remote"
trap 'rm -rf "$p0_remote"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cat > "$p0_remote/probe.sh" <<'P0_PROBE_SOURCE_610'
'''
suffix='''
for p0_repo in bifrost-platform bifrost-trade-infra; do
  date -u '+START P0-05 06 %Y-%m-%dT%H:%M:%SZ'
  PROBE_MODE=protection PROBE_IDENTITY_SOURCE=installed-file PROBE_TOKEN_FILE="$HOME/.config/bifrost/agentd-git.token" \
    PROBE_REPO="bifrost/$p0_repo" bash "$p0_remote/probe.sh"
done
echo "PASS P0-05 06: $PROBE_EXPECT_LOGIN x 2 repositories; exit=0"
'''
Path(sys.argv[1]).write_text(prefix+source+'\n'+delimiter+'\n'+suffix)
PY
bash -n "$p0_dir/remote.sh"
while read -r p0_user p0_login; do
  ssh -F /dev/null -o IdentitiesOnly=yes -o ConnectTimeout=15 \
    -i ~/.bifrost-owner/ssh/node vision@192.168.10.79 \
    "sudo -u $p0_user -H env PROBE_EXPECT_LOGIN=$p0_login bash -s" < "$p0_dir/remote.sh"
done <<'IDENTITIES'
bifrost-agentd-stg agentd-agent-06-stg
bifrost-agentd agentd-agent-06
IDENTITIES
echo 'PASS P0-05 06 matrix: 2 identities x 2 repositories; exit=0'
SH
```

本节总共六条 `VERDICT PASS mode=protection`；每条之前必须有正确的 `identity/read` 和
`protection edit: HTTP 403; repository ACL denial`。本模式仅缺 token scope 不算保护 ACL 已验证，仍 FAIL。06 若显示 `installed-file/Unix-user provenance`，原样贴回，保留该证据边界。
仅 GET 设置页面被拒绝、admin=false 或 HTTP 404 均不代替 PATCH 负例。

## 4. P0-06：Mac 实际 push 凭据与有限探针（main / merge 未验证）

先检查两份真实 checkout 的 credential 元数据，确认没有 Owner 缓存和未知 helper。
随后用 `git remote get-url --push --all origin` 获取展开 pushurl/rewrite 后的真实目标。只接受一个且精确匹配本仓地址的 URL（允许显式 bifrost-mbp username）；多目标或其他目标/用户名立即停止。
将真实 URL 交给 `git credential fill`，stdout/stderr 均被 Python 捕获；核对 username 后把 password 仅经子进程环境传递，不落盘或打印。
拒绝 HTTP extraHeader 或运行时 Git 配置注入，以免探针与日常凭据来源不一致。

桌面旧 token 可能只有 repository scope，故本节以钥匙串 lookup 的 username 为凭据来源证据，
不要求 `/user` 的 user Read scope，不轮换 token。另用该 token 的仓库元数据拒绝 admin=true。
这和前节 `/user` 的服务端登录名证据须分开记录，不能写成已通过 `/user` 验证。

```bash
bash -euo pipefail <<'SH'
{ set +x; } 2>/dev/null
umask 077
cd ~/agent-work/p0-remaining
ulimit -c 0
trap 'exit 130' INT
trap 'exit 143' TERM
python3 scripts/gitea/check-local-credential-identity.py --admin weitingzhao \
  --checkout "$HOME/Desktop/stocks/bifrost-platform" \
  --checkout "$HOME/Desktop/stocks/bifrost-trade-infra"
for p0_repo in bifrost-platform bifrost-trade-infra; do
  date -u '+START P0-06 %Y-%m-%dT%H:%M:%SZ'
  python3 - "$HOME/Desktop/stocks/$p0_repo" "$p0_repo" <<'PY'
import json,os,subprocess,sys,urllib.error,urllib.request
checkout,repo=sys.argv[1:3]
expected='http://192.168.10.73:30300/bifrost/'+repo+'.git'
if any(k.startswith('GIT_CONFIG') or k in ('GIT_DIR','GIT_WORK_TREE','GIT_COMMON_DIR') for k in os.environ):
    sys.exit('STOP: inherited Git configuration requires inspection')
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_TRACE') and k != 'GIT_CURL_VERBOSE'}
env['GIT_TERMINAL_PROMPT']='0'
headers=subprocess.run(['git','-C',checkout,'config','--get-regexp',r'^http\..*extraheader$|^http\.extraheader$'],
                       capture_output=True,env=env)
if headers.returncode != 1:
    sys.exit('STOP: extraHeader or unreadable configuration; do not print its value')
remote=subprocess.run(['git','-C',checkout,'remote','get-url','--push','--all','origin'],
                      text=True,capture_output=True,env=env)
urls=remote.stdout.splitlines()
allowed=(expected,expected.replace('http://','http://bifrost-mbp@'))
if remote.returncode or len(urls) != 1 or urls[0] not in allowed:
    sys.exit('STOP: actual push URL set differs from approved repository/identity; values suppressed')
url=urls[0]
result=subprocess.run(['git','-C',checkout,'credential','fill'],input='url='+url+'\n\n',
                      text=True,capture_output=True,env=env)
if result.returncode:
    sys.exit('STOP: credential lookup failed')
credential=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
if credential.get('username') != 'bifrost-mbp' or not credential.get('password'):
    sys.exit('STOP: actual Git credential is not bifrost-mbp')
token=credential['password']
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise urllib.error.HTTPError(req.full_url,code,'redirect refused',headers,fp)
req=urllib.request.Request('http://192.168.10.73:30300/api/v1/repos/bifrost/'+repo,
                          headers={'Authorization':'token '+token})
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect).open(req,timeout=30) as r:
        body=json.load(r)
except Exception:
    sys.exit('STOP: cannot verify repository access; response suppressed')
if body.get('permissions',{}).get('admin') is not False:
    sys.exit('STOP: credential is admin or permission is unknown')
print('PASS credential source: '+repo+' actual push URL Git keychain username=bifrost-mbp; repo admin=false',flush=True)
probe_env=dict(env,PROBE_MODE='writer',PROBE_TOKEN=token,PROBE_REPO='bifrost/'+repo)
result=subprocess.run(['bash','scripts/agent-host/probe-gitea-protection.sh'],env=probe_env)
if result.returncode:
    sys.exit('STOP: desktop probe failed')
print('PASS P0-06 partial: tag/branch/PR cleanup checked; UNVERIFIED main push/merge')
PY
done
SH
```

每仓核对 tag 的精确保护拒绝、临时分支创建/删除、PR 创建/关闭读回、main unchanged、no new tag 和 EXIT 清理。
必须保留 `UNVERIFIED main push/merge` 行：writer PASS 只覆盖本次已执行检查，不能证明 main push/merge 白名单生效，P0-06 这两项继续开放。
脚本 writer verdict 的 `identity=unspecified` 表示没有做 `/user`；与紧邻的 credential source 和 P0-06 行一起保存。

## 5. 清理、失败与贴回内容

成功时所有测试分支已删除、没有新标签、没有未关闭 PR。桌面探针正常留下关闭 PR 的审计记录（与 S0 原探针一致），
并非悬挂的 PR；不删除审计历史。Reader 若意外创建了 PR，脚本会按唯一 head 查找并关闭，再读回确认；
即使清理成功，该组仍 FAIL。丢失创建应答、创建途中 INT/TERM 也会按唯一 head 查找、关闭及读回；查找失败报告 head。writer 在标签写入前登记 ref，所有退出路径尝试清理并验证，清理成功不覆盖原始 FAIL。保护模式无测试对象需要清理。

脚本退出和 INT/TERM 会清临时目录；SIGKILL、断电、网络中断不能保证远端清理完成，遇此必须按输出 ref/PR 在 Gitea 两仓确认。
清理验证失败会输出 FAIL 和具体 ref/PR，绝不计 PASS。不要重复跑来掩盖失败。
HTTP 协议或正文读取异常仅记录失败状态（HTTP 0 表示无法取得完整可信响应），不打印响应正文、响应头或异常原文。
Reader 清理按 PR、分支、标签分别保护；某项失败仍继续其余已登记对象，并在最终 verdict 保留 FAIL。
若标签或分支意外获准但测试身份无权删除，由 Owner 在 Gitea 页面删除该次打印的唯一测试对象、关闭对应 PR，
再记录清理时间。main 读回变化表示并发外部改动或异常；保留证据停止，不自动 reset/force push。
本包不改权限，不存在“恢复放宽白名单”的回退。

贴回本线程：各完整代码块的脱敏输出及退出码、UTC START 行、6 条 reader verdict、6 条 protection verdict、
2 组桌面 credential source / writer verdict / P0-06 partial / UNVERIFIED 行；同时给出两仓关闭的桌面 PR 号、分支删除/无新 tag/main 未变结果。
若有 FAIL，贴检查名、HTTP 状态、具体 ref/PR 与清理结论；保留未验证项，不宣称整个 P0 已关闭。
**不要贴 token、Secret JSON、钥匙串输出、请求头、环境全文或临时目录内容。**
