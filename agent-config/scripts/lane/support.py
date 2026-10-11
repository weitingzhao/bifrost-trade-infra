"""Shared fixtures for lane round-1 tests. No absolute home paths."""

from __future__ import annotations

from pathlib import Path

from commands import cmd_new, cmd_status
from events import load_file
from query import created, current_round, expected_start, start_kind
from recorder import record_attempt

A = "a" * 40
B = "b" * 40
C = "c" * 40
TA = "1" * 40
TB = "2" * 40
TC = "3" * 40


def sha_set(commit: str, tree: str, name: str = "repo") -> dict:
    return {name: {"commit": commit, "tree": tree}}


def _repo_check(info: dict, *, implement: bool, kind: str) -> dict:
    body = {
        "commit": info.get("commit"),
        "tree": info.get("tree"),
        "clean": True,
        "hidden": False,
    }
    if implement:
        body["kind"] = kind
        body["expected"] = {"commit": info.get("commit"), "tree": info.get("tree")}
    else:
        body["consumed"] = {"commit": info.get("commit"), "tree": info.get("tree")}
    return body


def passing_prechecks(step: str, found: dict, *, kind: str = "baseline", expected: dict | None = None) -> dict:
    source = expected if expected is not None else found
    repos = {}
    for name, info in (found or {}).items():
        seen = dict(info or {})
        if step == "implement":
            exp = (source or {}).get(name) or seen
            seen = dict(seen)
            # The found HEAD is ``info``; the recorded expected start is ``exp``.
            body = _repo_check(seen, implement=True, kind=kind)
            body["expected"] = {"commit": exp.get("commit"), "tree": exp.get("tree")}
            repos[name] = body
        else:
            repos[name] = _repo_check(seen, implement=False, kind=kind)
    body = {"ok": True, "repos": repos}
    if step == "implement":
        body["kind"] = kind
    return body


def passing_postchecks(step: str, found: dict) -> dict:
    if step == "implement":
        return {}
    repos = {}
    for name, info in (found or {}).items():
        repos[name] = _repo_check(info or {}, implement=False, kind="baseline")
    return {"repos": repos}


def _materialize(start: dict) -> dict:
    trees = {A: TA, B: TB, C: TC}
    found = {}
    for name, info in start.items():
        commit = info.get("commit") or A
        tree = info.get("tree") or trees.get(commit) or TA
        found[name] = {"commit": commit, "tree": tree}
    return found


def _expected_consumed(lane: Lane) -> dict:
    events = lane.events()
    rnd = current_round(events) or 1
    targets = (created(events) or {}).get("repos") or {}
    return _materialize(expected_start(events, rnd, targets)) or sha_set(A, TA)


class Lane:
    def __init__(self, root: Path, lane_id: str, brief: Path):
        self.root = root
        self.lane_id = lane_id
        self.brief = brief
        self.dir = root / lane_id

    def status(self, **kw):
        return cmd_status(self.root, self.lane_id, **kw)

    def events(self) -> list[dict]:
        return load_file(self.dir / "events.jsonl").events

    def record(self, **kwargs) -> dict:
        # Tests stand in for the round-2 caller and supply a complete check
        # unless they pass one themselves.
        step = kwargs.get("step") or "implement"
        if "pre_checks" not in kwargs:
            kind = "baseline"
            expected = None
            found = kwargs.get("consumed") or {}
            if step == "implement":
                events = self.events()
                rnd = current_round(events) or 1
                kind = start_kind(events, rnd)
                targets = (created(events) or {}).get("repos") or {}
                expected = _materialize(expected_start(events, rnd, targets))
                if not found:
                    found = expected
                    kwargs["consumed"] = found
            kwargs["pre_checks"] = passing_prechecks(step, found, kind=kind, expected=expected or found)
        if step in ("verify", "review"):
            post = passing_postchecks(step, kwargs.get("consumed") or {})
            checks = kwargs.get("checks")
            if not isinstance(checks, dict):
                kwargs["checks"] = post
            elif "repos" not in checks:
                kwargs["checks"] = {**post, **checks}
        return record_attempt(self.dir, **kwargs)


def make_lane(tmp: Path, lane_id: str = "L", max_rounds: int = 2, repos: dict | None = None, title: str = "Title") -> Lane:
    root = tmp / "lanes"
    root.mkdir(exist_ok=True)
    brief = tmp / f"brief-{lane_id}.md"
    brief.write_text(f"task {lane_id}\n")
    if repos is None:
        repos = {"repo": {"role": "change", "target_ref": "main", "target_sha": A}}
    cmd_new(root, lane_id, title=title, brief=str(brief), repos=repos, max_rounds=max_rounds)
    return Lane(root, lane_id, brief)


def implement_ok(lane: Lane, **override) -> dict:
    events = lane.events()
    rnd = current_round(events) or 1
    kind = start_kind(events, rnd)
    start = _expected_consumed(lane)
    fields = dict(
        step="implement",
        pinned=sha_set(B, TB),
        consumed=start,
        bundle_bytes={"repo": b"bundle"},
        notes=[],
        pre_checks=passing_prechecks("implement", start, kind=kind, expected=start),
    )
    fields.update(override)
    return lane.record(**fields)


def verify_ok(lane: Lane, **override) -> dict:
    fields = dict(step="verify", stdout=b"VERDICT: pass\n", consumed=sha_set(B, TB), checks={})
    fields.update(override)
    fields.setdefault("pre_checks", passing_prechecks("verify", fields["consumed"]))
    return lane.record(**fields)


def review_ok(lane: Lane, **override) -> dict:
    report = b"VERDICT: safe to merge\n\nnotes\n\nEND OF REPORT\n"
    fields = dict(step="review", report=report, consumed=sha_set(B, TB), checks={})
    fields.update(override)
    fields.setdefault("pre_checks", passing_prechecks("review", fields["consumed"]))
    return lane.record(**fields)
