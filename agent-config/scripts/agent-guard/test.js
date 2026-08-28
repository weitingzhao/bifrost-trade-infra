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

const cases = [
  // ── D10 应拦截 ──
  ['D10', 'DENY', 'kubectl scale daemon --replicas=1', bash('kubectl scale deploy/daemon -n bifrost-stg --replicas=1')],
  ['D10', 'DENY', 'XADD ' + OPCMD, bash('redis-cli XADD ' + OPCMD + ' MAXLEN 1000 op place_order')],
  ['D10', 'DENY', 'LPUSH ' + OPCMD, bash('redis-cli LPUSH ' + OPCMD + ' payload')],
  ['D10', 'DENY', 'curl POST monitor/control', bash('curl -X POST http://x/api/monitor/control/arm')],
  ['D10', 'DENY', 'rm daemon-scale-zero', bash('rm k8s/overlays/stg/daemon-scale-zero.patch.yaml')],
  ['D10', 'DENY', 'Edit daemon-observe-safe', tool('Edit', { file_path: '/x/k8s/overlays/prod/daemon-observe-safe.patch.yaml' })],
  ['D10', 'DENY', 'MCP scale_deployment daemon=2', tool('mcp__bifrost-platform__scale_deployment', { namespace: 'bifrost-stg', name: 'daemon', replicas: 2 })],

  // ── dev-services 应拦截 ──
  ['dev', 'DENY', 'python run_platform.py', bash('python scripts/run_platform.py')],
  ['dev', 'DENY', PK + ' -f ' + SVC_API, bash(PK + ' -f ' + SVC_API)],
  ['dev', 'DENY', K + ' $(pgrep ' + SVC_CON + ')', bash(K + ' $(pgrep -f ' + SVC_CON + ')')],
  ['dev', 'DENY', '裸 port-forward 9090', bash('kubectl port-forward -n monitoring svc/prom 9090:9090')],

  // ── 合法操作不得误拦 ──
  ['ok', 'ALLOW', 'scale trade-api --replicas=2', bash('kubectl scale deploy/trade-api -n bifrost-stg --replicas=2')],
  ['ok', 'ALLOW', 'scale daemon --replicas=0', bash('kubectl scale deploy/daemon -n bifrost-stg --replicas=0')],
  ['ok', 'ALLOW', 'XLEN ' + OPCMD + '（只读）', bash('redis-cli XLEN ' + OPCMD)],
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

  // ── 畸形输入 ──
  ['edge', 'ALLOW', '空输入', null],
]

let pass = 0, fail = 0
let group = ''
for (const [g, want, name, payload] of cases) {
  if (g !== group) { group = g; console.log(`\n── ${{ D10: 'D10 交易执行冻结', dev: 'dev-services', ok: '合法操作（不得误拦）', edge: '边界输入' }[g]} ──`) }
  const r = spawnSync('node', [GUARD], { input: payload ? JSON.stringify(payload) : '', encoding: 'utf8' })
  const got = (r.stdout || '').trim() ? 'DENY' : 'ALLOW'
  const ok = got === want
  ok ? pass++ : fail++
  console.log(`  ${ok ? '✓' : '✗'} ${got.padEnd(5)} ${name}${ok ? '' : `   ← 期望 ${want}`}`)
}
console.log(`\n${fail === 0 ? '✓' : '✗'} ${pass} 通过 / ${fail} 失败（共 ${pass + fail}）`)
process.exit(fail === 0 ? 0 : 1)
