"""One strict fold of the event chain. It is the only source of the expected side.

Events are applied in order. Each one is checked against the state built so
far: the kind has to be legal in that state, every set it carries is a closed
record of exactly the lane's repositories, and a set the state already
determines has to equal that set. A mismatch, a repeat, an out-of-order
event, an unknown field or an invalid set stops the fold. Later events are
not applied, and nothing is filled in from the baseline or from a second copy.

Commit and tree move together. An unchanged commit with a changed tree is
not a transition the fold will accept. A changed commit with the same tree
is a legal pin only for a change repository: specification section 3, "通过绑定的是提交"
(amend, rebase or cherry-pick is a new commit even when the tree is the same).
A context repository that changes commit is left for the decision function,
which reports ``context repository <repo> moved``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from query import SHA_FIELDS, STEPS, close_set, same_set

# phase -> event kinds the fold will accept. Extra conditions are checked
# after the kind is in this set (the next step, a verdict already recorded).
TRANSITIONS = {
    "empty": frozenset({"lane_created"}),
    "created": frozenset({"round_opened", "tail_repaired", "abandoned"}),
    "ready": frozenset({"step_intent", "resolution", "tail_repaired", "abandoned", "execution_confirmed"}),
    "intent": frozenset({"step_started", "step_recorded", "resolution", "tail_repaired", "abandoned", "execution_confirmed"}),
    "started": frozenset({"step_recorded", "resolution", "tail_repaired", "abandoned", "execution_confirmed"}),
    "settled": frozenset({"step_intent", "verdict", "resolution", "tail_repaired", "abandoned", "execution_confirmed"}),
    "closed": frozenset({"round_opened", "resolution", "tail_repaired", "abandoned", "execution_confirmed"}),
    "abandoned": frozenset({"execution_confirmed", "tail_repaired"}),
}

_COMMON = frozenset({"type", "seq", "prev_sha256", "at"})
_FIELDS = {
    "lane_created": _COMMON | {
        "lane_id", "title", "max_rounds", "repos", "config_path", "config_sha256",
        "pinned_files", "brief_path", "brief_sha256", "brief_copy", "inputs", "created_at",
    },
    "round_opened": _COMMON | {"round", "brief_path", "brief_sha256", "brief_copy", "start", "start_set"},
    "step_intent": _COMMON | {"exec", "intent_sha256", "consumed"},
    "step_started": _COMMON | {"exec", "pid", "lstart", "started_at", "limit_seconds"},
    "step_recorded": _COMMON | {
        "exec", "manifest_sha256", "not_started", "exit", "consumed", "pinned", "bundles", "rejects", "sha_set",
    },
    "verdict": _COMMON | {"round", "result", "reason", "sha_set", "manifests"},
    "resolution": _COMMON | {"round", "step", "attempt_id", "kind", "operator", "reason", "evidence"},
    "tail_repaired": _COMMON | {"repair_id", "bytes", "sha256"},
    "abandoned": _COMMON | {"operator", "reason"},
    "execution_confirmed": _COMMON | {"attempt_id", "operator", "how"},
}
_EXEC_FIELDS = frozenset({"lane_id", "round", "step", "step_index", "attempt_id"})
_BASELINE_FIELDS = frozenset({"role", "target_ref", "target_sha", "tree"})
_BUNDLE_FIELDS = frozenset({"length", "sha256"})
_EXIT_FIELDS = frozenset({"code", "signal"})
_NOT_STARTED_FIELDS = frozenset({"check", "repo", "reason"})


@dataclass
class Folded:
    """Lane state after the valid prefix of the event chain."""

    baseline: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)
    rounds: dict = field(default_factory=dict)
    rejected: list = field(default_factory=list)
    resolutions: dict = field(default_factory=dict)
    verdicts: dict = field(default_factory=dict)
    last_pin: dict = field(default_factory=dict)
    pins_at: dict = field(default_factory=dict)
    defect: str | None = None
    defect_seq: int | None = None
    phase: str = "empty"
    opened: int = 0
    current_round: int | None = None
    open_step: str | None = None
    lane_id: str | None = None
    title: str = ""
    max_rounds: int = 2
    config_sha256: str | None = None

    def start_of(self, rnd: int) -> dict:
        row = self.rounds.get(int(rnd))
        if not row:
            return {}
        return row.get("start_set") or {}

    def start_kind_of(self, rnd: int) -> str:
        row = self.rounds.get(int(rnd)) or {}
        return row.get("start") or "baseline"

    def pin_before(self, rnd: int) -> dict:
        found: dict = {}
        for number in sorted(self.pins_at):
            if number < int(rnd) and self.pins_at[number]:
                found = self.pins_at[number]
        return found

    def required_start(self, rnd: int, start: str, targets: dict | None = None) -> dict:
        """The set ``round_opened.start_set`` must equal. No partial fill-in.

        Context repositories start at the target baseline (specification
        section 3). Change repositories start at the last complete pin, or at
        the baseline when nothing has been pinned or the round asks for it.
        """
        baseline = self.baseline or _baseline_from(targets)
        if int(rnd) <= 1 or start == "baseline" or not self.roles:
            return {name: dict(row) for name, row in baseline.items()}
        pin = self.pin_before(rnd)
        if not pin:
            return {name: dict(row) for name, row in baseline.items()}
        found = {}
        for name, role in self.roles.items():
            if role == "context":
                found[name] = dict(baseline[name])
            else:
                found[name] = dict(pin[name])
        return found

    def consumed_for(self, rnd: int, step: str) -> dict | None:
        """The set a step must consume: the start, then the pin once implement pins."""
        if step == "implement":
            found = self.start_of(rnd)
            return found or None
        pin = self.pins_at.get(int(rnd)) or {}
        return pin or None

    def resolutions_of(self, rnd: int) -> list:
        return list(self.resolutions.get(int(rnd)) or [])

    def verdict_of(self, rnd: int) -> dict | None:
        return self.verdicts.get(int(rnd))


def fold_events(events: list[dict] | None) -> Folded:
    """Fold ``events`` in order. The first defect freezes the state."""
    folded = Folded()
    for event in events or []:
        if folded.defect is not None:
            break
        if not isinstance(event, dict):
            folded.defect = "evidence invalid: event 0 unknown: not an object"
            break
        _apply(folded, event)
    return folded


def _apply(folded: Folded, event: dict) -> None:
    kind = event.get("type")
    if not isinstance(kind, str) or kind not in _FIELDS:
        _bad(folded, event, "unknown kind" if kind else "missing kind")
        return
    unknown = sorted(set(event) - _FIELDS[kind])
    if unknown:
        _bad(folded, event, f"{unknown[0]} unknown")
        return
    why = _order(folded, event, kind)
    if why:
        _bad(folded, event, why)
        return
    if kind not in TRANSITIONS[folded.phase]:
        _bad(folded, event, f"{kind} is not allowed")
        return
    handler = _HANDLERS[kind]
    why = handler(folded, event)
    if why:
        _bad(folded, event, why)


def _bad(folded: Folded, event: dict, why: str) -> None:
    seq = event.get("seq")
    number = seq if isinstance(seq, int) else 0
    kind = event.get("type") if isinstance(event.get("type"), str) else "unknown"
    folded.defect = f"evidence invalid: event {number} {kind}: {why}"
    folded.defect_seq = number


def _order(folded: Folded, event: dict, kind: str) -> str | None:
    """Repeats and impossible steps, named before the generic transition."""
    if kind == "round_opened":
        rnd = event.get("round")
        if isinstance(rnd, int) and rnd in folded.rounds:
            return f"duplicate round_opened for round {rnd}"
        return None
    if kind not in ("step_intent", "step_started", "step_recorded"):
        return None
    body = event.get("exec")
    if not isinstance(body, dict):
        return "exec missing"
    step = body.get("step")
    rnd = body.get("round")
    if step not in STEPS:
        return f"{step} is not a step"
    if not isinstance(rnd, int) or rnd != folded.current_round:
        return f"{step} is outside the open round"
    row = folded.rounds.get(rnd) or {}
    steps = row.get("steps") or {}
    have = steps.get(step) or {}
    if kind == "step_intent" and have.get("intent"):
        return f"duplicate attempt for {step}"
    if kind == "step_recorded" and have.get("recorded"):
        return f"duplicate attempt for {step}"
    if kind == "step_recorded" and not have.get("intent"):
        return f"{step} recorded without a matching intent"
    if kind == "step_started" and not have.get("intent"):
        return f"{step} started without a matching intent"
    if kind == "step_started" and have.get("started"):
        return f"duplicate attempt for {step}"
    if kind == "step_intent":
        nxt = _next_step(steps)
        if step != nxt:
            previous = STEPS[STEPS.index(step) - 1] if step != "implement" else None
            if previous:
                return f"{step} before {previous}"
            return f"{step} is out of order"
    return None


def _next_step(steps: dict) -> str | None:
    for name in STEPS:
        if not (steps.get(name) or {}).get("recorded"):
            return name
    return None


def _on_created(folded: Folded, event: dict) -> str | None:
    repos = event.get("repos")
    closed, roles, why = _close_baseline(repos)
    if why:
        return f"baseline {why}"
    folded.baseline = closed
    folded.roles = roles
    folded.targets = repos
    folded.lane_id = event.get("lane_id")
    folded.title = event.get("title") or ""
    folded.max_rounds = event.get("max_rounds") if isinstance(event.get("max_rounds"), int) else 2
    folded.config_sha256 = event.get("config_sha256")
    folded.phase = "created"
    return None


def _on_opened(folded: Folded, event: dict) -> str | None:
    rnd = event.get("round")
    if not isinstance(rnd, int) or rnd != folded.opened + 1:
        return "round is out of order"
    if rnd > 1 and folded.current_round not in folded.verdicts:
        return "previous round has no verdict"
    mode = event.get("start")
    if mode not in ("baseline", "pinned"):
        return "start is not baseline or pinned"
    if rnd == 1 and mode != "baseline":
        return "round 1 does not start at the baseline"
    required = folded.required_start(rnd, mode)
    why = _closed_equal(event.get("start_set"), required, folded.roles, "start_set", transition=False)
    if why:
        return why
    folded.rounds[rnd] = {"start": mode, "start_set": _copy_set(required), "steps": {}}
    folded.opened = rnd
    folded.current_round = rnd
    folded.open_step = None
    folded.phase = "ready"
    return None


def _on_intent(folded: Folded, event: dict) -> str | None:
    body = event["exec"]
    why = _exec_ok(body)
    if why:
        return why
    step = body["step"]
    required = folded.consumed_for(folded.current_round, step)
    if not required:
        return "consumed has no current set"
    why = _closed_equal(event.get("consumed"), required, folded.roles, "consumed", transition=False)
    if why:
        return why
    _step(folded, step)["intent"] = body.get("attempt_id")
    _step(folded, step)["consumed"] = _copy_set(required)
    folded.open_step = step
    folded.phase = "intent"
    return None


def _on_started(folded: Folded, event: dict) -> str | None:
    body = event["exec"]
    why = _exec_ok(body)
    if why:
        return why
    step = body["step"]
    if _step(folded, step).get("intent") != body.get("attempt_id"):
        return f"{step} started without a matching intent"
    _step(folded, step)["started"] = body.get("attempt_id")
    folded.phase = "started"
    return None


def _on_recorded(folded: Folded, event: dict) -> str | None:
    body = event["exec"]
    why = _exec_ok(body)
    if why:
        return why
    step = body["step"]
    slot = _step(folded, step)
    if slot.get("intent") != body.get("attempt_id"):
        return f"{step} recorded without a matching intent"
    if "not_started" not in event:
        return "not_started missing"
    not_started = event.get("not_started")
    if not_started is None and not slot.get("started"):
        return f"{step} recorded without step_started"
    if not_started is None and not isinstance(event.get("exit"), dict):
        return "exit missing"
    if step == "review" and not isinstance(event.get("rejects"), bool):
        return "rejects is not a bool"
    required = slot.get("consumed") or folded.consumed_for(folded.current_round, step)
    if not required:
        return "consumed has no current set"
    why = _closed_equal(event.get("consumed"), required, folded.roles, "consumed", transition=False)
    if why:
        return why
    if step == "implement":
        why = _accept_pin(folded, event, required)
        if why:
            return why
    if step == "review":
        why = _accept_review_set(folded, event, required)
        if why:
            return why
    exit_body = event.get("exit")
    if exit_body is not None:
        why = _known(exit_body, _EXIT_FIELDS, "exit")
        if why:
            return why
    not_started = event.get("not_started")
    if not_started is not None:
        why = _known(not_started, _NOT_STARTED_FIELDS, "not_started")
        if why:
            return why
    slot["recorded"] = body.get("attempt_id")
    slot["manifest_sha256"] = event.get("manifest_sha256")
    folded.open_step = None
    folded.phase = "settled"
    return None


def _on_verdict(folded: Folded, event: dict) -> str | None:
    rnd = event.get("round")
    if rnd != folded.current_round:
        return "verdict is outside the open round"
    if rnd in folded.verdicts:
        return "duplicate verdict"
    if folded.open_step is not None:
        return "verdict while a step is open"
    pin = folded.pins_at.get(rnd) or {}
    carried = event.get("sha_set")
    if pin:
        why = _closed_equal(carried, pin, folded.roles, "sha_set", transition=False)
        if why:
            return why
    elif carried not in ({}, None):
        closed, detail = close_set(carried, folded.roles, SHA_FIELDS)
        if detail:
            return f"sha_set {detail}"
        return "sha_set does not equal the current set"
    why = _manifests_match(folded, event, rnd)
    if why:
        return why
    folded.verdicts[rnd] = event
    folded.phase = "closed"
    return None


def _manifests_match(folded: Folded, event: dict, rnd: int) -> str | None:
    """The verdict's manifest map is the hashes the round actually recorded."""
    manifests = event.get("manifests")
    if not isinstance(manifests, dict):
        return "manifests missing"
    steps = (folded.rounds.get(rnd) or {}).get("steps") or {}
    recorded = {
        name: slot.get("manifest_sha256")
        for name, slot in steps.items()
        if slot.get("recorded")
    }
    if manifests != recorded:
        return "manifests do not match the recorded attempts"
    return None


