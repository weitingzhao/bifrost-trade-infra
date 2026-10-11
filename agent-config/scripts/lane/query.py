"""Pure queries over an already-parsed event list."""

from __future__ import annotations

STEPS = ("implement", "verify", "review")
STEP_INDEX = {name: index for index, name in enumerate(STEPS)}
CLOSING_KINDS = ("failed", "cancelled", "evidence-lost")
NEGATIVE = ("verify_failed", "changes_requested", "step_failed")
IN_PROGRESS = ("implementing", "verifying", "reviewing")
PROGRESS_NAME = {"implement": "implementing", "verify": "verifying", "review": "reviewing"}


def by_type(events: list[dict], kind: str) -> list[dict]:
    return [event for event in events if event.get("type") == kind]


def created(events: list[dict]) -> dict | None:
    found = by_type(events, "lane_created")
    return found[0] if found else None


def round_events(events: list[dict]) -> list[dict]:
    return by_type(events, "round_opened")


def opened_count(events: list[dict]) -> int:
    return len(round_events(events))


def current_round(events: list[dict]) -> int | None:
    opened = round_events(events)
    if not opened:
        return None
    return int(opened[-1]["round"])


def max_rounds(events: list[dict]) -> int:
    info = created(events)
    if not info:
        return 2
    return int(info.get("max_rounds", 2))


def verdict_event(events: list[dict], rnd: int) -> dict | None:
    found = [event for event in by_type(events, "verdict") if int(event.get("round", -1)) == rnd]
    return found[-1] if found else None


def resolutions(events: list[dict], rnd: int | None = None) -> list[dict]:
    rows = by_type(events, "resolution")
    if rnd is None:
        return rows
    return [row for row in rows if int(row.get("round", -1)) == rnd]


def closing_resolutions(events: list[dict], rnd: int) -> list[dict]:
    return [row for row in resolutions(events, rnd) if row.get("kind") in CLOSING_KINDS]


def confirmed_ids(events: list[dict]) -> set[str]:
    return {event["attempt_id"] for event in by_type(events, "execution_confirmed") if event.get("attempt_id")}


def abandoned_event(events: list[dict]) -> dict | None:
    found = by_type(events, "abandoned")
    return found[-1] if found else None


def exec_of(event: dict) -> dict:
    return event.get("exec") or {}


def events_for_step(events: list[dict], rnd: int, step: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {name: [] for name in ("step_intent", "step_started", "step_recorded")}
    for event in events:
        if event.get("type") not in groups:
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) == rnd and body.get("step") == step:
            groups[event["type"]].append(event)
    return groups


def rejected_sets(events: list[dict]) -> list[dict]:
    found = []
    for event in by_type(events, "step_recorded"):
        if event.get("rejects") is True:
            found.append({"round": int(exec_of(event).get("round", 0)), "sha_set": event.get("sha_set") or {}})
    return found


def repair_ids(events: list[dict]) -> set[str]:
    return {event["repair_id"] for event in by_type(events, "tail_repaired") if event.get("repair_id")}


def same_set(left: dict | None, right: dict | None) -> bool:
    if not left or not right:
        return False
    if set(left) != set(right):
        return False
    for name in left:
        a = left[name] or {}
        b = right[name] or {}
        if a.get("commit") != b.get("commit") or a.get("tree") != b.get("tree"):
            return False
    return True


def short_set(sha_set: dict | None) -> str:
    if not sha_set:
        return ""
    parts = []
    for name in sorted(sha_set):
        commit = str((sha_set[name] or {}).get("commit") or "")
        parts.append(f"{name}:{commit[:12]}")
    return ",".join(parts)


def make_exec(lane_id: str, rnd: int, step: str, attempt_id: str) -> dict:
    return {
        "lane_id": lane_id,
        "round": rnd,
        "step": step,
        "step_index": STEP_INDEX[step],
        "attempt_id": attempt_id,
    }


def may_open_round(opened: int, budget: int, extensions: int = 0) -> bool:
    """The only budget check. ``new`` and ``next-round`` both call it."""
    return int(opened) < int(budget) + int(extensions)


