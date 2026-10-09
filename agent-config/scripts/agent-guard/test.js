#!/usr/bin/env node
/* preflight.js 回归测试 —— 通过 Node 直接喂 stdin，避免测试夹具本身被 guard 拦截。 */
'use strict'
const { spawnSync } = require('node:child_process')
// 相对自身定位，随治理层整体搬迁而不失效
const GUARD = require('node:path').join(__dirname, 'preflight.js')

const bash = c => ({ hook_event_name: 'PreToolUse', tool_name: 'Bash', tool_input: { command: c } })
const tool = (n, i) => ({ hook_event_name: 'PreToolUse', tool_name: n, tool_input: i })

// 用拼接构造敏感字符串，避免本文件自身触发任何静态扫描
const K = 'k' + 'ill'
const PK = 'p' + K
const SVC_API = 'platform' + '-api'
const SVC_CON = 'platform' + '-console'
const OPCMD = 'ib:operator' + ':cmd'
const APPR = '/api/v1/' + 'approvals/'
const APPROVE_URL = APPR + 'req-1/' + 'approve'
const REJECT_URL = APPR + 'req-1/' + 'reject'
const TOKEN_FILE = 'mcp-tokens' + '.env'
const ADMIN_KEY = 'PLATFORM_' + 'ADMIN_TOKEN'
const HASH_PAGE = '#' + 'approvals'
const OWNER_DIR = '.bifrost-' + 'owner'
const OWNER_ENV = 'owner' + '.env'
const KUBE_OK = '.kube/bifrost-k3s.yaml'