def _on_resolution(folded: Folded, event: dict) -> str | None:
    rnd = event.get("round")
    if rnd != folded.current_round:
        return "resolution is outside the open round"
    kind = event.get("kind")
    if kind not in ("failed", "cancelled", "evidence-lost", "still-unknown"):
        return "resolution kind is unknown"
    folded.resolutions.setdefault(rnd, []).append(
        {
            "step": event.get("step"),
            "kind": kind,
            "operator": event.get("operator"),
            "reason": event.get("reason"),
            "attempt_id": event.get("attempt_id"),
        }
    )
    if kind in ("failed", "cancelled", "evidence-lost"):
        folded.open_step = None
        folded.phase = "settled"
    return None


def _on_note(folded: Folded, event: dict) -> str | None:
    return None


def _accept_pin(folded: Folded, event: dict, required: dict) -> str | None:
    raw = event.get("pinned")
    if raw == {}:
        # Pinned nothing. Do not erase the previous complete pin.
        bundles = event.get("bundles")
        if bundles not in ({}, None):
            return "bundles without a pin"
        return None
    why = _closed_equal(raw, None, folded.roles, "pinned", transition=True, before=required)
    if why:
        return why
    bundles = event.get("bundles")
    if bundles is None:
        bundles = {}
    if not isinstance(bundles, dict):
        return "bundles type"
    for name, info in bundles.items():
        if name not in folded.roles:
            return f"bundles extra repo {name}"
        why = _known(info, _BUNDLE_FIELDS, f"bundles.{name}")
        if why:
            return why
    for name, role in folded.roles.items():
        if role != "change":
            continue
        if required and raw[name]["commit"] == required[name]["commit"]:
            continue
        if name not in bundles:
            return f"bundles missing {name}"
    closed, _detail = close_set(raw, folded.roles, SHA_FIELDS)
    folded.pins_at[folded.current_round] = closed
    folded.last_pin = closed
    return None


