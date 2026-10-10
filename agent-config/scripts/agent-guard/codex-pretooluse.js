#!/usr/bin/env node
/**
 * Codex PreToolUse → preflight.js 的薄适配层。判定全部在 preflight.js，这里不加规则。
 *
 * Codex 的载荷与 Claude 同形（hook_event_name / tool_name / tool_input），shell 调用是
 * tool_name "Bash"、tool_input.command 字符串，原样转给 preflight。
 *
 * 唯一的差别是改文件：Codex 用 apply_patch，tool_input.command 是整段补丁。原样转过去，
 * preflight 会把补丁正文当 shell 命令判（可能误拦），而只认 Edit / Write 的 D10 路径
 * 规则看不到它（2026-10-10 实测：改 daemon-observe-safe 被放行）。所以按补丁头
 * 拆成每个文件一次 Write，和 Claude 的 Edit / Write 一样只看路径。解析不出文件头时
 * 原样转过去（宁可误拦，不放行）。
 *
 * 接线：~/.codex/hooks.json（见 agent-config/codex/README.md）。
 */
'use strict'
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')

const GUARD = path.join(__dirname, 'preflight.js')
const FILE_HEADER = /^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm

function runGuard(input) {
  const r = spawnSync(process.execPath, [GUARD], { input, encoding: 'utf8' })
  return { status: r.status ?? 1, stdout: r.stdout || '', stderr: r.stderr || '' }
}

function patchText(toolInput) {
  if (typeof toolInput === 'string') return toolInput
  if (!toolInput || typeof toolInput !== 'object') return ''
  for (const key of ['command', 'patch', 'input']) {
    if (typeof toolInput[key] === 'string') return toolInput[key]
  }
  return ''
}

function patchFiles(text) {
  const files = []
  for (const m of text.matchAll(FILE_HEADER)) files.push(m[1].trim())
  return [...new Set(files)]
}

function deny(message) {
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: message,
    },
  })
}

function main() {
  let raw = ''
  try {
    raw = fs.readFileSync(0, 'utf8')
  } catch {
    raw = ''
  }

  let payload = null
  try {
    payload = JSON.parse(raw || '{}')
  } catch {
    payload = null
  }

  const files = payload && payload.tool_name === 'apply_patch' ? patchFiles(patchText(payload.tool_input)) : []
  if (files.length === 0) {
    const r = runGuard(raw)
    process.stdout.write(r.stdout)
    process.stderr.write(r.stderr)
    process.exit(r.status)
  }

  for (const file_path of files) {
    const r = runGuard(
      JSON.stringify({ ...payload, tool_name: 'Write', tool_input: { file_path } }),
    )
    if (r.status !== 0 || r.stdout.trim()) {
      process.stdout.write(r.stdout)
      process.stderr.write(r.stderr)
      process.exit(r.status)
    }
  }
  process.exit(0)
}

try {
  main()
} catch (err) {
  process.stdout.write(deny('Codex 适配层出错，按拦截处理：' + String((err && err.message) || err)))
  process.exit(0)
}
