"""Inventory safety and data distinctions. No database or vendor calls."""

import ast
import datetime as dt
import importlib.util
from pathlib import Path

from bifrost_research.engines.pine.context import term_30_60
from bifrost_research.engines.volatility.atm_iv import build_expiry_side_items
from bifrost_research.repositories.iv_cone import tenor_iv

HERE = Path(__file__).parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_grid_keeps_whole_day_absence_and_deduplicates_overlap():
    day = dt.date(2026, 8, 10)
    other = day - dt.timedelta(days=3)
    audit = module("audit-iv-gap-plan")
    grid = audit.inventory_grid(
        ["present", "missing"], ["present"], [other, day], day, day
    )
    assert grid == {("present", other), ("present", day), ("missing", day)}


def test_month_chunks_keep_leap_day_and_year_boundary():
    audit = module("audit-iv-gap-plan")
    assert list(audit.chunks(dt.date(2024, 2, 28), dt.date(2024, 3, 1))) == [
        (dt.date(2024, 2, 28), dt.date(2024, 2, 29)),
        (dt.date(2024, 3, 1), dt.date(2024, 3, 1)),
    ]
    assert list(audit.chunks(dt.date(2025, 12, 31), dt.date(2026, 1, 1))) == [
        (dt.date(2025, 12, 31), dt.date(2025, 12, 31)),
        (dt.date(2026, 1, 1), dt.date(2026, 1, 1)),
    ]


def test_joint_request_dedup_keeps_all_missing_days():
    audit = module("audit-iv-request-scope")
    key = ("NVDA", "O:test", dt.date(2026, 12, 18))
    a, b = dt.date(2026, 8, 10), dt.date(2026, 8, 11)
    assert audit.merged_requests({"td172": {key: {a}}, "td142": {key: {a, b}}}) == {
        key: {a, b}
    }


def test_zero_term_slope_is_a_valid_reading_and_absence_is_none():
    day = dt.date(2026, 8, 10)
    assert (
        term_30_60(
            day,
            [(day + dt.timedelta(days=25), 0.3), (day + dt.timedelta(days=65), 0.3)],
        )
        == 0
    )
    assert term_30_60(day, [(day + dt.timedelta(days=25), 0.3)]) is None


def test_long_cone_needs_bracket_and_rejects_invalid_iv():
    day = dt.date(2026, 8, 10)
    assert tenor_iv(day, [(day + dt.timedelta(days=150), 0.3)], 180) is None
    assert (
        tenor_iv(
            day,
            [(day + dt.timedelta(days=150), 0.3), (day + dt.timedelta(days=210), 0.5)],
            180,
        )
        == 0.4
    )
    assert (
        tenor_iv(
            day,
            [
                (day + dt.timedelta(days=150), 0.3),
                (day + dt.timedelta(days=210), float("nan")),
            ],
            180,
        )
        is None
    )


def test_two_put_bars_do_not_supply_the_required_brent_call_pair():
    rows = [
        {"strike": 180, "iv": 0.3, "option_right": "P"},
        {"strike": 185, "iv": 0.3, "option_right": "P"},
    ]
    items = build_expiry_side_items(rows, 199.05, max_moneyness=0.10, min_iv=0.05)
    assert len(items) == 2
    assert not any(r[1] is not None for r in items)


def test_inventory_tools_have_readonly_connections_and_no_writer_imports():
    for name in (
        "audit-iv-gap-plan",
        "audit-iv-request-scope",
        "audit-iv-snapshot-source",
    ):
        source = (HERE / f"{name}.py").read_text()
        tree = ast.parse(source)
        assert "default_transaction_read_only=on" in source
        assert "readonly=True" in source
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert all(
                    not alias.name.startswith(
                        ("compute_", "upsert", "insert_job", "project_vendor_")
                    )
                    for alias in node.names
                )
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert (
                    not node.value.strip()
                    .upper()
                    .startswith(
                        (
                            "INSERT ",
                            "UPDATE ",
                            "DELETE ",
                            "TRUNCATE ",
                            "CREATE ",
                            "ALTER ",
                            "DROP ",
                        )
                    )
                )
