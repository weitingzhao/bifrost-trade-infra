"""Shared fixtures for lane round-1 tests. No absolute home paths."""

from __future__ import annotations

from pathlib import Path

from commands import cmd_new, cmd_status
from events import load_file
from recorder import record_attempt

A = "a" * 40
B = "b" * 40
C = "c" * 40
TA = "1" * 40
TB = "2" * 40
TC = "3" * 40


def sha_set(commit: str, tree: str, name: str = "repo") -> dict:
    return {name: {"commit": commit, "tree": tree}}


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
    fields = dict(
        step="implement",
        pinned=sha_set(B, TB),
        consumed=sha_set(A, TA),
        bundle_bytes={"repo": b"bundle"},
        notes=[],
    )
    fields.update(override)
    return lane.record(**fields)


def verify_ok(lane: Lane, **override) -> dict:
    fields = dict(step="verify", stdout=b"VERDICT: pass\n", consumed=sha_set(B, TB), checks={})
    fields.update(override)
    return lane.record(**fields)


def review_ok(lane: Lane, **override) -> dict:
    report = b"VERDICT: safe to merge\n\nnotes\n\nEND OF REPORT\n"
    fields = dict(step="review", report=report, consumed=sha_set(B, TB), checks={})
    fields.update(override)
    return lane.record(**fields)