def _accept_review_set(folded: Folded, event: dict, required: dict) -> str | None:
    """A review's sha set is the set it consumed. An incomplete one is not skipped."""
    raw = event.get("sha_set")
    why = _closed_equal(raw, required, folded.roles, "sha_set", transition=False)
    if why:
        return why
    if event.get("rejects") is True:
        closed, _detail = close_set(raw, folded.roles, SHA_FIELDS)
        folded.rejected.append({"round": folded.current_round, "sha_set": closed})
    return None


def _closed_equal(raw, required, roles, label: str, *, transition: bool, before: dict | None = None) -> str | None:
    closed, detail = close_set(raw, roles, SHA_FIELDS)
    if detail:
        return f"{label} {detail}"
    if transition:
        why = _transition(before, closed, roles)
        if why:
            return f"{label} {why}"
        return None
    if required is not None and not same_set(closed, required):
        return f"{label} does not equal the current set"
    return None


def _transition(before: dict | None, after: dict, roles: dict) -> str | None:
    """Same commit must keep its tree. A new commit may keep the tree only for a change repo.

    Specification section 3 binds a pass to the commit: amend, rebase and
    cherry-pick are new commits when the tree does not change. That is the
    only transition where a changed commit and an unchanged tree are valid,
    and only on a change repository's pin. A context repository's new commit
    is not invalid evidence; the decision function reports that it moved.
    """
    if not before:
        return None
    for name in before:
        old = before[name]
        new = after[name]
        same_commit = old.get("commit") == new.get("commit")
        same_tree = old.get("tree") == new.get("tree")
        if same_commit and not same_tree:
            return f"{name} commit unchanged but tree changed"
        if not same_commit and same_tree and roles.get(name) != "change":
            # Context: not rejected here. Section 3's table says the repository moved.
            continue
    return None


