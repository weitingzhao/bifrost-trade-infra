#!/usr/bin/env node
/**
 * Claude Code `Stop` hook — 上报本会话的标题给 Commit Lineage（TD-197，见 report-thread-title.js）。
 *
 * 原来还向 POST /api/v1/programs/session-stop 上报会话元数据；平台从未实现这个路由，
 * 2026-11-18 经 Owner 同意删除（通道 X-B7）。
 */
'use strict'

const fs = require('node:fs')
const { reportThreadTitle } = require('./report-thread-title.js')
const { reportOwnerSaid } = require('./report-owner-said.js')

async function main() {
  let payload = {}
  try {
    payload = JSON.parse(fs.readFileSync(0, 'utf8') || '{}')
  } catch {
    payload = {}
  }

  // stop_hook_active = 本次 Stop 是由上一个 Stop hook 触发的续跑，不重复上报。
  if (payload.stop_hook_active === true) return

  // 标题上报（TD-197）：失败一律吞掉。
  try {
    await reportThreadTitle(payload)
  } catch {
    // never block a session
  }
  // Owner 的话上报（LAW-1，report-owner-said.js）：失败一律吞掉。
  try {
    await reportOwnerSaid(payload)
  } catch {
    // never block a session
  }
}

main()
