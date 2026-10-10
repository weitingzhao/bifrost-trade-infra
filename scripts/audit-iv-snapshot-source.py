#!/usr/bin/env python3
"""Read-only check of unprojected observed snapshots; private candidate output."""

import argparse
import collections
import datetime as dt
import json
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-src", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, a.research_src)
    import psycopg2
    from bifrost_research.engines.volatility.atm_iv import (
        fetch_snapshot_iv_rows_for_date,
    )
    from bifrost_research.engines.volatility.iv_solver import degraded_sessions

    conn = psycopg2.connect(
        host="192.168.10.73",
        port=30432,
        user="agent_reader",
        dbname="bifrost_golden_source",
        connect_timeout=10,
        keepalives_idle=10,
        keepalives_interval=5,
        keepalives_count=3,
        options="-c default_transaction_read_only=on -c statement_timeout=20000 -c jit=off",
    )
    conn.set_session(readonly=True, autocommit=True)
    sql = Path(__file__).with_name("audit-iv-unprojected-snapshots.sql").read_text()
    groups = []
    for lo, hi in [("2026-08-05", "2026-09-01"), ("2026-09-01", "2026-09-26")]:
        with conn.cursor() as cur:
            cur.execute(sql, (lo, hi))
            groups.extend(cur.fetchall())
    (a.evidence / "unprojected-snapshot-groups.json").write_text(
        json.dumps(groups, default=str)
    )
    candidates = {(s, d, e) for s, d, e, n in groups}
    names = sorted({r[0] for r in groups})
    degraded = {
        s: degraded_sessions(conn, s, dt.date(2026, 8, 5), dt.date(2026, 9, 25))
        for s in names
    }
    byday = collections.defaultdict(set)
    for s, d, e in candidates:
        byday[d].add(s)
    out = []
    for d, syms in sorted(byday.items()):
        rows = fetch_snapshot_iv_rows_for_date(conn, d, underlyings=sorted(syms))
        for r in rows:
            s, e = r["underlying"], r["expiry"]
            if (s, d, e) not in candidates or d in degraded[s]:
                continue
            iv = float(r["iv"])
            if iv > 3:
                iv /= 100
            spot = float(r["underlying_price"])
            if not (
                0.05 <= iv <= 5
                and 0 < spot < float("inf")
                and 0.9 * spot <= r["strike"] <= 1.1 * spot
            ):
                continue
            out.append(
                {
                    "symbol": s,
                    "session": str(d),
                    "expiry": str(e),
                    "option_ticker": r["option_ticker"],
                    "strike": r["strike"],
                    "option_right": r["option_right"],
                    "iv": iv,
                    "underlying_price": spot,
                    "solver_status": "vendor_snapshot",
                }
            )
        print(d, len(rows), flush=True)
    (a.evidence / "snapshot-source-candidates.json").write_text(json.dumps(out))
    summary = {
        "eligible_contract_days": len(out),
        "eligible_expiry_groups": len(
            {(r["symbol"], r["session"], r["expiry"]) for r in out}
        ),
        "degraded_symbol_days": sum(len(ds) for ds in degraded.values()),
        "by_symbol": dict(collections.Counter(r["symbol"] for r in out)),
    }
    (a.evidence / "snapshot-source-summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(json.dumps(summary, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