def _close_baseline(repos):
    if not isinstance(repos, dict) or len(repos) == 0:
        return None, None, "missing"
    closed = {}
    roles = {}
    for name in repos:
        meta = repos[name]
        if not isinstance(meta, dict):
            return None, None, f"{name} type"
        unknown = sorted(set(meta) - _BASELINE_FIELDS)
        if unknown:
            return None, None, f"{name}.{unknown[0]} unknown"
        for key in ("role", "target_ref", "target_sha", "tree"):
            if key not in meta or meta[key] is None or meta[key] == "":
                leaf = "missing" if key not in meta else "type"
                return None, None, f"{name}.{key} {leaf}"
        if meta["role"] not in ("change", "context"):
            return None, None, f"{name}.role type"
        if not isinstance(meta["target_sha"], str) or not isinstance(meta["tree"], str):
            return None, None, f"{name}.target_sha type"
        if not isinstance(meta["target_ref"], str):
            return None, None, f"{name}.target_ref type"
        closed[name] = {"commit": meta["target_sha"], "tree": meta["tree"]}
        roles[name] = meta["role"]
    return closed, roles, None


def _baseline_from(targets: dict | None) -> dict:
    found = {}
    for name, meta in (targets or {}).items():
        meta = meta if isinstance(meta, dict) else {}
        found[name] = {"commit": meta.get("target_sha"), "tree": meta.get("tree")}
    return found


