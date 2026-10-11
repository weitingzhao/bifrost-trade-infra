"""T01, T02, T16, T17, T21, T31."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from decide import PIN_FIELDS, POST_FIELDS, PRE_FIELDS, RoundEvidence, StepView, decide
from support import A, B, TA, TB, implement_ok, make_lane, review_ok, sha_set, verify_ok

WRONG = "f" * 40


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


def _repo(commit: str, tree: str, *, implement: bool, kind: str = "baseline") -> dict:
    body = {"commit": commit, "tree": tree, "clean": True, "hidden": False}
    if implement:
        body["kind"] = kind
        body["expected"] = {"commit": commit, "tree": tree}
    else:
        body["consumed"] = {"commit": commit, "tree": tree}
    return body


def _check(step: str, commit: str, tree: str, *, ok: bool = True, reason: str | None = None, kind: str = "baseline") -> dict:
    implement = step == "implement"
    body = {"ok": ok, "repos": {"repo": _repo(commit, tree, implement=implement, kind=kind)}}
    if implement:
        body["kind"] = kind
    if reason:
        body["reason"] = reason
    return body


def _post(step: str, commit: str, tree: str) -> dict:
    if step == "implement":
        return {}
    return {"repos": {"repo": _repo(commit, tree, implement=False)}}


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
        pre_checks=_check("implement", A, TA),
    )
    verify = StepView(
        "verify",
        "ran",
        True,
        exit={"code": 0, "signal": None},
        termination="exited",
        checks=_post("verify", B, TB),
        fields={"stdout_last_line": "VERDICT: pass"},
        consumed=pinned,
        pre_checks=_check("verify", B, TB),
    )
    review = StepView(
        "review",
        "ran",
        True,
        exit={"code": 0, "signal": None},
        termination="exited",
        checks=_post("review", B, TB),
        fields={"report_first_line": "VERDICT: safe to merge", "report_last_line": "END OF REPORT", "p1": 0, "p2": 0, "p3": 0},
        consumed=pinned,
        report={"present": True, "length": 40, "sha256": "cd" * 32},
        pre_checks=_check("review", B, TB),
    )
    return RoundEvidence(
        1,
        {"implement": implement, "verify": verify, "review": review},
        {"repo": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA}},
        expected_start={"repo": {"commit": A, "tree": TA}},
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
        ("git-nonzero", lambda ev: _step(ev, "verify", checks={**ev.steps["verify"].checks, "git_failed": "repo"}), "step_failed", "snapshot of repo changed during verify"),
        ("context-moved", lambda ev: _context(ev), "step_failed", "context repository ctx moved"),
        ("start", lambda ev: _step(ev, "implement", consumed=sha_set(B, TB), pre_checks=_check("implement", B, TB)), "step_failed", f"implement did not start: repo HEAD {B} != expected {A}"),
        ("pre-check-missing", lambda ev: _step(ev, "implement", pre_checks={}), "unknown", "evidence invalid: implement pre-check missing"),
        ("pre-check-failed", lambda ev: _step(ev, "implement", pre_checks=_check("implement", A, TA, ok=False, reason="worktree is dirty")), "step_failed", "implement did not start: worktree is dirty"),
        ("consumed-mismatch", lambda ev: _step(ev, "verify", consumed=sha_set(A, TA)), "step_failed", "verify ran on a different SHA set"),
        ("bundle-missing", lambda ev: _step(ev, "implement", bundles={}), "step_failed", "cannot export repo: HEAD moved"),
        ("rejected-set", lambda ev: replace(ev, round_no=2, rejected=({"round": 1, "sha_set": ev.steps["implement"].pinned},)), "step_failed", "no new commit since round 1 said fix first"),
        ("close-failed", lambda ev: _closing(ev, "failed"), "step_failed", "review closed as failed by ada: because"),
        ("close-cancelled", lambda ev: _closing(ev, "cancelled"), "step_failed", "review closed as cancelled by ada: because"),
        ("close-evidence-lost", lambda ev: _closing(ev, "evidence-lost"), "step_failed", "review closed as evidence-lost by ada: because"),
        ("still-unknown", lambda ev: replace(ev, resolutions=({"step": "implement", "kind": "still-unknown", "operator": "ada", "reason": "looked", "attempt_id": "a"},)), "passed", "round 1 passed for repo:bbbbbbbbbbbb"),
        ("context-start", lambda ev: _context_start(ev), "step_failed", "context repository ctx moved"),
    ],
)
def test_t31_pass_contract_each_gap_is_not_passed(name, mutate, result, reason):
    got = decide(mutate(_passed()))
    assert got == (result, reason), name


def _closing(evidence: RoundEvidence, kind: str) -> RoundEvidence:
    return replace(
        evidence,
        resolutions=({"step": "review", "kind": kind, "operator": "ada", "reason": "because", "attempt_id": "a"},),
    )


def _with_context(evidence: RoundEvidence, *, found: str, found_tree: str, pinned_commit: str, pinned_tree: str) -> RoundEvidence:
    targets = dict(evidence.targets)
    targets["ctx"] = {"role": "context", "target_ref": "main", "target_sha": A, "tree": TA}
    expected = dict(evidence.expected_start)
    expected["ctx"] = {"commit": A, "tree": TA}
    pinned = dict(evidence.steps["implement"].pinned)
    pinned["ctx"] = {"commit": pinned_commit, "tree": pinned_tree}
    pre = dict(evidence.steps["implement"].pre_checks or {})
    repos = dict(pre.get("repos") or {})
    repos["ctx"] = {
        "commit": found,
        "tree": found_tree,
        "clean": True,
        "hidden": False,
        "kind": "baseline",
        "expected": {"commit": A, "tree": TA},
    }
    consumed = dict(evidence.steps["implement"].consumed or {})
    consumed["ctx"] = {"commit": found, "tree": found_tree}
    return _step(
        replace(evidence, targets=targets, expected_start=expected),
        "implement",
        pinned=pinned,
        pre_checks={**pre, "repos": repos},
        consumed=consumed,
    )


def _context(evidence: RoundEvidence) -> RoundEvidence:
    return _with_context(evidence, found=A, found_tree=TA, pinned_commit=B, pinned_tree=TB)


def _context_start(evidence: RoundEvidence) -> RoundEvidence:
    return _with_context(evidence, found=B, found_tree=TB, pinned_commit=A, pinned_tree=TA)


def _set_path(node: dict, path: str, value) -> None:
    parts = path.split(".")
    cursor = node
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def _delete_path(node: dict, path: str) -> None:
    parts = path.split(".")
    cursor = node
    for part in parts[:-1]:
        cursor = cursor[part]
    del cursor[parts[-1]]


def _apply(node: dict, field: str, mode: str, *, pin_baseline: bool = False) -> None:
    if mode == "delete":
        _delete_path(node, field)
        return
    if mode == "mistype":
        _set_path(node, field, "no" if field in ("clean", "hidden") else 0)
        return
    if field == "clean":
        _set_path(node, field, False)
    elif field == "hidden":
        _set_path(node, field, True)
    elif field == "kind":
        _set_path(node, field, "pinned")
    elif pin_baseline and field == "commit":
        _set_path(node, field, A)
    else:
        _set_path(node, field, WRONG)


def _mutate(evidence: RoundEvidence, where: str, step: str, field: str, mode: str) -> RoundEvidence:
    if where == "expected":
        expected = deepcopy(evidence.expected_start)
        _apply(expected["repo"], field, mode)
        return replace(evidence, expected_start=expected)
    view = evidence.steps[step]
    if where == "consumed" and mode == "delete-set":
        return _step(evidence, step, consumed=None)
    if where == "pre":
        pre = deepcopy(view.pre_checks)
        if mode == "missing-repo":
            del pre["repos"][field]
        elif mode == "extra-repo":
            pre["repos"][field] = deepcopy(pre["repos"]["repo"])
        else:
            _apply(pre["repos"]["repo"], field, mode)
        return _step(evidence, step, pre_checks=pre)
    if where == "post":
        checks = deepcopy(view.checks)
        if mode == "missing-repo":
            del checks["repos"][field]
        elif mode == "extra-repo":
            checks["repos"][field] = deepcopy(checks["repos"]["repo"])
        else:
            _apply(checks["repos"]["repo"], field, mode)
        return _step(evidence, step, checks=checks)
    if where == "pinned":
        pinned = deepcopy(view.pinned)
        if mode == "missing-repo":
            del pinned[field]
        elif mode == "extra-repo":
            pinned[field] = deepcopy(pinned["repo"])
        else:
            _apply(pinned["repo"], field, mode, pin_baseline=True)
        return _step(evidence, step, pinned=pinned)
    consumed = deepcopy(view.consumed)
    _apply(consumed["repo"], field, mode)
    return _step(evidence, step, consumed=consumed)


def _shape_cases() -> list[tuple]:
    rows = []
    for step, fields in PRE_FIELDS.items():
        for path, _typ in fields:
            for mode in ("delete", "mistype", "wrong"):
                rows.append(("pre", step, path, mode))
        rows.append(("pre", step, "repo", "missing-repo"))
        rows.append(("pre", step, "extra", "extra-repo"))
    for step, fields in POST_FIELDS.items():
        for path, _typ in fields:
            for mode in ("delete", "mistype", "wrong"):
                rows.append(("post", step, path, mode))
        rows.append(("post", step, "repo", "missing-repo"))
        rows.append(("post", step, "extra", "extra-repo"))
    for path, _typ in PIN_FIELDS:
        modes = ("delete", "mistype", "wrong") if path == "commit" else ("delete", "mistype")
        for mode in modes:
            rows.append(("pinned", "implement", path, mode))
    rows.append(("pinned", "implement", "repo", "missing-repo"))
    rows.append(("pinned", "implement", "extra", "extra-repo"))
    for step in ("implement", "verify", "review"):
        for path in ("commit", "tree"):
            for mode in ("delete", "mistype", "wrong"):
                rows.append(("consumed", step, path, mode))
        rows.append(("consumed", step, "*", "delete-set"))
    for field in ("commit", "tree"):
        for mode in ("delete", "mistype", "wrong"):
            rows.append(("expected", "start", field, mode))
    return rows


def _case_id(row: tuple) -> str:
    where, step, field, mode = row
    if mode in ("missing-repo", "extra-repo", "delete-set"):
        return f"{where}-{step}-{mode}"
    return f"{where}-{step}-{field}-{mode}"


def _expect(where: str, step: str, field: str, mode: str) -> tuple[str, str]:
    if where == "expected":
        if mode in ("delete", "mistype"):
            return "unknown", "evidence invalid: expected start incomplete in events"
        if field == "commit":
            return "step_failed", f"implement did not start: repo HEAD {A} != expected {WRONG}"
        return "step_failed", f"implement did not start: repo tree {TA} != expected {WRONG}"
    kind = {"pre": "pre-check", "post": "post-check", "pinned": "pinned", "consumed": "pre-check"}[where]
    if mode == "delete-set":
        return "unknown", f"evidence invalid: {step} pre-check consumed"
    if mode == "missing-repo":
        return "unknown", f"evidence invalid: {step} {kind} missing repo repo"
    if mode == "extra-repo":
        return "unknown", f"evidence invalid: {step} {kind} extra repo extra"
    if mode in ("delete", "mistype"):
        leaf = "missing" if mode == "delete" else "type"
        prefix = "consumed." if where == "consumed" else ""
        return "unknown", f"evidence invalid: {step} {kind} {prefix}repo.{field} {leaf}"
    if where == "pinned":
        return "step_failed", "implement produced no commit"
    if field == "clean":
        if step == "implement":
            return "step_failed", "implement did not start: repo worktree is dirty"
        return "step_failed", f"snapshot of repo changed during {step}"
    if field == "hidden":
        return "step_failed", "hidden index flag in repo"
    if field == "kind":
        return "step_failed", "implement did not start: repo start kind pinned != baseline"
    if field == "expected.tree":
        return "step_failed", f"implement did not start: repo expected tree {WRONG} != {TA}"
    if field == "expected.commit":
        return "step_failed", f"implement did not start: repo expected {WRONG} != {A}"
    if field in ("consumed.commit", "consumed.tree"):
        return "step_failed", f"{step} ran on a different SHA set"
    if field == "tree" and step == "implement" and where in ("pre", "consumed"):
        return "step_failed", f"implement did not start: repo tree {WRONG} != expected {TA}"
    if field == "commit" and step == "implement" and where in ("pre", "consumed"):
        return "step_failed", f"implement did not start: repo HEAD {WRONG} != expected {A}"
    if field in ("commit", "tree"):
        return "step_failed", f"{step} ran on a different SHA set"
    raise AssertionError(f"no row for {where} {step} {field} {mode}")


_SHAPE_CASES = _shape_cases()


@pytest.mark.parametrize(("where", "step", "field", "mode"), _SHAPE_CASES, ids=[_case_id(row) for row in _SHAPE_CASES])
def test_t31_shape_is_exhaustive(where, step, field, mode):
    got = decide(_mutate(_passed(), where, step, field, mode))
    assert got[0] != "passed"
    assert got == _expect(where, step, field, mode), (where, step, field, mode)


def test_t31_reviewer_wrong_start_trees_are_not_passed():
    base = _passed()
    verify = decide(_mutate(base, "pre", "verify", "tree", "wrong"))
    review = decide(_mutate(base, "pre", "review", "tree", "wrong"))
    assert verify == ("step_failed", "verify ran on a different SHA set")
    assert review == ("step_failed", "review ran on a different SHA set")
    assert verify[0] != "passed" and review[0] != "passed"


def test_t31_reviewer_deleted_precheck_fields_are_not_passed():
    base = _passed()
    for step in ("implement", "verify", "review"):
        for field in ("tree", "clean", "hidden"):
            got = decide(_mutate(base, "pre", step, field, "delete"))
            assert got[0] != "passed"
            assert got[0] == "unknown"
            assert got[1] == f"evidence invalid: {step} pre-check repo.{field} missing"


def test_t31_reviewer_deleted_implement_consumed_is_not_passed():
    got = decide(_mutate(_passed(), "consumed", "implement", "*", "delete-set"))
    assert got == ("unknown", "evidence invalid: implement pre-check consumed")


T1 = "4" * 40
T2 = "5" * 40
T3 = "6" * 40


def _three_pre(commit: str, *, kind: str = "baseline") -> dict:
    return {
        "ok": True,
        "kind": kind,
        "repos": {
            "repo": {
                "commit": commit,
                "tree": T1,
                "clean": True,
                "hidden": False,
                "kind": kind,
                "expected": {"commit": commit, "tree": T2},
            }
        },
    }


def test_reviewer_three_trees_round_1_are_not_passed(tmp_path):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(
        lane,
        consumed=sha_set(A, TA),
        pre_checks=_three_pre(A),
        pinned=sha_set(B, TB),
    )
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["state"] != "passed"
    assert status["reason"] == f"implement did not start: repo tree {T1} != expected {TA}"


def test_reviewer_three_trees_after_baseline_are_not_passed(tmp_path):
    from commands import cmd_next_round

    lane = make_lane(tmp_path, "B2", max_rounds=3)
    implement_ok(lane, exit_code=9)
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief), start="baseline")
    implement_ok(
        lane,
        consumed=sha_set(A, TA),
        pre_checks=_three_pre(A),
        pinned=sha_set(B, TB),
    )
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["state"] != "passed"
    assert status["reason"] == f"implement did not start: repo tree {T1} != expected {TA}"


def test_reviewer_three_trees_on_a_context_repository_are_not_passed(tmp_path):
    repos = {
        "repo": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA},
        "ctx": {"role": "context", "target_ref": "main", "target_sha": A, "tree": TA},
    }
    lane = make_lane(tmp_path, "CTX", repos=repos)
    pre = {
        "ok": True,
        "kind": "baseline",
        "repos": {
            "repo": {
                "commit": A,
                "tree": TA,
                "clean": True,
                "hidden": False,
                "kind": "baseline",
                "expected": {"commit": A, "tree": TA},
            },
            "ctx": {
                "commit": A,
                "tree": T1,
                "clean": True,
                "hidden": False,
                "kind": "baseline",
                "expected": {"commit": A, "tree": T2},
            },
        },
    }
    implement_ok(
        lane,
        consumed={"repo": {"commit": A, "tree": TA}, "ctx": {"commit": A, "tree": TA}},
        pre_checks=pre,
        pinned={"repo": {"commit": B, "tree": TB}, "ctx": {"commit": A, "tree": TA}},
    )
    status = lane.status()
    assert status["state"] == "step_failed"
    assert status["state"] != "passed"
    assert status["reason"] == "context repository ctx moved"


def test_expected_side_missing_a_tree_is_not_passed(tmp_path):
    lane = make_lane(tmp_path, "MISS")
    implement_ok(
        lane,
        consumed={"repo": {"commit": A}},
        pre_checks=_check("implement", A, TA),
        pinned=sha_set(B, TB),
    )
    status = lane.status()
    assert status["state"] != "passed"
    assert status["reason"] == "evidence invalid: event 3 step_intent: consumed repo.tree missing"
    synthetic = decide(_mutate(_passed(), "expected", "start", "tree", "delete"))
    assert synthetic[0] != "passed"
    assert synthetic == ("unknown", "evidence invalid: expected start incomplete in events")
    none_tree = deepcopy(_passed().expected_start)
    none_tree["repo"]["tree"] = None
    got = decide(replace(_passed(), expected_start=none_tree))
    assert got[0] != "passed"
    assert got == ("unknown", "evidence invalid: expected start incomplete in events")


def test_duplicate_repository_in_new(tmp_path, capsys):
    from lane import main

    root = tmp_path / "lanes"
    root.mkdir()
    brief = tmp_path / "brief.md"
    brief.write_text("task\n")
    spec = f"repo:change:main:{A}:{TA}"
    code = main(
        ["--root", str(root), "new", "L", "--title", "Title", "--brief", str(brief), "--repo", spec, "--repo", spec]
    )
    assert code == 1
    assert "duplicate repository repo" in capsys.readouterr().err
    assert not (root / "L").exists()


def test_duplicate_json_key_is_refused():
    from evidence import json_loads

    with pytest.raises(ValueError, match="duplicate key"):
        json_loads('{"repo": {"commit": "a", "tree": "1"}, "repo": {"commit": "b", "tree": "2"}}')


def test_unknown_field_on_each_side():
    base = _passed()
    pre = deepcopy(base.steps["implement"].pre_checks)
    pre["repos"]["repo"]["note"] = "extra"
    actual = decide(_step(base, "implement", pre_checks=pre))
    assert actual[0] != "passed"
    assert actual == ("unknown", "evidence invalid: implement pre-check repo.note unknown")
    expected = deepcopy(base.expected_start)
    expected["repo"]["note"] = "extra"
    other = decide(replace(base, expected_start=expected))
    assert other[0] != "passed"
    assert other == ("unknown", "evidence invalid: expected start incomplete in events")


def test_decide_does_not_guard_a_comparison_on_an_expected_value():
    text = Path(__file__).with_name("decide.py").read_text(encoding="utf-8")
    guarded = re.compile(r"\bif\s+(?:exp_[A-Za-z0-9_]*|expected\b)")
    truthy = re.compile(r"\b(?:and|or)\s+(?:exp_[A-Za-z0-9_]*|expected)\b")
    assert guarded.search(text) is None
    assert truthy.search(text) is None
