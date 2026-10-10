#!/usr/bin/env node
/* codex-pretooluse.js 回归测试：载荷形状取自 2026-10-10 实测的 Codex 0.162 PreToolUse。 */
'use strict'
const { spawnSync } = require('node:child_process')
const ADAPTER = require('node:path').join(__dirname, 'codex-pretooluse.js')

const base = { session_id: 's', turn_id: 't', cwd: '/tmp', hook_event_name: 'PreToolUse', model: 'm' }
const bash = c => ({ ...base, tool_name: 'Bash', tool_input: { command: c } })
const patch = body => ({ ...base, tool_name: 'apply_patch', tool_input: { command: '*** Begin Patch\n' + body + '*** End Patch' } })

// 用拼接构造敏感字符串，避免本文件自身触发任何静态扫描
const ADD_ALL = 'git add ' + '-A'
const GUARD_FILE = '/x/bifrost-trade-infra/k8s/overlays/prod/daemon-' + 'observe-safe.patch.yaml'

const cases = [
  ['ALLOW', 'Bash git status', bash('git status --short')],
  ['DENY', 'Bash ' + ADD_ALL, bash(ADD_ALL)],
  ['DENY', 'Bash git commit -am', bash('git commit -am wip')],
  ['ALLOW', 'apply_patch 新建文档，正文写了 ' + ADD_ALL,
    patch('*** Add File: /tmp/notes.md\n+Do not run ' + ADD_ALL + ' here.\n')],
  ['DENY', 'apply_patch 改 D10 guard 文件',
    patch('*** Update File: ' + GUARD_FILE + '\n@@\n-replicas: 0\n+replicas: 1\n')],
  ['DENY', 'apply_patch 把别的文件挪成 D10 guard 文件',
    patch('*** Update File: /tmp/a.yaml\n*** Move to: ' + GUARD_FILE + '\n@@\n-a\n+b\n')],
  ['DENY', 'apply_patch 多个文件里有一个是 guard 文件',
    patch('*** Add File: /tmp/ok.md\n+ok\n*** Delete File: ' + GUARD_FILE + '\n')],
  ['DENY', 'apply_patch 解析不出文件头时按原文判',
    { ...base, tool_name: 'apply_patch', tool_input: { command: ADD_ALL } }],
  ['DENY', 'MCP scale_deployment daemon=2',
    { ...base, tool_name: 'mcp__bifrost-platform__scale_deployment', tool_input: { name: 'daemon', replicas: 2 } }],
]

let pass = 0
let fail = 0
for (const [want, name, payload] of cases) {
  const r = spawnSync(process.execPath, [ADAPTER], { input: JSON.stringify(payload), encoding: 'utf8' })
  let got = 'ALLOW'
  if (r.status !== 0) got = 'ERROR'
  else if (r.stdout.trim()) {
    const out = JSON.parse(r.stdout)
    if (out.hookSpecificOutput && out.hookSpecificOutput.permissionDecision === 'deny') got = 'DENY'
  }
  if (got === want) pass++
  else {
    fail++
    console.log(`✗ ${name}: want ${want}, got ${got}\n  ${r.stdout}${r.stderr}`)
  }
}
console.log(`\n${fail ? '✗' : '✓'} ${pass} 通过 / ${fail} 失败（共 ${cases.length}）`)
process.exit(fail ? 1 : 0)
