"""T01, T02, T16, T17, T21, T31."""

from __future__ import annotations

from dataclasses import replace

import pytest

from decide import RoundEvidence, StepView, decide
from support import A, B, TA, TB, implement_ok, make_lane, review_ok, sha_set, verify_ok


def test_t01_verify_pass_text_with_exit_7(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    lane.record(step="verify", stdout=b"VERDICT: pass\n", exit_code=7, consumed=sha_set(B, TB), checks={})
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "verify exited 7"
    assert "review" not in [event["exec"]["step"] for event in lane.events() if event["type"] == "step_intent"]


def test_t02_review_safe_text_with_exit_9(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    verify_ok(lane)
    report = b"VERDICT: safe to merge\n\nbody\n\nEND OF REPORT\n"
    lane.record(step="review", report=report, exit_code=9, consumed=sha_set(B, TB), checks={})
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "review exited 9"


def test_t16_pass_text_not_on_the_last_line(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    stdout = b"example\nVERDICT: pass\nnot the verdict\n"
    lane.record(step="verify", stdout=stdout, consumed=sha_set(B, TB), checks={})
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "verify produced no verdict"


def test_t17_bom_leading_blanks_and_truncated_report(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    verify_ok(lane)
    report = b"\xef\xbb\xbf\n\nVERDICT: safe to merge\n\nbody\n\nEND OF REPORT\n"
    lane.record(step="review", report=report, consumed=sha_set(B, TB), checks={})
    assert lane.status()["state"] == "passed"

    other = make_lane(tmp_path, "L2")
    implement_ok(other)
    verify_ok(other)
    truncated = b"\xef\xbb\xbf\n\nVERDICT: safe to merge\n\nstill writing\n"
    other.record(step="review", report=truncated, consumed=sha_set(B, TB), checks={})
    status = other.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "review report is truncated"


def test_t21_pass_text_only_on_stderr(tmp_path):
    lane = make_lane(tmp_path)
    implement_ok(lane)
    lane.record(
        step="verify",
        stdout=b"no verdict here\n",
        stderr=b"VERDICT: pass\n",
        consumed=sha_set(B, TB),
        checks={},
    )
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["reason"] == "verify produced no verdict"


def _passed() -> RoundEvidence:
    pinned = sha_set(B, TB)
    base = sha_set(A, TA)
    bundle = {"repo": {"length": 6, "sha256": "ab" * 32}}
    implement = StepView(
        "implement",
        "ran",
        True,
        exit={"code": 0, "signal": None},
        termination="exited",
        checks={},
        fields={},
        pinned=pinned,
        bundles=bundle,
        consumed=base,
        notes=("uncommitted changes in repo are not part of this round",),
    )
    verify = StepView(
        "verify",
        "ran",
        True,
        exit={"code": 0, "signal": None},
        termination="exited",
        checks={},
        fields={"stdout_last_line": "VERDICT: pass"},
        consumed=pinned,
    )
    review = StepView(
        "review",
        "ran",
        True,
        exit={"code": 0, "signal": None},
        termination="exited",
        checks={},
        fields={"report_first_line": "VERDICT: safe to merge", "report_last_line": "END OF REPORT", "p1": 0, "p2": 0, "p3": 0},
        consumed=pinned,
        report={"present": True, "length": 40, "sha256": "cd" * 32},
    )
    return RoundEvidence(
        1,
        {"implement": implement, "verify": verify, "review": review},
        {"repo": {"role": "change", "target_ref": "main", "target_sha": A}},
    )


def _step(evidence: RoundEvidence, name: str, **kwargs) -> RoundEvidence:
    steps = dict(evidence.steps)
    steps[name] = replace(steps[name], **kwargs)
    return replace(evidence, steps=steps)


@pytest.mark.parametrize(
    ("name", "mutate", "result", "reason"),
    [
        ("intact", lambda ev: ev, "passed", "round 1 passed for repo:bbbbbbbbbbbb"),
        ("manifest-missing", lambda ev: _step(ev, "verify", presence="invalid", invalid_which="manifest missing"), "unknown", "evidence invalid: verify manifest missing"),
        ("bad-shape", lambda ev: _step(ev, "verify", presence="invalid", invalid_which="manifest shape"), "unknown", "evidence invalid: verify manifest shape"),
        ("signal", lambda ev: _step(ev, "verify", exit={"code": None, "signal": 15}), "step_failed", "verify ended by signal 15"),
        ("nonzero", lambda ev: _step(ev, "implement", exit={"code": 9, "signal": None}), "step_failed", "implement exited 9"),
        ("termination", lambda ev: _step(ev, "verify", termination="timed_out"), "step_failed", "verify timed_out by the executor"),
        ("extra-char", lambda ev: _step(ev, "verify", fields={"stdout_last_line": "VERDICT: passX"}), "step_failed", "verify produced no verdict"),
        ("truncated", lambda ev: _step(ev, "review", fields={"report_first_line": "VERDICT: safe to merge", "report_last_line": "END OF REPOR", "p1": 0, "p2": 0, "p3": 0}), "step_failed", "review report is truncated"),
        ("no-report", lambda ev: _step(ev, "review", report={"present": False}), "step_failed", "review produced no report"),
        ("git-nonzero", lambda ev: _step(ev, "verify", checks={"git_failed": "repo"}), "step_failed", "snapshot of repo changed during verify"),
        ("context-moved", lambda ev: _context(ev), "step_failed", "context repository ctx moved"),
    ],
)
def test_t31_pass_contract_each_gap_is_not_passed(name, mutate, result, reason):
    got = decide(mutate(_passed()))
    assert got == (result, reason), name


def _context(evidence: RoundEvidence) -> RoundEvidence:
    targets = dict(evidence.targets)
    targets["ctx"] = {"role": "context", "target_ref": "main", "target_sha": A}
    pinned = dict(evidence.steps["implement"].pinned)
    pinned["ctx"] = {"commit": B, "tree": TB}
    return _step(replace(evidence, targets=targets), "implement", pinned=pinned)