def round_open(events: list[dict], rnd: int) -> dict | None:
    rows = [event for event in round_events(events) if int(event.get("round", -1)) == rnd]
    return rows[-1] if rows else None


def _nonempty_pin(pinned: object) -> bool:
    """A pin counts only when some repository has a commit. An empty set does not."""
    if not isinstance(pinned, dict):
        return False
    for info in pinned.values():
        if isinstance(info, dict) and isinstance(info.get("commit"), str) and info.get("commit"):
            return True
    return False


def last_pinned_before(events: list[dict], rnd: int) -> dict:
    """The newest implement pin before ``rnd`` that actually pinned something.

    A later round whose implement recorded an empty pin (it did not start, or
    it failed before pinning) must not erase the previous set.
    """
    found: dict = {}
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        body = exec_of(event)
        if body.get("step") != "implement":
            continue
        if int(body.get("round", -1)) < rnd and _nonempty_pin(event.get("pinned")):
            found = event["pinned"]
    return found


def start_kind(events: list[dict], rnd: int) -> str:
    """``baseline`` on round 1 and on ``--start baseline``; otherwise ``pinned``."""
    opened = round_open(events, rnd) or {}
    if int(rnd) <= 1 or opened.get("start") == "baseline":
        return "baseline"
    return "pinned"


def expected_start(events: list[dict], rnd: int, targets: dict | None) -> dict:
    """Where implement must have started, from the round and the last pinned set.

    Round 1, and any round opened with ``start=baseline``, starts at the target
    baseline. Later rounds start change repositories at the most recent
    non-empty pinned set and context repositories at the target baseline.
    An empty pin does not count. The manifest being judged is not an input.
    """
    baseline = {}
    for name, meta in (targets or {}).items():
        baseline[name] = {"commit": meta.get("target_sha"), "tree": meta.get("tree")}
    opened = round_open(events, rnd) or {}
    if int(rnd) <= 1 or opened.get("start") == "baseline":
        return baseline
    pinned = last_pinned_before(events, rnd)
    start = {}
    for name, meta in (targets or {}).items():
        if meta.get("role") == "context" or not pinned.get(name):
            start[name] = dict(baseline[name])
            continue
        prev = pinned[name] or {}
        start[name] = {"commit": prev.get("commit"), "tree": prev.get("tree")}
    return start


def round_defect(events: list[dict], rnd: int) -> str | None:
    """Duplicate or out-of-order step events make the round's evidence invalid.

    The reader does not keep the first record or the last one.
    """
    groups: dict[str, dict[str, list[dict]]] = {
        step: {"step_intent": [], "step_recorded": [], "step_started": []} for step in STEPS
    }
    sequence: list[dict] = []
    for event in events:
        kind = event.get("type")
        if kind not in ("step_intent", "step_started", "step_recorded"):
            continue
        body = exec_of(event)
        if int(body.get("round", -1)) != rnd:
            continue
        step = body.get("step")
        if step not in groups:
            return f"events out of order: {step}"
        groups[step][kind].append(event)
        sequence.append(event)
    for step in STEPS:
        if len(groups[step]["step_intent"]) > 1 or len(groups[step]["step_recorded"]) > 1:
            return f"evidence invalid: duplicate attempt for {step}"
    intent_ids: dict[str, str] = {}
    recorded: set[str] = set()
    for event in sequence:
        body = exec_of(event)
        step = body.get("step")
        attempt = body.get("attempt_id")
        kind = event.get("type")
        previous = STEPS[STEPS.index(step) - 1] if step != "implement" else None
        if kind == "step_intent":
            if previous and previous not in recorded:
                return f"events out of order: {step} before {previous}"
            intent_ids[step] = attempt
            continue
        if intent_ids.get(step) != attempt:
            verb = "recorded" if kind == "step_recorded" else "started"
            return f"events out of order: {step} {verb} without a matching intent"
        if previous and previous not in recorded:
            return f"events out of order: {step} before {previous}"
        if kind == "step_recorded":
            recorded.add(step)
    return None
