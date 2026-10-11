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


# Closed repository record. Checks add clean and hidden; a SHA set is commit and tree only.
SHA_FIELDS = (("commit", str), ("tree", str))
CHECK_FIELDS = (("commit", str), ("tree", str), ("clean", bool), ("hidden", bool))
_SET_FIELDS = ("start_set", "consumed", "pinned", "sha_set")


def set_delta(expected, actual) -> str | None:
    """The one comparison of two repository records.

    ``None`` means equal. Otherwise the first difference: ``shape``, ``commit``,
    ``tree``, ``clean`` or ``hidden``. Callers use :func:`same_set` for the
    boolean and this function only to name a difference that already failed it.
    """
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return "shape"
    if len(expected) == 0 or len(actual) == 0:
        return "shape"
    if set(expected) != set(actual):
        return "shape"
    for name in expected:
        exp = expected[name]
        act = actual[name]
        if not isinstance(exp, dict) or not isinstance(act, dict):
            return "shape"
        if exp.get("commit") != act.get("commit"):
            return "commit"
        if exp.get("tree") != act.get("tree"):
            return "tree"
        if "clean" in exp or "clean" in act:
            if exp.get("clean") != act.get("clean"):
                return "clean"
        if "hidden" in exp or "hidden" in act:
            if exp.get("hidden") != act.get("hidden"):
                return "hidden"
    return None


def same_set(expected: dict | None, actual: dict | None) -> bool:
    """Equality of two validated closed records. An empty record is not a set."""
    return set_delta(expected, actual) is None


def _field_ok(value: object, typ: type) -> bool:
    if typ is str:
        return isinstance(value, str) and bool(value)
    if typ is bool:
        return isinstance(value, bool)
    return False


def close_set(raw: object, names, fields: tuple) -> tuple[dict | None, str | None]:
    """Validate ``raw`` into one closed record per repository.

    Returns ``(record, None)`` or ``(None, detail)``. A missing repository, an
    extra repository, an unknown field, a missing field, or ``None`` is invalid.
    Duplicate names cannot appear in a dict; parsers must refuse them first.
    """
    if not isinstance(raw, dict):
        return None, "missing"
    wanted = set(names)
    missing = sorted(wanted - set(raw))
    extra = sorted(set(raw) - wanted)
    if missing:
        return None, f"missing repo {missing[0]}"
    if extra:
        return None, f"extra repo {extra[0]}"
    allowed = {name for name, _typ in fields}
    closed: dict = {}
    for repo in sorted(wanted):
        info = raw[repo]
        if not isinstance(info, dict):
            return None, f"{repo} type"
        unknown = sorted(set(info) - allowed)
        if unknown:
            return None, f"{repo}.{unknown[0]} unknown"
        row = {}
        for name, typ in fields:
            if name not in info or info[name] is None:
                leaf = "missing" if name not in info else "type"
                return None, f"{repo}.{name} {leaf}"
            if not _field_ok(info[name], typ):
                return None, f"{repo}.{name} type"
            row[name] = info[name]
        closed[repo] = row
    return closed, None


def _repo_tree_missing(info: object) -> bool:
    if not isinstance(info, dict):
        return False
    if "commit" not in info and "target_sha" not in info and "tree" not in info:
        return False
    tree = info.get("tree")
    return not isinstance(tree, str) or not tree


def set_missing_trees(value: object) -> bool:
    """True when a carried set has a repository record and that record has no tree."""
    if not isinstance(value, dict) or not value:
        return False
    return any(_repo_tree_missing(info) for info in value.values())


def expected_incomplete(events: list[dict]) -> str | None:
    """An event that carries a set without trees is invalid when read.

    The message names the set. An empty set pinned nothing and is not this defect.
    """
    info = created(events) or {}
    if set_missing_trees(info.get("repos")):
        return "evidence invalid: expected baseline incomplete in events"
    for event in events:
        for field in _SET_FIELDS:
            if field in event and set_missing_trees(event.get(field)):
                what = "start" if field == "start_set" else field
                return f"evidence invalid: expected {what} incomplete in events"
    return None


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


def last_pinned_before(events: list[dict], rnd: int) -> dict:
    """The last complete pin accepted before ``rnd``. An empty pin does not count.

    A partial pin is not stored and is not filled in here.
    """
    from fold import fold_events

    return fold_events(events).pin_before(int(rnd))


def start_kind(events: list[dict], rnd: int) -> str:
    """``baseline`` on round 1 and on ``--start baseline``; otherwise ``pinned``."""
    opened = round_open(events, rnd) or {}
    if int(rnd) <= 1 or opened.get("start") == "baseline":
        return "baseline"
    return "pinned"


def baseline_set(targets: dict | None) -> dict:
    """Target baseline as a SHA set. Missing trees stay missing so the reader can reject them."""
    found = {}
    for name, meta in (targets or {}).items():
        meta = meta if isinstance(meta, dict) else {}
        found[name] = {"commit": meta.get("target_sha"), "tree": meta.get("tree")}
    return found


def resolve_start_set(events: list[dict], rnd: int, targets: dict | None, start: str) -> dict:
    """The start set ``round_opened`` must carry. Delegates to the fold.

    Nothing is filled in from a later event or from a partial pin. Context
    repositories stay on the target baseline (specification section 3);
    change repositories take the last complete pin. An empty pin does not
    replace that pin. With no pin yet, the start is the baseline.
    """
    from fold import fold_events

    return fold_events(events).required_start(int(rnd), start, targets)


def expected_start(events: list[dict], rnd: int, targets: dict | None) -> dict:
    """Where implement must have started, from the fold. Not from a raw event."""
    from fold import fold_events

    folded = fold_events(events)
    found = folded.start_of(int(rnd))
    if found:
        return found
    return folded.required_start(int(rnd), "baseline" if int(rnd) <= 1 else "pinned", targets)


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
