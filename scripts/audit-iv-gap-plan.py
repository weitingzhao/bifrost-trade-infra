#!/usr/bin/env python3
"""Bounded, read-only TD-172/142 inventory. Private evidence, no DB writer calls.

Run with the Research environment and --research-src pointing at reviewed source.
The current universe is a retrospective population, not a historical roster.
"""

import argparse
import calendar
import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path


def chunks(start, end):
    while start <= end:
        stop = min(
            end, start.replace(day=calendar.monthrange(start.year, start.month)[1])
        )
        yield start, stop
        start = stop + dt.timedelta(days=1)


def inventory_grid(names, priority, days, gap_start, gap_end):
    grid = {(s, d) for s in names for d in days if gap_start <= d <= gap_end}
    grid.update((s, d) for s in priority for d in days)
    return grid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-src", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--snapshot-input", type=Path)
    a = p.parse_args()
    sys.path.insert(0, a.research_src)
    import psycopg2
    from bifrost_research.engines.pine.context import term_30_60
    from bifrost_research.engines.volatility.atm_iv import (
        atm_iv_from_side_items,
        build_expiry_side_items,
        representative_spot,
    )
    from bifrost_research.engines.volatility.iv_solver import (
        _mid_from_ohlc,
        as_traded_close,
    )
    from bifrost_research.pricing import load_rate_curve, solve_iv
    from bifrost_research.repositories.iv_cone import tenor_iv

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
    a.output.mkdir(parents=True, exist_ok=True)

    def query(sql, args=()):
        if args and isinstance(args[-1], list) and len(args[-1]) > 64:
            result = []
            for offset in range(0, len(args[-1]), 64):
                result.extend(query(sql, (*args[:-1], args[-1][offset : offset + 64])))
            return result
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    end = dt.date(2026, 10, 9)
    days = [
        r[0]
        for r in query(
            "SELECT trade_date FROM dw_stock.dim_trading_calendar WHERE is_trading_day AND trade_date<=%s ORDER BY trade_date DESC LIMIT 252",
            (end,),
        )
    ][::-1]
    start = days[0]
    universe = query(
        "SELECT symbol,tier,entered_on FROM research.option_universe ORDER BY symbol"
    )
    names = [r[0] for r in universe]
    residents = [r[0] for r in universe if r[1] == "resident"]
    # AAPL is included as the debt's pre-existing acceptance control.
    priority = sorted(set(residents + ["AAPL"]))
    td172_start, td172_end = dt.date(2026, 7, 6), dt.date(2026, 9, 25)
    scope = lambda s, d: s in priority or td172_start <= d <= td172_end
    spots = {}
    for lo, hi in chunks(start, end):
        syms = names if lo <= td172_end and hi >= td172_start else priority
        for s, d, spot in query(
            f"SELECT s.symbol,s.bar_date,{as_traded_close('s')} FROM raw_market.stock_daily s WHERE s.bar_date BETWEEN %s AND %s AND s.symbol=ANY(%s)",
            (lo, hi, syms),
        ):
            if d in days and scope(s, d) and spot and 0 < spot < float("inf"):
                spots[s, d] = spot
    existing = collections.defaultdict(dict)
    for lo, hi in chunks(start, end):
        syms = names if lo <= td172_end and hi >= td172_start else priority
        for s, d, e, iv in query(
            "SELECT symbol,trade_date,expiry,atm_iv FROM features.option_metric_atm_iv_daily WHERE trade_date BETWEEN %s AND %s AND symbol=ANY(%s) AND atm_iv>0 AND atm_iv<10",
            (lo, hi, syms),
        ):
            if scope(s, d):
                existing[s, d][e] = iv
    sources = collections.defaultdict(list)
    raw = collections.defaultdict(list)
    failures = collections.Counter()
    rates = load_rate_curve(conn, start, end)
    for lo, hi in chunks(start, end):
        syms = names if lo <= td172_end and hi >= td172_start else priority
        for s, d, e, ticker, strike, right, iv, spot, status in query(
            "SELECT symbol,trade_date,expiry,option_ticker,strike,option_right,iv,spot,solver_status FROM features.option_iv_reconstructed_daily WHERE trade_date BETWEEN %s AND %s AND symbol=ANY(%s) AND expiry-trade_date BETWEEN 50 AND 220 AND iv>0 AND iv<10 AND spot>0 AND spot<'Infinity'::float8 AND substr(option_ticker,3,length(option_ticker)-17) !~ '[0-9]$'",
            (lo, hi, syms),
        ):
            if scope(s, d):
                sources[s, d, e].append(
                    {
                        "option_ticker": ticker,
                        "strike": strike,
                        "option_right": right,
                        "iv": iv,
                        "underlying_price": spot,
                        "solver_status": status,
                    }
                )
        # Explicit stock bounds prune both sides; exact as-traded spot is reused locally.
        rows = query(
            "SELECT underlying,bar_date,expiry,option_ticker,strike,option_right,close,high,low,volume FROM raw_market.option_daily WHERE bar_date BETWEEN %s AND %s AND underlying=ANY(%s) AND expiry-bar_date BETWEEN 50 AND 220 AND substr(option_ticker,3,length(option_ticker)-17) !~ '[0-9]$'",
            (lo, hi, syms),
        )
        for s, d, e, ticker, strike, right, close, high, low, volume in rows:
            spot = spots.get((s, d))
            if not scope(s, d) or not spot or not 0.9 * spot <= strike <= 1.1 * spot:
                continue
            raw[s, d, e].append((ticker, strike, right, close, high, low, volume, spot))
        print(f"read {lo}..{hi}: {len(rows)} raw bars", flush=True)
    if a.snapshot_input:
        for r in json.loads(a.snapshot_input.read_text()):
            s, d, e = (
                r["symbol"],
                dt.date.fromisoformat(r["session"]),
                dt.date.fromisoformat(r["expiry"]),
            )
            if s not in names or not scope(s, d):
                continue
            key = s, d, e
            sources[key] = [
                v for v in sources[key] if v["option_ticker"] != r["option_ticker"]
            ]
            sources[key].append(r)
    recomputed = collections.defaultdict(dict)
    inputs = collections.Counter()
    for key in sorted(set(sources) | set(raw)):
        s, d, e = key
        rows = list(sources[key])
        held = {r["option_ticker"] for r in rows}
        for ticker, strike, right, close, high, low, volume, spot in raw[key]:
            if ticker in held:
                continue
            mid = _mid_from_ohlc(close, high, low)
            if mid is None:
                failures["no_positive_price"] += 1
                continue
            iv, status = solve_iv(
                spot, strike, (e - d).days / 365, mid, right, rate=rates.on_or_before(d)
            )
            if iv is None:
                failures[status] += 1
                continue
            rows.append(
                {
                    "option_ticker": ticker,
                    "strike": strike,
                    "option_right": right,
                    "iv": iv,
                    "underlying_price": spot,
                    "solver_status": "ok",
                }
            )
        spot = representative_spot(rows)
        if not spot:
            continue
        items = build_expiry_side_items(rows, spot, max_moneyness=0.10, min_iv=0.05)
        vendor = any(r.get("solver_status") == "vendor_snapshot" for r in rows)
        if len(items) < 2 or (
            not vendor
            and not (
                any(i[1] is not None for i in items)
                and any(i[2] is not None for i in items)
            )
        ):
            failures["insufficient_near_atm_pair_expiry"] += 1
            continue
        iv, _, _, _ = atm_iv_from_side_items(items)
        if iv is not None:
            recomputed[s, d][e] = iv
            inputs["vendor_expiry" if vendor else "brent_expiry"] += 1

    metrics = []
    missing_rows = []
    grid = inventory_grid(names, priority, days, td172_start, td172_end)
    for s, d in sorted(grid):
        old = existing[s, d]
        new = dict(old)
        new.update(recomputed[s, d])
        flags = {}
        for label, test in [
            (
                "front30",
                lambda pairs, day=d: any(7 <= (e - day).days <= 90 for e, _ in pairs),
            ),
            (
                "front60",
                lambda pairs, day=d: any(7 <= (e - day).days <= 60 for e, _ in pairs),
            ),
            (
                "breadth50_100",
                lambda pairs, day=d: any(50 <= (e - day).days <= 100 for e, _ in pairs),
            ),
            ("term", lambda pairs, day=d: term_30_60(day, pairs) is not None),
            ("cone60", lambda pairs, day=d: tenor_iv(day, pairs, 60) is not None),
            ("cone90", lambda pairs, day=d: tenor_iv(day, pairs, 90) is not None),
            ("cone180", lambda pairs, day=d: tenor_iv(day, pairs, 180) is not None),
        ]:
            flags[label + "_old"] = int(test(list(old.items())))
            flags[label + "_local"] = int(test(list(new.items())))
        added = [e for e in recomputed[s, d] if e not in old]
        metrics.append(
            dict(
                symbol=s,
                session=d.isoformat(),
                stock_spot_missing=int((s, d) not in spots),
                **flags,
                added_expiry_rows=len(added),
                local_input_expiries=len(recomputed[s, d]),
            )
        )
        for e in added:
            missing_rows.append((s, d.isoformat(), e.isoformat(), (e - d).days))
    with (a.output / "symbol-session.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    with (a.output / "local-new-expiries.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "session", "expiry", "dte"])
        writer.writerows(missing_rows)
    summary = {
        "as_of": str(end),
        "start": str(start),
        "calendar_sessions": len(days),
        "universe": len(names),
        "priority": priority,
        "input_counts": dict(inputs),
        "failures": dict(failures),
        "cohorts": {},
    }
    for label, select in [
        (
            "td172",
            lambda r: (
                td172_start.isoformat() <= r["session"] <= td172_end.isoformat()
                and r["symbol"] in names
            ),
        ),
        ("td142_priority", lambda r: r["symbol"] in priority),
    ]:
        rs = [r for r in metrics if select(r)]
        totals = {
            k: sum(r[k] for r in rs) for k in rs[0] if k not in ("symbol", "session")
        }
        summary["cohorts"][label] = dict(symbol_days=len(rs), **totals)
        byname = {}
        for s in sorted({r["symbol"] for r in rs}):
            sr = [r for r in rs if r["symbol"] == s]
            byname[s] = dict(
                symbol_days=len(sr), **{k: sum(r[k] for r in sr) for k in totals}
            )
        (a.output / f"{label}-by-symbol.json").write_text(json.dumps(byname, indent=2))
    week = collections.defaultdict(collections.Counter)
    for r in metrics:
        d = dt.date.fromisoformat(r["session"])
        if r["symbol"] in names and td172_start <= d <= td172_end:
            key = str(d - dt.timedelta(days=d.weekday()))
            week[key]["denominator"] += 1
            for k in (
                "breadth50_100_old",
                "breadth50_100_local",
                "term_old",
                "term_local",
                "cone60_old",
                "cone60_local",
            ):
                week[key][k] += r[k]
    summary["weeks"] = dict(week)
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2))
    conn.close()
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
