#!/usr/bin/env node
/**
 * Claude Code `Stop` hook — 把会话元数据 POST 给 platform-api。
 *
 * Cursor 与 Claude 的 stop payload 结构不同，本文件是适配层：
 *   Cursor : {agent_id, summary, duration_ms, program_id, phase_id, track, lane, intent}
 *   Claude : {session_id, transcript_path, cwd, hook_event_name:"Stop", stop_hook_active}
 * 两侧最终写入同一个契约 POST /api/v1/programs/session-stop。
 *
 * Env: PLATFORM_API_URL (默认 http://127.0.0.1:8780), PLATFORM_OPERATOR_TOKEN,
 *      BIFROST_PROGRAM_ID, BIFROST_PHASE_ID
 *
 * 注意（2026-08-27 实测）：platform-api **尚未实现** POST /api/v1/programs/session-stop
 * （Go 侧无此路由，返回 405）。Cursor 侧的同名 hook 也一直在静默失败。
 * 本适配层对 404/405 静默跳过 —— 端点上线后自动生效。
 *
 * 对等文件: .cursor/hooks/on-session-stop.js
 */
'use strict'

const fs = require('node:fs')

async function main() {
  let payload = {}
  try {
    payload = JSON.parse(fs.readFileSync(0, 'utf8') || '{}')
  } catch {
    payload = {}
  }

  // stop_hook_active = 本次 Stop 是由上一个 Stop hook 触发的续跑，不重复上报。
  if (payload.stop_hook_active === true) return

  const base = process.env.PLATFORM_API_URL || 'http://127.0.0.1:8780'
  const token = process.env.PLATFORM_OPERATOR_TOKEN || ''

  const body = {
    program_id: process.env.BIFROST_PROGRAM_ID || 'briefing',
    phase_id: process.env.BIFROST_PHASE_ID || '',
    // 服务端字段名沿用 cursor_agent_id，此处填 Claude 的 session_id（同一语义：会话标识）
    cursor_agent_id: payload.session_id || '',
    summary: 'claude session stop',
    track: process.env.BIFROST_TRACK || '',
    lane: process.env.BIFROST_LANE || '',
    intent: process.env.BIFROST_INTENT || '',
    duration_ms: 0,
    source: 'claude-code',
    transcript_path: payload.transcript_path || '',
    cwd: payload.cwd || '',
  }

  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  try {
    const res = await fetch(`${base}/api/v1/programs/session-stop`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    })
    // 404/405 = platform-api 尚未实现该端点（截至 2026-08-27 Go 侧无此路由）。
    // 静默跳过：端点上线后本 hook 自动开始工作，无需改动。
    if (!res.ok && res.status !== 404 && res.status !== 405) {
      process.stderr.write(`[on-session-stop] HTTP ${res.status}: ${await res.text()}\n`)
    }
  } catch (err) {
    // platform-api 没起时属正常，不打断会话
    process.stderr.write(`[on-session-stop] ${err.message}\n`)
  }
}

main()