def _exec_ok(body: dict) -> str | None:
    unknown = sorted(set(body) - _EXEC_FIELDS)
    if unknown:
        return f"exec.{unknown[0]} unknown"
    step = body.get("step")
    if step not in STEPS:
        return "exec.step type"
    if body.get("step_index") != STEPS.index(step):
        return "exec.step_index does not match"
    return None


def _known(value, allowed: frozenset, label: str) -> str | None:
    if not isinstance(value, dict):
        return f"{label} type"
    unknown = sorted(set(value) - allowed)
    if unknown:
        return f"{label}.{unknown[0]} unknown"
    return None


def _step(folded: Folded, step: str) -> dict:
    steps = folded.rounds[folded.current_round]["steps"]
    steps.setdefault(step, {})
    return steps[step]


def _copy_set(raw: dict) -> dict:
    return {name: {"commit": row["commit"], "tree": row["tree"]} for name, row in raw.items()}


_HANDLERS = {
    "lane_created": _on_created,
    "round_opened": _on_opened,
    "step_intent": _on_intent,
    "step_started": _on_started,
    "step_recorded": _on_recorded,
    "verdict": _on_verdict,
    "resolution": _on_resolution,
    "tail_repaired": _on_note,
    "abandoned": _on_note,
    "execution_confirmed": _on_note,
}