const cases = [
  // ── D10 应拦截 ──
  ['D10', 'DENY', 'kubectl scale daemon --replicas=1', bash('kubectl scale deploy/daemon -n bifrost-stg --replicas=1')],
  ['D10', 'DENY', 'XADD ' + OPCMD, bash('redis-cli XADD ' + OPCMD + ' MAXLEN 1000 op place_order')],
  ['D10', 'DENY', 'LPUSH ' + OPCMD, bash('redis-cli LPUSH ' + OPCMD + ' payload')],
  // TD-21：真的在写 —— 不论经 redis-cli 的参数、管道、heredoc，还是客户端代码，派生流同样拦
  ['D10', 'DENY', 'kubectl exec redis-cli XADD ' + OPCMD + ':dev',
    bash('kubectl -n data exec deploy/redis-ib -- redis-cli --user u XADD ' + OPCMD + ':dev "*" op ping')],
  ['D10', 'DENY', 'echo XADD | redis-cli', bash('echo "XADD ' + OPCMD + ' * op ping" | redis-cli')],
  ['D10', 'DENY', 'redis-cli <<heredoc XADD', bash('redis-cli <<EOF\nXADD ' + OPCMD + ' * op ping\nEOF')],
  ['D10', 'DENY', 'redis-cli DEL ' + OPCMD, bash('redis-cli DEL ' + OPCMD)],
  ['D10', 'DENY', 'python -c r.xadd(' + OPCMD + ')',
    bash('python3 -c "import redis; redis.Redis().xadd(\'' + OPCMD + '\', {\'op\': \'ping\'})"')],
  ['D10', 'DENY', 'python heredoc r.xadd(' + OPCMD + ':stg)',
    bash("python3 - <<'EOF'\nimport redis\nr = redis.Redis()\nr.xadd('" + OPCMD + ":stg', {'op': 'ping'})\nEOF")],
  ['D10', 'DENY', 'node client.xAdd(' + OPCMD + ')',
    bash('node -e "client.xAdd(\'' + OPCMD + '\', \'*\', {op: \'ping\'})"')],
  ['D10', 'DENY', 'execute_command("XADD", ' + OPCMD + ')',
    bash('python3 -c "r.execute_command(\'XADD\', \'' + OPCMD + '\', \'*\', \'op\', \'ping\')"')],
  ['D10', 'DENY', 'IbOperatorClient.request（流名不出现在命令里）',
    bash('python3 -c "from bifrost_core.ib_operator.client import IbOperatorClient as C; C.from_merged_config(cfg).request(\'disconnect_all\', {})"')],
  ['D10', 'DENY', 'redis-cli ACL SETUSER 给 ' + OPCMD + ' 写权限',
    bash('redis-cli ACL SETUSER trade-dev %W~' + OPCMD + ':dev +xadd')],
  ['D10', 'DENY', 'curl POST monitor/control', bash('curl -X POST http://x/api/monitor/control/arm')],
  ['D10', 'DENY', 'rm daemon-scale-zero', bash('rm k8s/overlays/stg/daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'Edit daemon-observe-safe', tool('Edit', { file_path: '/x/k8s/overlays/prod/daemon-observe-safe.patch.yaml' })],
  ['D10', 'DENY', 'MCP scale_deployment daemon=2', tool('mcp__bifrost-platform__scale_deployment', { namespace: 'bifrost-stg', name: 'daemon', replicas: 2 })],

  // TD-96：curl 之外的 HTTP 写法、kubectl patch 扩容、原地改写 guard 文件
  ['D10', 'DENY', 'python requests.post …/control/arm',
    bash('python3 -c "import requests; requests.post(\'https://trader.bifrost.lan' + '/api/monitor/' + 'control/arm' + '\')"')],
  ['D10', 'DENY', 'python heredoc httpx.put …/control/arm',
    bash("python3 - <<'EOF'\nimport httpx\nhttpx.put('http://127.0.0.1:8765" + '/api/monitor/' + 'control/arm' + "')\nEOF")],
  ['D10', 'DENY', 'python session.post …/control/arm',
    bash('python3 -c "s = requests.Session(); s.post(\'http://x' + '/api/monitor/' + 'control/arm' + '\', json={})"')],
  ['D10', 'DENY', 'python urllib data= …/control/arm',
    bash('python3 -c "import urllib.request as u; u.urlopen(u.Request(\'http://x' + '/api/monitor/' + 'control/arm' + '\', data=b\'{}\'))"')],
  ['D10', 'DENY', 'wget --post-data …/control/arm', bash('wget -qO- --post-data "{}" http://x' + '/api/monitor/' + 'control/arm')],
  ['D10', 'DENY', 'wget --method=POST …/control/arm', bash('wget --method=POST http://x' + '/api/monitor/' + 'control/arm')],
  ['D10', 'DENY', 'httpie http POST …/control/arm', bash('http POST http://x' + '/api/monitor/' + 'control/arm')],
  ['D10', 'DENY', 'node fetch method POST …/control/arm',
    bash('node -e "fetch(\'http://x' + '/api/monitor/' + 'control/arm' + '\', {method: \'POST\'})"')],
  ['D10', 'DENY', 'curl --request PATCH …/control/arm', bash('curl --request PATCH http://x' + '/api/monitor/' + 'control/arm')],
  ['D10', 'DENY', 'kubectl patch daemon replicas 1',
    bash('kubectl -n bifrost-stg patch deploy/daemon -p \'{"spec":{"replicas":1}}\'')],
  ['D10', 'DENY', 'kubectl patch daemon --type merge replicas 2',
    bash('kubectl -n bifrost-prod patch deployment daemon --type merge -p \'{"spec": {"replicas": 2}}\'')],
  ['D10', 'DENY', 'sed -i guard (stg)', bash("sed -i '' 's/replicas: 0/replicas: 1/' " + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'sed -Ei guard (prod)', bash("sed -Ei 's/x/y/' " + 'k8s/overlays/prod/' + 'daemon-observe-safe.patch.yaml')],
  ['D10', 'DENY', 'perl -pi guard', bash("perl -pi -e 's/0/1/' " + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', '> 重定向覆盖 guard', bash('echo "" > ' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'cp 覆盖 guard', bash('cp /tmp/empty.yaml ' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'tee 覆盖 guard', bash('echo x | tee ' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'python requests.delete …/control/arm',
    bash('python3 -c "import requests; requests.delete(\'http://x' + '/api/monitor/' + 'control/arm' + '\')"')],
  ['D10', 'DENY', 'python httpx.delete …/control/arm',
    bash('python3 -c "import httpx; httpx.delete(\'http://x' + '/api/monitor/' + 'control/arm' + '\')"')],
  ['D10', 'DENY', 'kubectl apply guard file',
    bash('kubectl apply -f ' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'kubectl patch guard file',
    bash('kubectl patch -f ' + 'k8s/overlays/prod/' + 'daemon-observe-safe.patch.yaml' + ' --type merge -p \'{"spec":{"replicas":1}}\'')],
  ['D10', 'DENY', 'kubectl edit guard file',
    bash('kubectl edit -f ' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'git rm guard', bash('git rm ' + 'k8s/overlays/prod/' + 'daemon-observe-safe.patch.yaml')],
  ['D10', 'DENY', 'python open(guard, w)',
    bash('python3 -c "open(\'' + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml' + '\', \'w\').write(\'\')"')],
  // ── dev-services 应拦截 ──
  ['dev', 'DENY', 'python run_platform.py', bash('python scripts/run_platform.py')],
  ['dev', 'DENY', PK + ' -f ' + SVC_API, bash(PK + ' -f ' + SVC_API)],
  ['dev', 'DENY', K + ' $(pgrep ' + SVC_CON + ')', bash(K + ' $(pgrep -f ' + SVC_CON + ')')],
  ['dev', 'DENY', '裸 port-forward 9090', bash('kubectl port-forward -n monitoring svc/prom 9090:9090')],

  // ── 合法操作不得误拦 ──
  // TD-96：同类只读写法不得误拦
  ['ok', 'ALLOW', 'python requests.get …/control/status',
    bash('python3 -c "import requests; print(requests.get(\'http://x/api/monitor/' + 'control/status\').text)"')],
  ['ok', 'ALLOW', 'wget GET …/control/status', bash('wget -qO- http://x/api/monitor/' + 'control/status')],
  ['ok', 'ALLOW', 'http GET …/control/status', bash('http GET http://x/api/monitor/' + 'control/status')],
  ['ok', 'ALLOW', 'kubectl patch daemon replicas 0',
    bash('kubectl -n bifrost-stg patch deploy/daemon -p \'{"spec":{"replicas":0}}\'')],
  ['ok', 'ALLOW', 'kubectl get daemon replicas', bash("kubectl -n bifrost-stg get deploy/daemon -o jsonpath='{.spec.replicas}'")],
  ['ok', 'ALLOW', 'sed -n 读 guard', bash("sed -n '1,20p' " + 'k8s/overlays/stg/' + 'daemon-scale-zero.patch.yaml')],
  ['ok', 'ALLOW', 'git log guard', bash('git log --oneline -- ' + 'k8s/overlays/prod/' + 'daemon-observe-safe.patch.yaml')],
  ['ok', 'ALLOW', 'requests.post 到别的路径', bash('python3 -c "import requests; requests.post(\'http://x/api/research/drafts\')"')],
  ['ok', 'ALLOW', 'scale trade-api --replicas=2', bash('kubectl scale deploy/trade-api -n bifrost-stg --replicas=2')],
  ['ok', 'ALLOW', 'scale daemon --replicas=0', bash('kubectl scale deploy/daemon -n bifrost-stg --replicas=0')],
  ['ok', 'ALLOW', 'XLEN ' + OPCMD + '（只读）', bash('redis-cli XLEN ' + OPCMD)],
  // TD-21：改源码、读代码、写 ACL 文件 —— 文本里有流名和写命令字样，但没有在写流
  ['ok', 'ALLOW', 'redis-cli XINFO STREAM（只读）', bash('redis-cli XINFO STREAM ' + OPCMD + ':dev')],
  ['ok', 'ALLOW', 'python heredoc 改源码（注释含 XADD / set）',
    bash("python3 - <<'EOF'\nfrom pathlib import Path\np = Path('redis_keys.py')\ns = p.read_text()\n" +
      "s = s.replace('X = 1\\n', '# env users may XADD only to their own stream; set per env\\nCMD = \"" + OPCMD + "\"\\n')\n" +
      "p.write_text(s)\nEOF")],
  ['ok', 'ALLOW', 'heredoc 写 ACL 文件（%W~' + OPCMD + ':dev +xadd）',
    bash("cat > acl.conf.example <<'EOF'\nuser trade-dev on >P %R~ib:tick:* %W~" + OPCMD + ':dev +@read +xadd +sadd +hset\nEOF')],
  ['ok', 'ALLOW', 'grep 流名与 xadd', bash('grep -rnE "' + OPCMD + '|xadd" src | grep -i set')],
  ['ok', 'ALLOW', 'grep 正则转义的 \\.xadd\\(', bash('grep -rnE "\\.xadd\\(" src && grep -rn "' + OPCMD + '" src')],
  ['ok', 'ALLOW', 'git log --grep 流名', bash('git log --oneline --grep "' + OPCMD + '" -- src')],
  ['ok', 'ALLOW', 'pytest（测试源码里有流名）', bash('pytest -q tests/test_operator_streams.py -k ' + OPCMD.split(':')[1])],
  ['ok', 'ALLOW', 'GET monitor/control（只读）', bash('curl -s http://x/api/monitor/control/status')],
  ['ok', 'ALLOW', 'cat run_platform.py', bash('cat scripts/run_platform.py')],
  ['ok', 'ALLOW', 'grep daemon-scale-zero', bash('grep -n replicas k8s/overlays/stg/daemon-scale-zero.patch.yaml')],
  ['ok', 'ALLOW', 'bdev restart platform', bash('bdev restart platform')],
  ['ok', 'ALLOW', 'run_prometheus_pf.sh', bash('./scripts/run_prometheus_pf.sh')],
  ['ok', 'ALLOW', '普通 Edit', tool('Edit', { file_path: '/x/src/app.ts' })],
  ['ok', 'ALLOW', K + ' 无关 PID', bash(K + ' -9 12345')],
  ['ok', 'ALLOW', 'JS 里的 p.' + K + '() + 平台路径',
    bash('node -e "setTimeout(()=>{p.' + K + '()},100)" /x/stocks/bifrost-platform/mcp/platform/src/index.ts')],
  ['ok', 'ALLOW', '写文件（内容含 ' + PK + ' ' + SVC_API + '）',
    bash("cat > /tmp/t.sh <<'EOF'\n" + PK + ' -f ' + SVC_API + '\nEOF')],
  ['ok', 'ALLOW', 'grep ' + K + ' 日志（只读）', bash('grep -rn ' + K + ' ' + SVC_API + '.log')],

  // ── 审批旁路（ADR §5）──
  ['appr', 'DENY', 'curl POST ' + APPROVE_URL,
    bash('curl -sS -X POST http://192.168.10.100:30876' + APPROVE_URL + ' -H "content-type: application/json" -d \'{"channel":"chat"}\'')],
  ['appr', 'DENY', 'cat ' + TOKEN_FILE, bash('cat ~/.config/bifrost/' + TOKEN_FILE)],
  ['appr', 'ALLOW', 'mcp__bifrost-approve__approve_request',
    tool('mcp__bifrost-approve__' + 'approve_request', { id: 'req-1' })],
  ['appr', 'DENY', 'wget ' + REJECT_URL, bash('wget -qO- http://192.168.10.100:30876' + REJECT_URL)],
  ['appr', 'DENY', 'printenv ' + ADMIN_KEY, bash('printenv ' + ADMIN_KEY)],
  ['appr', 'DENY', 'Read ' + TOKEN_FILE, tool('Read', { file_path: '/Users/x/.config/bifrost/' + TOKEN_FILE })],
  ['appr', 'DENY', 'browser open ' + HASH_PAGE,
    tool('browser_navigate', { url: 'http://192.168.10.100:30880/' + HASH_PAGE })],
  ['appr', 'DENY', 'browser click approvals',
    tool('browser_click', { element: 'Approve', url: 'http://ops.example/' + HASH_PAGE })],
  ['appr', 'ALLOW', 'Edit 文档正文可以提到令牌文件名',
    tool('Edit', {
      file_path: '/x/agent-config/.mcp.json.README.md',
      old_string: 'x',
      new_string: 'see ~/.config/bifrost/' + TOKEN_FILE + ' and ' + ADMIN_KEY,
    })],
  ['appr', 'ALLOW', 'GET /api/v1/approvals（列表，不是 approve）',
    bash('curl -sS http://192.168.10.100:30876/api/v1/' + 'approvals')],
  ['appr', 'ALLOW', '其他 MCP 写工具',
    tool('mcp__bifrost-platform__start_pipeline_run', { name: 'ci-example' })],

  // ── Owner 凭证（LANE-W33D）。Cursor 与 Claude 共用这一份闸门。──
  ['own', 'DENY', 'cat Owner 目录', bash('cat ~/' + OWNER_DIR + '/' + OWNER_ENV)],
  ['own', 'DENY', 'Read Owner 目录', tool('Read', { file_path: '/Users/x/' + OWNER_DIR + '/' + OWNER_ENV })],
  ['own', 'DENY', 'Grep owner env', tool('Grep', { pattern: OWNER_ENV, path: 'src' })],
  ['own', 'DENY', 'Glob owner env', tool('Glob', { glob_pattern: '**/*' + OWNER_ENV + '*' })],
  ['own', 'DENY', 'KUBECONFIG=~ 指向别的文件', bash('KUBECONFIG=~/.kube/admin.yaml kubectl get pods')],
  ['own', 'DENY', 'KUBECONFIG=$HOME 指向别的文件', bash('KUBECONFIG=$HOME/.kube/admin.yaml kubectl get pods')],
  ['own', 'DENY', 'KUBECONFIG=${HOME} 指向别的文件', bash('KUBECONFIG=${HOME}/.kube/admin.yaml kubectl get pods')],
  ['own', 'DENY', 'KUBECONFIG 绝对路径指向别的文件', bash('KUBECONFIG=/Users/x/.kube/admin.yaml kubectl get pods')],
  ['own', 'DENY', '--kubeconfig 指向别的文件', bash('kubectl --kubeconfig ~/.kube/admin.yaml get pods')],
  ['own', 'DENY', '--kubeconfig= Owner 目录', bash('kubectl --kubeconfig=/Users/x/' + OWNER_DIR + '/kube/admin.yaml get pods')],
  ['own', 'ALLOW', 'KUBECONFIG=~ 只读 kubeconfig', bash('KUBECONFIG=~/' + KUBE_OK + ' kubectl get pods')],
  ['own', 'ALLOW', 'KUBECONFIG=$HOME 只读 kubeconfig', bash('KUBECONFIG=$HOME/' + KUBE_OK + ' kubectl get pods')],
  ['own', 'ALLOW', 'KUBECONFIG=${HOME} 只读 kubeconfig', bash('KUBECONFIG=${HOME}/' + KUBE_OK + ' kubectl get pods')],
  ['own', 'ALLOW', 'KUBECONFIG 绝对路径只读 kubeconfig', bash('KUBECONFIG=/Users/x/' + KUBE_OK + ' kubectl get pods')],
  ['own', 'ALLOW', '未设置 KUBECONFIG 的 kubectl get pods', bash('kubectl get pods')],
  ['own', 'DENY', 'Agent 运行 Owner 脚本 move-owner-secrets', bash('bash scripts/owner/move-owner-secrets.sh')],
  ['own', 'DENY', 'Agent 运行 Owner 脚本 make-agent-kubeconfig', bash('bash scripts/owner/make-agent-kubeconfig.sh /tmp/x')],
  ['own', 'DENY', 'Agent 运行 Owner 脚本 owner-run', bash('bash scripts/owner/owner-run.sh appr_x')],
  ['own', 'DENY', 'Agent 运行 Secret 物化', bash('python3 scripts/materialize_k8s_trade_secrets.py --env prod')],
  ['own', 'DENY', 'Agent 运行 redis-ib ACL 渲染', bash('scripts/render-redis-ib-acl.sh > /tmp/acl')],
  ['own', 'DENY', 'Agent 运行 redis-ib 用户脚本', bash('bash scripts/redis-ib-env-users.sh status')],
  ['own', 'DENY', 'Agent 运行 UniFi 脚本', bash('python3 scripts/unifi_firewall_setup.py --dry-run')],
  ['own', 'DENY', 'Agent 运行属主密码轮换', bash('bash scripts/bifrost-password-rotate.sh --check')],
  ['own', 'ALLOW', 'Owner 脚本的测试照常运行', bash('bash scripts/owner/move-owner-secrets_test.sh')],
  ['own', 'ALLOW', 'owner-run 的测试照常运行', bash('bash scripts/owner/owner-run_test.sh')],
  ['own', 'ALLOW', 'UniFi 凭证读取的测试照常运行', bash('python3 scripts/unifi_owner_env_test.py')],
  ['own', 'ALLOW', 'Edit 文档正文可以提到 Owner 目录',
    tool('Edit', { file_path: '/x/docs/note.md', old_string: 'x', new_string: 'see ~/' + OWNER_DIR + '/' + OWNER_ENV })],

  // ── 畸形输入 ──
  ['edge', 'ALLOW', '空输入', null],
]

let pass = 0, fail = 0
let group = ''
for (const [g, want, name, payload] of cases) {
  if (g !== group) { group = g; console.log(`\n── ${{ D10: 'D10 交易执行冻结', dev: 'dev-services', ok: '合法操作（不得误拦）', appr: '审批旁路（ADR §5）', own: 'Owner 凭证（LANE-W33D）', edge: '边界输入' }[g]} ──`) }
  const r = spawnSync('node', [GUARD], { input: payload ? JSON.stringify(payload) : '', encoding: 'utf8' })
  const got = (r.stdout || '').trim() ? 'DENY' : 'ALLOW'
  let ok = got === want
  if (ok && g === 'appr' && want === 'DENY' && !String(r.stdout).includes('ADR §5')) {
    ok = false
  }
  if (ok && g === 'own' && want === 'DENY' && !String(r.stdout).includes('这是 Owner 的凭证，写操作走平台动作或 owner_run_command')) {
    ok = false
  }
  ok ? pass++ : fail++
  console.log(`  ${ok ? '✓' : '✗'} ${got.padEnd(5)} ${name}${ok ? '' : `   ← 期望 ${want}`}`)
}
console.log(`\n${fail === 0 ? '✓' : '✗'} ${pass} 通过 / ${fail} 失败（共 ${pass + fail}）`)
process.exit(fail === 0 ? 0 : 1)
