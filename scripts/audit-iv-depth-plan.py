#!/usr/bin/env python3
"""Offline proposal from frozen private inventory and historical reference GETs.

No network, database, ingest, or writer. A listed contract is not a valid bar.
"""

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path


def historical_pick(row, reference):
    params = reference.get("params", {})
    if (params.get("underlying_ticker"), params.get("as_of")) != (
        row["symbol"],
        row["session"],
    ):
        return "wrong_as_of", None
    if reference.get("http") != 200 or reference.get("status") != "OK":
        return "reference_error", None
    if reference.get("truncated"):
        return "reference_incomplete", None
    day = dt.date.fromisoformat(row["session"])
    if (params.get("expiration_date.gte"), params.get("expiration_date.lte")) != (
        str(day + dt.timedelta(days=180)),
        str(day + dt.timedelta(days=220)),
    ):
        return "wrong_band", None
    spot = row.get("spot")
    if spot is None or not math.isfinite(spot) or spot <= 0:
        return "missing_spot", None
    if (
        params.get("strike_price.gte", math.inf) > 0.9 * spot + 1e-6
        or params.get("strike_price.lte", -math.inf) < 1.1 * spot - 1e-6
    ):
        return "reference_incomplete_strikes", None
    groups = collections.defaultdict(list)
    for contract in reference.get("contracts", []):
        ticker = contract.get("ticker", "")
        if not re.fullmatch(
            r"O:" + re.escape(row["symbol"]) + r"\d{6}[CP]\d{8}", ticker
        ):
            continue
        if contract.get("shares_per_contract") != 100 or contract.get(
            "additional_underlyings"
        ):
            continue
        expiry = contract.get("expiration_date")
        strike = contract.get("strike_price")
        if expiry is None or strike is None or not math.isfinite(strike):
            continue
        dte = (dt.date.fromisoformat(expiry) - day).days
        if 180 <= dte <= 220 and 0.9 * spot <= strike <= 1.1 * spot:
            groups[expiry].append(contract)
    for expiry, contracts in sorted(groups.items()):
        picks = []
        for side in ("call", "put"):
            unique = {
                c["ticker"]: c for c in contracts if c.get("contract_type") == side
            }
            picks += sorted(
                unique.values(),
                key=lambda c: (abs(c["strike_price"] - spot), c["ticker"]),
            )[:2]
        if len(picks) == 4:
            return "listed_needs_bars", {"expiry": expiry, "contracts": picks}
    return "no_standard_four_contract_candidate", None


def merged_ranges(proof):
    targets = collections.defaultdict(set)
    for row in proof:
        if row["raw_state"] == "held":
            continue
        targets[row["cohort"], row["symbol"], row["option_ticker"], row["expiry"]].add(
            row["session"]
        )
    return [
        {
            "cohort": c,
            "symbol": s,
            "option_ticker": t,
            "expiry": e,
            "start": min(days),
            "end": max(days),
            "target_sessions": ",".join(sorted(days)),
        }
        for (c, s, t, e), days in sorted(targets.items())
    ]


def execution_ranges(proof):
    gate_days = sorted(
        {
            r["session"]
            for r in proof
            if r["symbol"] == "SPY" and r["cohort"] == "primary"
        },
        reverse=True,
    )[:2]
    phased = []
    for row in proof:
        phase = (
            "SPY_gate"
            if row["symbol"] == "SPY"
            and row["cohort"] == "primary"
            and row["session"] in gate_days
            else f"{row['symbol']}_{row['cohort']}"
        )
        phased.append(dict(row, cohort=phase))
    ranges = merged_ranges(phased)
    for row in ranges:
        row["execution_phase"] = row.pop("cohort")
        row["cohort"] = (
            "reserve" if row["execution_phase"].endswith("_reserve") else "primary"
        )
    return ranges


