"""The proposal cannot promote current, incomplete, or invalid reference data."""

import datetime as dt
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "depth", Path(__file__).with_name("audit-iv-depth-plan.py")
)
depth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(depth)


def fixture(symbol="SPY", day="2026-08-20"):
    row = {
        "symbol": symbol,
        "session": day,
        "spot": 100.0,
        "cone90": False,
        "cone180": False,
        "valid_dtes": [7, 30],
        "rate": 0.0,
    }
    date = dt.date.fromisoformat(day)
    expiry = date + dt.timedelta(days=200)
    contracts = [
        {
            "ticker": f"O:{symbol}{expiry:%y%m%d}{side}{strike * 1000:08d}",
            "expiration_date": str(expiry),
            "strike_price": strike,
            "contract_type": "call" if side == "C" else "put",
            "shares_per_contract": 100,
        }
        for side in ("C", "P")
        for strike in (100, 101)
    ]
    ref = {
        "params": dict(
            underlying_ticker=symbol,
            as_of=day,
            **{
                "expiration_date.gte": str(date + dt.timedelta(days=180)),
                "expiration_date.lte": str(date + dt.timedelta(days=220)),
                "strike_price.gte": 90.0,
                "strike_price.lte": 110.00000000000001,
            },
        ),
        "http": 200,
        "status": "OK",
        "truncated": False,
        "contracts": contracts,
    }
    return row, ref


def test_exact_historical_date_required():
    row, ref = fixture()
    ref["params"]["as_of"] = "2026-10-09"
    assert depth.historical_pick(row, ref) == ("wrong_as_of", None)


def test_partial_response_is_unknown_even_when_four_contracts_exist():
    row, ref = fixture()
    ref["truncated"] = True
    assert depth.historical_pick(row, ref) == ("reference_incomplete", None)
    ref["truncated"] = False
    ref["http"] = 403
    assert depth.historical_pick(row, ref) == ("reference_error", None)


def test_four_distinct_standard_contracts_and_both_sides():
    row, ref = fixture()
    assert depth.historical_pick(row, ref)[0] == "listed_needs_bars"
    ref["contracts"][-1]["shares_per_contract"] = 10
    assert depth.historical_pick(row, ref)[1] is None
    ref["contracts"][-1] = ref["contracts"][-2]
    assert depth.historical_pick(row, ref)[1] is None


def test_expiry_cap_and_complete_strike_band():
    row, ref = fixture()
    ref["params"]["expiration_date.lte"] = "2027-06-01"
    assert depth.historical_pick(row, ref)[0] == "wrong_band"
    row, ref = fixture()
    ref["params"]["strike_price.gte"] = 95
    assert depth.historical_pick(row, ref)[0] == "reference_incomplete_strikes"


def test_ranges_deduplicate_and_preserve_held_zero_bars():
    rows = [
        {
            "cohort": "primary",
            "symbol": "SPY",
            "option_ticker": "O:test",
            "expiry": "2027-03-19",
            "session": d,
            "raw_state": state,
        }
        for d, state in [
            ("2026-08-17", "missing"),
            ("2026-08-17", "missing"),
            ("2026-08-18", "held"),
            ("2026-08-20", "missing"),
        ]
    ]
    ranges = depth.merged_ranges(rows)
    assert len(ranges) == 1
    assert ranges[0]["target_sessions"] == "2026-08-17,2026-08-20"
    # The interval envelope never authorizes the held or intervening dates.
    assert ranges[0]["start"] == "2026-08-17" and ranges[0]["end"] == "2026-08-20"


def grid_fixture():
    grid, refs = [], []
    for symbol, n90, n180 in [("SPY", 39, 33), ("NVDA", 44, 43), ("AAPL", 41, 40)]:
        for i in range(252):
            row, ref = fixture(symbol, str(dt.date(2025, 10, 1) + dt.timedelta(days=i)))
            row.update(cone90=i < n90, cone180=i < n180)
            grid.append(row)
            refs.append(ref)
    return grid, refs


def test_one_new_far_expiry_can_improve_both_tenors_and_zero_rate_survives():
    grid, refs = grid_fixture()
    result = depth.plan(grid, refs, set(), set())
    assert result["summary"]["SPY"]["primary"] == 27
    assert result["summary"]["SPY"]["potential_primary"] == {90: 66, 180: 60}
    assert result["summary"]["NVDA"]["primary"] == 17
    assert result["summary"]["AAPL"]["primary"] == 20
    assert all(s["reserve"] == 3 for s in result["summary"].values())
    assert all(p["improves"] == [90, 180] for p in result["parents"])
    # Projections remain potential: no eligible bars were tested or written.
    assert "not yet fetched" in result["availability"]


def test_unknown_rate_and_existing_parent_fail_closed():
    grid, refs = grid_fixture()
    for row in grid:
        row["rate"] = None
    assert depth.plan(grid, refs, set(), set())["parents"] == []
    grid, refs = grid_fixture()
    occupied = {
        (r["symbol"], r["session"], refs[i]["contracts"][0]["expiration_date"])
        for i, r in enumerate(grid)
    }
    assert depth.plan(grid, refs, set(), occupied)["parents"] == []


def test_missing_calendar_day_cannot_shrink_denominator():
    grid, refs = grid_fixture()
    try:
        depth.plan(grid[:-1], refs, set(), set())
    except ValueError as error:
        assert "252" in str(error)
    else:
        raise AssertionError("missing calendar day accepted")


def test_duplicate_session_cannot_inflate_effective_count():
    grid, refs = grid_fixture()
    grid.append(grid[-1])
    try:
        depth.plan(grid, refs, set(), set())
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate calendar session accepted")


def test_spy_gate_splits_requests_without_expanding_target_dates():
    proof = [
        {
            "cohort": "primary",
            "symbol": "SPY",
            "option_ticker": "O:test",
            "expiry": "2027-03-19",
            "session": d,
            "raw_state": "missing",
        }
        for d in ["2026-08-17", "2026-09-02", "2026-09-03"]
    ]
    rows = depth.execution_ranges(proof)
    assert len(rows) == 2
    assert {r["execution_phase"] for r in rows} == {"SPY_gate", "SPY_primary"}
    assert sorted(d for r in rows for d in r["target_sessions"].split(",")) == [
        "2026-08-17",
        "2026-09-02",
        "2026-09-03",
    ]
