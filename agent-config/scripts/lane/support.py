"""Shared fixtures for lane round-1 tests. No absolute home paths."""

from __future__ import annotations

from pathlib import Path

from commands import cmd_new, cmd_status
from events import load_file
from query import created, current_round, expected_start
from recorder import record_attempt

A = "a" * 40
B = "b" * 40
C = "c" * 40
TA = "1" * 40
TB = "2" * 40
TC = "3" * 40


def sha_set(commit: str, tree: str, name: str = "repo") -> dict:
    return {name: {"commit": commit, "tree": tree}}


def passing_prechecks(step: str, found: dict) -> dict:
    repos = {}
    for name, info in (found or {}).items():
        repos[name] = {
            "commit": info.get("commit"),
            "tree": info.get("tree"),
            "clean": True,
            "hidden": False,
        }
    kind = "baseline" if step == "implement" else "invariance"
    return {"kind": kind, "ok": True, "repos": repos}


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
        # Tests stand in for the round-2 caller and supply a pre-check unless
        # they pass one themselves. The recorder stores an empty check when
        # the argument is omitted.
        if "pre_checks" not in kwargs:
            kwargs["pre_checks"] = passing_prechecks(kwargs.get("step") or "implement", kwargs.get("consumed") or {})
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
    start = _expected_consumed(lane)
    fields = dict(
        step="implement",
        pinned=sha_set(B, TB),
        consumed=start,
        bundle_bytes={"repo": b"bundle"},
        notes=[],
        pre_checks=passing_prechecks("implement", start),
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
