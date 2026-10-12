"""Every argument check, type and range, with an empty log and a non-empty one."""

from __future__ import annotations

import json
import math

from harness import WORK, LogBuilder, _chain
from publish import publish_total
from read import fold_total


def _log() -> bytes:
    built = LogBuilder()
    built.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    return _chain(built.events)


def _pairs():
    yield "empty", []
    yield "nonempty", [("w1", _log())]


def _fallback(folded) -> dict:
    return json.loads(publish_total(folded, "board"))


def _assert_argument(doc: dict, argument: str) -> None:
    assert doc["recorder_failed"]["reason"] == "invalid_argument"
    assert doc["recorder_failed"]["argument"] == argument
    assert doc["internal_errors"] == 0
    assert doc["ball"]["holder"] == "unknown"
    assert doc["fold_complete"] is False


def test_a_forward_clock_is_not_backwards_and_the_scan_returns():
    """A later event is outside a backwards interval, and the scan finishes.

    Dropping the rewind comparison leaves the index unmoved and never returns.
    """
    import threading

    from validate import _backwards

    samples = (([{"at": 1}, {"at": 2}], set()), ([{"at": 10}, {"at": 1}], {1}))
    for events, expected in samples:
        box = {}

        def run(events=events):
            box["got"] = _backwards(events)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(2)
        assert not thread.is_alive()
        assert box["got"] == expected


def test_now_type_empty_and_nonempty():
    calls = {"n": 0}

    class _Now:
        def __eq__(self, other):
            calls["n"] += 1
            return False

    for _name, logs in _pairs():
        for now in (True, "1", None, _Now()):
            _assert_argument(_fallback(fold_total(logs, [], now)), "now")
    assert calls["n"] == 0


def test_now_range_empty_and_nonempty():
    for _name, logs in _pairs():
        for now in (10**400, -10**400, 2**53 + 1, math.nan, math.inf, -math.inf):
            _assert_argument(_fallback(fold_total(logs, [], now)), "now")


def test_logs_unread_type_and_range():
    for _name, logs in _pairs():
        for count in (True, -1, 1.0, (1 << 53) + 1, 10**5000):
            _assert_argument(_fallback(fold_total(logs, [], 1, count)), "logs_unread")


def test_logs_type_rejects_without_calling_methods():
    calls = {"n": 0}

    class _Trap:
        def _hit(self, *args, **kwargs):
            calls["n"] += 1
            return False

        __eq__ = __lt__ = __len__ = __iter__ = __bool__ = __str__ = __repr__ = __hash__ = _hit

    _assert_argument(_fallback(fold_total(_Trap(), [], 1)), "logs")
    _assert_argument(_fallback(fold_total([_Trap()], [], 1)), "logs")
    _assert_argument(_fallback(fold_total([(_Trap(), b"")], [], 1)), "logs")
    assert calls["n"] == 0


def test_observer_type_rejects_without_calling_methods():
    calls = {"n": 0}

    class _Trap:
        def _hit(self, *args, **kwargs):
            calls["n"] += 1
            return False

        __eq__ = __lt__ = __len__ = __iter__ = __bool__ = __str__ = __repr__ = __hash__ = _hit

    for _name, logs in _pairs():
        _assert_argument(_fallback(fold_total(logs, _Trap(), 1)), "observer")
        _assert_argument(_fallback(fold_total(logs, [_Trap()], 1)), "observer")
    assert calls["n"] == 0


def test_host_type_and_shape_empty_and_nonempty():
    calls = {"n": 0}

    class _Host(str):
        def __eq__(self, other):
            calls["n"] += 1
            raise ValueError("eq")

    for _name, logs in _pairs():
        folded = fold_total(logs, [], 1)
        for host in (_Host("board"), "bad\nhost", "h" * 65, "bad\ud800host"):
            published = json.loads(publish_total(folded, host))
            assert calls["n"] == 0
            assert "recorder_failed" not in published
            assert published["internal_errors"] == 0
            assert "host" not in published
            assert "host" in published["incomplete"]


def test_blocks_type_and_shape_empty_and_nonempty():
    calls = {"n": 0}

    class _Trap:
        def _hit(self, *args, **kwargs):
            calls["n"] += 1
            return False

        __eq__ = __len__ = __iter__ = __bool__ = __str__ = _hit

    deep = {"k": 0}
    cursor = deep
    for _ in range(12):
        cursor["k"] = {}
        cursor = cursor["k"]
    samples = (
        _Trap(),
        deep,
        {"recent": [10**400]},
        {"password": "x"},
        {"coordinator": "nope"},
        {"recent": ["has\nnewline"]},
    )
    for _name, logs in _pairs():
        folded = fold_total(logs, [], 1)
        for blocks in samples:
            published = json.loads(publish_total(folded, "board", blocks))
            assert "recorder_failed" not in published
            assert published["internal_errors"] == 0
            assert published.get("incomplete")
            blob = json.dumps(published)
            assert "password" not in blob
            assert "token" not in blob
            assert "has\\nnewline" not in blob and "has\nnewline" not in blob
    assert calls["n"] == 0


def test_a_forged_folded_is_an_invalid_document():
    for value in ({"at": 0, "fold_complete": True}, b"{}", object()):
        published = json.loads(publish_total(value, "board"))
        _assert_argument(published, "document")