def plan(grid, references, held, occupied, reserve=3):
    keys = {(row["symbol"], row["session"]) for row in grid}
    if len(grid) != 756 or len(keys) != len(grid):
        raise ValueError("freeze 756 unique symbol/calendar-session rows (252 each)")
    dates = {
        s: {r["session"] for r in grid if r["symbol"] == s}
        for s in ("SPY", "NVDA", "AAPL")
    }
    if (
        any(len(v) != 252 for v in dates.values())
        or len({tuple(sorted(v)) for v in dates.values()}) != 1
    ):
        raise ValueError("freeze the same 252 calendar sessions for all three symbols")
    ref = {
        (r["params"]["underlying_ticker"], r["params"]["as_of"]): r for r in references
    }
    if len(ref) != len(references):
        raise ValueError("duplicate historical reference proofs")
    parents, proof, inventory, summary = [], [], [], {}
    for symbol in dates:
        rows = sorted(
            (r for r in grid if r["symbol"] == symbol),
            key=lambda r: r["session"],
            reverse=True,
        )
        counts = {t: sum(r[f"cone{t}"] for r in rows) for t in (90, 180)}
        projected = counts.copy()
        reserve_used = 0
        for row in rows:
            if row["cone90"] and row["cone180"]:
                continue
            reference = ref.get((symbol, row["session"]))
            state, pick = (
                historical_pick(row, reference)
                if reference
                else ("reference_unprobed", None)
            )
            if row.get("rate") is None or not math.isfinite(row["rate"]):
                state, pick = "missing_observed_rate", None
            if not any(7 <= d <= 90 for d in row["valid_dtes"]):
                state, pick = "missing_lower_bracket", None
            if pick and (symbol, row["session"], pick["expiry"]) in occupied:
                state, pick = "existing_parent_preserved", None
            inventory.append(
                dict(
                    row,
                    source_state=state,
                    candidate_expiry=pick["expiry"] if pick else None,
                )
            )
            if pick is None:
                continue
            primary = any(projected[t] < 60 and not row[f"cone{t}"] for t in (90, 180))
            cohort = "primary" if primary else "reserve"
            if not primary and reserve_used >= reserve:
                continue
            parent = {
                "symbol": symbol,
                "session": row["session"],
                "expiry": pick["expiry"],
                "cohort": cohort,
                "improves": [t for t in (90, 180) if not row[f"cone{t}"]],
            }
            parents.append(parent)
            for contract in pick["contracts"]:
                proof.append(
                    dict(
                        parent,
                        option_ticker=contract["ticker"],
                        raw_state="held"
                        if (contract["ticker"], row["session"]) in held
                        else "missing",
                    )
                )
            if primary:
                for tenor in parent["improves"]:
                    projected[tenor] += 1
            else:
                reserve_used += 1
        summary[symbol] = {
            "current": counts,
            "potential_primary": projected,
            "reaches_60_if_valid": all(n >= 60 for n in projected.values()),
            "primary": sum(
                p["symbol"] == symbol and p["cohort"] == "primary" for p in parents
            ),
            "reserve": reserve_used,
        }
    return {
        "summary": summary,
        "parents": parents,
        "proof": proof,
        "ranges": merged_ranges(proof),
        "execution-ranges": execution_ranges(proof),
        "inventory": inventory,
        "availability": "historical listing verified; eligible bars and IV not yet fetched",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = plan(
        data["grid"],
        data["references"],
        set(map(tuple, data["held"])),
        set(map(tuple, data["occupied"])),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for label in ("ranges", "execution-ranges", "proof", "parents", "inventory"):
        rows = result[label]
        if not rows:
            continue
        with (args.output / f"{label}.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    result["manifest_sha256"] = hashlib.sha256(
        (args.output / "ranges.csv").read_bytes()
    ).hexdigest()
    result["execution_manifest_sha256"] = hashlib.sha256(
        (args.output / "execution-ranges.csv").read_bytes()
    ).hexdigest()
    (args.output / "plan.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "summary": result["summary"],
                "parents": len(result["parents"]),
                "ranges": len(result["ranges"]),
                "target_days": sum(
                    len(r["target_sessions"].split(",")) for r in result["ranges"]
                ),
                "manifest_sha256": result["manifest_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
