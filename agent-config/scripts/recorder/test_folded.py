"""The fold result is opaque. publish_total takes nothing else."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from publish import publish_total
from read import Folded, fold_total
from test_support import folded_for_test


def _published(raw: bytes) -> dict:
    return json.loads(raw)


def test_a_dict_is_an_invalid_document():
    raw = publish_total({"at": 0, "fold_complete": True, "internal_errors": 0}, "board")
    published = _published(raw)
    assert published["recorder_failed"] == {
        "stage": "publish",
        "reason": "invalid_argument",
        "argument": "document",
    }
    assert published["internal_errors"] == 0


def test_folded_cannot_be_subclassed():
    with pytest.raises(TypeError):
        class _Child(Folded):
            pass


def test_a_lookalike_is_an_invalid_document():
    class _Look:
        def document(self):
            raise AssertionError("document")

        def __eq__(self, other):
            raise AssertionError("eq")

    raw = publish_total(_Look(), "board")
    published = _published(raw)
    assert published["recorder_failed"]["argument"] == "document"
    assert published["recorder_failed"]["reason"] == "invalid_argument"
    assert published["internal_errors"] == 0


def test_document_handed_back_is_an_invalid_document():
    folded = fold_total([], [], 1)
    raw = publish_total(folded.document(), "board")
    published = _published(raw)
    assert published["recorder_failed"]["argument"] == "document"
    assert published["internal_errors"] == 0


def test_mutating_the_document_copy_does_not_change_what_is_published():
    from harness import LogBuilder, _chain

    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id="w1", title="T")
    folded = fold_total([("w1", _chain(log.events))], [], 1)
    copied = folded.document()
    assert copied["ball"]["holder"] != "nobody"
    copied["ball"] = {"holder": "nobody", "why": "queue_done"}
    copied["fold_complete"] = False
    published = _published(publish_total(folded, "board"))
    assert published["ball"]["holder"] != "nobody"
    assert published["fold_complete"] is True


def test_review102_owner_now_zero_is_invalid_argument():
    raw = publish_total(
        {"at": 0, "fold_complete": True, "internal_errors": 0, "owner_now": 0},
        "board",
    )
    published = _published(raw)
    assert published["recorder_failed"]["reason"] == "invalid_argument"
    assert published["recorder_failed"]["argument"] == "document"
    assert "owner_now" not in published
    assert published["internal_errors"] == 0


def test_review102_failed_with_nobody_is_invalid_argument():
    seeded = fold_total([], [], True).document()
    seeded["fold_complete"] = True
    seeded["ball"] = {"holder": "nobody", "why": "queue_done"}
    published = _published(publish_total(seeded, "board"))
    assert published["recorder_failed"]["reason"] == "invalid_argument"
    assert published["recorder_failed"]["argument"] == "document"
    assert published["ball"]["holder"] == "unknown"
    assert published["internal_errors"] == 0


def test_a_str_subclass_host_is_not_compared():
    calls = {"eq": 0}

    class _Host(str):
        def __eq__(self, other):
            calls["eq"] += 1
            raise ValueError("eq")

    folded = fold_total([], [], 1)
    published = _published(publish_total(folded, _Host("board")))
    assert calls["eq"] == 0
    assert "host" not in published
    assert "host" in published["incomplete"]
    assert published["internal_errors"] == 0
    assert "recorder_failed" not in published


def test_for_test_door_is_not_named_outside_its_definition():
    root = Path(__file__).resolve().parent
    for path in root.glob("*.py"):
        if path.name.startswith("test_") or path.name in {"harness.py", "conftest.py"}:
            continue
        assert "folded_for_test" not in path.read_text(encoding="utf-8")
    tree = ast.parse((root / "test_support.py").read_text(encoding="utf-8"))
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert names == ["folded_for_test"]


def test_the_door_seals_a_reduction_document():
    folded = folded_for_test({
        "at": 1,
        "fold_complete": True,
        "internal_errors": 0,
        "ball": {"holder": "nobody", "why": "queue_done"},
        "works": [],
        "owner_all": [],
        "feed": [],
    })
    assert type(folded) is Folded
    published = _published(publish_total(folded, "board"))
    assert published["internal_errors"] == 0
    assert "recorder_failed" not in published
