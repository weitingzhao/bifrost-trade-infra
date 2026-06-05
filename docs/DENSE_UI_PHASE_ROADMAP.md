# Dense UI Phase Roadmap（4.10+）

> 权威完成状态见 `bifrost-trade-frontend/docs/LEGACY_CSS_PAYDOWN.md`。本文件仅协调 **Phase 编号**，避免多 plan 冲突。

| Phase | 页面 | Plan 文件 | 状态 |
|-------|------|-----------|------|
| 4.10 | Win Rate | `win_rate_dense_ui_517a913b.plan.md` | done |
| 4.11 | Structures | `structures_dense_ui_73d4fb8f.plan.md` | done |
| 4.12 | Opportunities | `opportunities_dense_ui_cec8f108.plan.md` | done |
| 4.13 | Gates | `gates_dense_ui_a8f3c2e1.plan.md` | **done** |
| 4.14 | Allocations | `allocations_dense_ui_d4f8a1c3.plan.md` | **done** |
| 4.15 | Option Category | `option_category_dense_ui_f3a9c2e8.plan.md` | **done** |
| 4.16 | API Health | `api_health_dense_ui_e5c2b7a4.plan.md` | **done** |
| 4.17 | API Health Follow-up (business parity) | `api_pages_dense_ui_b7e4f9a2.plan.md` | **done** |
| 4.18 | Socket Services | `socket_dense_ui_b7e4a1f9.plan.md` | **done** |
| 4.19 | Operations Daemon | `daemon_dense_ui_c4a8e1f7.plan.md` | **done** |
| 4.20 | Operations Celery | `celery_dense_ui_b7e4f2a9.plan.md` | **done** |
| 5 | Module CSS shrink | — | **done** |

**4.13–4.16 已于 2026-06-02 并行完成**；全仓 `lint && build && check-legacy-css` 通过。

**4.17–4.20** 已全部完成（2026-06-03）。

**Phase 5（2026-06-03）**：删除空 module.css 文件 2 个，收紧 3 处行数预算，`*.module.css` 文件数 25 → 16。
