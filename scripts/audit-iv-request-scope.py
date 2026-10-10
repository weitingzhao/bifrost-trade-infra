#!/usr/bin/env python3
"""Read-only bounded request candidate inventory; never enqueue or call vendor.

Catalogue membership does not prove the contract was listed on a historical day.
The resulting manifest is conditional until a point-in-time vendor reference check.
"""

import argparse
import collections
import csv
import datetime as dt
import json
import sys
from pathlib import Path


def merged_requests(plans):
    merged = collections.defaultdict(set)
    for requests in plans.values():
        for key, days in requests.items():
            merged[key].update(days)
    return merged


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-src", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, a.research_src)
    import psycopg2
    from bifrost_research.engines.volatility.iv_solver import as_traded_close

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

    def query(sql, args=()):
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    metrics = list(csv.DictReader((a.evidence / "symbol-session.csv").open()))
    priority = json.loads((a.evidence / "summary.json").read_text())["priority"]
    names = sorted({r["symbol"] for r in metrics})
    spots = {
        (s, d): v
        for s, d, v in query(
            f"SELECT s.symbol,s.bar_date,{as_traded_close('s')} FROM raw_market.stock_daily s WHERE s.symbol=ANY(%s) AND s.bar_date BETWEEN %s AND %s",
            (names, "2025-10-09", "2026-10-09"),
        )
    }
    catalog = collections.defaultdict(lambda: collections.defaultdict(list))
    for s, t, e, k, right in query(
        "SELECT underlying,option_ticker,expiry,strike,option_right FROM raw_market.option_contract WHERE underlying=ANY(%s) AND expiry BETWEEN %s AND %s AND substr(option_ticker,3,length(option_ticker)-17) !~ '[0-9]$' AND (shares_per_contract=100 OR shares_per_contract IS NULL)",
        (names, "2025-12-08", "2027-05-17"),
    ):
        catalog[s][e].append((t, k, right))
    held = set()
    # Chunked partition-pruned reads; only selected historical scope is retained.
    lo = dt.date(2025, 10, 9)
    while lo <= dt.date(2026, 10, 9):
        hi = (
            lo.replace(year=lo.year + 1, month=1, day=1)
            if lo.month == 12
            else lo.replace(month=lo.month + 1, day=1)
        )
        syms = (
            names
            if lo <= dt.date(2026, 9, 25) and hi > dt.date(2026, 7, 6)
            else priority
        )
        for ticker, d in query(
            "SELECT option_ticker,bar_date FROM raw_market.option_daily WHERE underlying=ANY(%s) AND bar_date >= %s AND bar_date < %s AND expiry-bar_date BETWEEN 50 AND 220",
            (syms, lo, hi),
        ):
            held.add((ticker, d))
        lo = hi
    plans = collections.defaultdict(lambda: collections.defaultdict(set))
    reasons = collections.Counter()
    aims = collections.Counter()
    for r in metrics:
        s, d = r["symbol"], dt.date.fromisoformat(r["session"])
        tasks = []
        if dt.date(2026, 7, 6) <= d <= dt.date(2026, 9, 25) and (
            r["term_local"] == "0" or r["cone60_local"] == "0"
        ):
            tasks.append(("td172", 60, 100))
        if s in priority:
            if r["cone90_local"] == "0":
                tasks.append(("td142", 90, 120))
            if r["cone180_local"] == "0":
                tasks.append(("td142", 180, 220))
        spot = spots.get((s, d))
        for cohort, lo, hi in tasks:
            aims[cohort + "_tenor_days"] += 1
            exps = sorted(
                (e for e in catalog[s] if lo <= (e - d).days <= hi),
                key=lambda e: ((e - d).days - lo, e),
            )
            if not exps or not spot:
                reasons[cohort + "_no_local_catalogue_or_spot"] += 1
                continue
            # Take the first expiry with two calls and two puts inside the actual ATM band.
            chosen = None
            for e in exps:
                picks = []
                for right in ("C", "P"):
                    side = sorted(
                        (
                            v
                            for v in catalog[s][e]
                            if v[2] == right and 0.9 * spot <= v[1] <= 1.1 * spot
                        ),
                        key=lambda v: (abs(v[1] - spot), v[0]),
                    )[:2]
                    picks.extend(side)
                if len(picks) == 4:
                    chosen = (e, picks)
                    break
            if chosen is None:
                reasons[cohort + "_no_catalogue_atm_two_sides"] += 1
                continue
            for ticker, k, right in chosen[1]:
                if (ticker, d) in held:
                    reasons[cohort + "_selected_contract_day_already_has_bar"] += 1
                    continue
                plans[cohort][(s, ticker, chosen[0])].add(d)
    summary = {
        "conditional": True,
        "aims": dict(aims),
        "reasons": dict(reasons),
        "cohorts": {},
    }
    for cohort, requests in plans.items():
        result = []
        for (s, t, e), dates in sorted(requests.items()):
            result.append(
                {
                    "symbol": s,
                    "option_ticker": t,
                    "expiry": str(e),
                    "start": str(min(dates)),
                    "end": str(max(dates)),
                    "missing_target_sessions": len(dates),
                    "target_sessions": ",".join(str(d) for d in sorted(dates)),
                }
            )
        with (a.evidence / f"{cohort}-request-candidates.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(result[0]))
            writer.writeheader()
            writer.writerows(result)
        summary["cohorts"][cohort] = {
            "contracts": len(result),
            "target_contract_days": sum(r["missing_target_sessions"] for r in result),
            "symbols": len({r["symbol"] for r in result}),
            "request_ranges": len(result),
            "min_date": min(r["start"] for r in result),
            "max_date": max(r["end"] for r in result),
            "by_symbol": dict(collections.Counter(r["symbol"] for r in result)),
        }
    merged = merged_requests(plans)
    summary["joint"] = {
        "contracts": len(merged),
        "target_contract_days": sum(len(ds) for ds in merged.values()),
    }
    with (a.evidence / "joint-request-candidates.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["symbol", "option_ticker", "expiry", "start", "end", "target_sessions"]
        )
        for (s, t, e), ds in sorted(merged.items()):
            writer.writerow(
                [s, t, e, min(ds), max(ds), ",".join(str(d) for d in sorted(ds))]
            )
    (a.evidence / "request-summary.json").write_text(json.dumps(summary, indent=2))
    print(
        json.dumps(
            {
                **summary,
                "cohorts": {
                    k: {x: v for x, v in r.items() if x != "by_symbol"}
                    for k, r in summary["cohorts"].items()
                },
            },
            indent=2,
        )
    )
    conn.close()


if __name__ == "__main__":
    main()
