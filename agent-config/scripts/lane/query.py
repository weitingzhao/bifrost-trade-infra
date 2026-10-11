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
