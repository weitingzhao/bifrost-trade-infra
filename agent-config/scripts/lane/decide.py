"""Pure decision function. No I/O, no child process, no clock.

Before the per-step walk (section 4):

1. A closing resolution (``failed``, ``cancelled``, ``evidence-lost``) fixes
   the round as ``step_failed``. ``still-unknown`` is a note and is ignored.
2. A duplicate attempt, or step events out of order, makes the round
   ``unknown``. The first record and the last record are both ignored.
A recorded rejection does not short-circuit: a complete manifest is walked,
so an execution failure outranks verdict text. Lost review evidence uses row 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from query import CLOSING_KINDS, SHA_FIELDS, STEPS, close_set, same_set, set_delta, short_set

VERDICT_FAIL = "VERDICT: FAIL"
VERDICT_PASS = "VERDICT: pass"
VERDICT_FIX = "VERDICT: fix first"
VERDICT_SAFE = "VERDICT: safe to merge"
END_MARK = "END OF REPORT"
KIND_VALUES = ("baseline", "pinned")

# Closed pre-check, one entry per repository. Tests generate T31 from these.
# ``kind`` is the string "kind" so it is not the same check as a plain str.
PRE_FIELDS = {
    "implement": (
        ("commit", str),
        ("tree", str),
        ("clean", bool),
        ("hidden", bool),
        ("kind", "kind"),
        ("expected.commit", str),
        ("expected.tree", str),
    ),
    "verify": (
        ("commit", str),
        ("tree", str),
        ("clean", bool),
        ("hidden", bool),
        ("consumed.commit", str),
        ("consumed.tree", str),
    ),
    "review": (
        ("commit", str),
        ("tree", str),
        ("clean", bool),
        ("hidden", bool),
        ("consumed.commit", str),
        ("consumed.tree", str),
    ),
}
POST_FIELDS = {"verify": PRE_FIELDS["verify"], "review": PRE_FIELDS["review"]}
PIN_FIELDS = (("commit", str), ("tree", str))
_MISSING = object()


@dataclass(frozen=True)
class StepView:
    name: str
    presence: str = "missing"
    started: bool = False
    invalid_which: str | None = None
    not_started: dict | None = None
    exit: dict | None = None
    termination: str | None = None
    checks: dict | None = None
    fields: dict | None = None
    pinned: dict | None = None
    bundles: dict | None = None
    consumed: dict | None = None
    notes: tuple = ()
    rejects: bool = False
    report: dict | None = None
    pre_checks: dict | None = None


@dataclass(frozen=True)
class RoundEvidence:
    round_no: int
    steps: dict
    targets: dict = field(default_factory=dict)
    rejected: tuple = ()
    resolutions: tuple = ()
    expected_start: dict = field(default_factory=dict)
    order_defect: str | None = None
    start_kind: str = "baseline"
    expected_defect: str | None = None
    fold_defect: str | None = None


def decide(evidence: RoundEvidence) -> tuple[str, str | None]:
    closing = [row for row in evidence.resolutions if row.get("kind") in CLOSING_KINDS]
    if closing:
        row = closing[0]
        return "step_failed", f"{row['step']} closed as {row['kind']} by {row['operator']}: {row['reason']}"
    if evidence.fold_defect is not None:
        return "unknown", evidence.fold_defect
    if evidence.order_defect is not None:
        return "unknown", evidence.order_defect
    gap = _expected_gap(evidence)
    if gap is not None:
        return gap
    saw_review = False
    for name in STEPS:
        step = evidence.steps[name]
        if step.presence == "missing":
            return "continue", None
        hit = _eval_step(evidence, step)
        if hit is not None:
            return hit
        if name == "review":
            saw_review = True
    if saw_review:
        pinned = evidence.steps["implement"].pinned or {}
        return "passed", f"round {evidence.round_no} passed for {short_set(pinned)}"
    return "continue", None


def _eval_step(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    if step.presence == "absent":
        if not step.started:
            return "start_ambiguous", "started or not is unknown; no pid recorded"
        return "unknown", f"{step.name} result is unknown"
    if step.name == "review" and step.rejects and step.presence == "invalid":
        return "changes_requested", "fix first (recorded in the event; evidence lost)"
    if step.presence == "invalid":
        return "unknown", f"evidence invalid: {step.name} {step.invalid_which}"
    if step.presence == "not_started":
        reason = (step.not_started or {}).get("reason") or ""
        return "step_failed", f"{step.name} did not start: {reason}"
    if step.termination != "exited":
        word = step.termination if step.termination in ("timed_out", "cancelled") else step.termination
        return "step_failed", f"{step.name} {word} by the executor"
    signal = (step.exit or {}).get("signal")
    if signal is not None:
        return "step_failed", f"{step.name} ended by signal {signal}"
    code = (step.exit or {}).get("code")
    if step.name in ("implement", "review") and code != 0:
        return "step_failed", f"{step.name} exited {code}"
    if step.name == "verify" and code not in (0, 1):
        return "step_failed", f"verify exited {code}"
    hit = _precheck(evidence, step)
    if hit is not None:
        return hit
    if step.name in ("verify", "review"):
        hit = _invariance(evidence, step)
        if hit is not None:
            return hit
    if step.name == "implement":
        hit = _pin(evidence, step)
        if hit is not None:
            return hit
    if step.name == "verify":
        return _verify_text(step, code)
    if step.name == "review":
        return _review_text(step)
    return None


def _expected_gap(evidence: RoundEvidence) -> tuple[str, str] | None:
    """The expected side is a closed record, or the round's evidence is invalid."""
    if evidence.expected_defect is not None:
        return "unknown", evidence.expected_defect
    if not evidence.targets:
        return None
    closed, _detail = close_set(evidence.expected_start, evidence.targets, SHA_FIELDS)
    if closed is None:
        return "unknown", "evidence invalid: expected start incomplete in events"
    return None


def _invalid(step: str, kind: str, detail: str) -> tuple[str, str]:
    return "unknown", f"evidence invalid: {step} {kind} {detail}"


def _dig(obj: object, path: str):
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _typed(value: object, typ: object) -> bool:
    if typ == "kind":
        return isinstance(value, str) and value in KIND_VALUES
    if typ is str:
        return isinstance(value, str) and bool(value)
    if typ is bool:
        return isinstance(value, bool)
    return False


def _allowed(fields: tuple) -> tuple[set, dict]:
    allowed: set[str] = set()
    nested: dict[str, list] = {}
    for path, typ in fields:
        head, _, tail = path.partition(".")
        allowed.add(head)
        if tail:
            nested.setdefault(head, []).append((tail, typ))
    return allowed, nested


def _closed_detail(repos: object, fields: tuple, targets: dict) -> str | None:
    """First shape defect, or None when ``repos`` is exactly ``targets`` and every field is typed.

    Unknown fields are invalid. ``None`` is invalid.
    """
    if not isinstance(repos, dict):
        return "repos"
    missing = sorted(set(targets) - set(repos))
    extra = sorted(set(repos) - set(targets))
    if missing:
        return f"missing repo {missing[0]}"
    if extra:
        return f"extra repo {extra[0]}"
    allowed, nested = _allowed(fields)
    for repo in sorted(targets):
        info = repos[repo]
        if not isinstance(info, dict):
            return f"{repo} type"
        for path, typ in fields:
            value = _dig(info, path)
            if value is _MISSING or value is None:
                leaf = "missing" if value is _MISSING else "type"
                return f"{repo}.{path} {leaf}"
            if not _typed(value, typ):
                return f"{repo}.{path} type"
        unknown = sorted(set(info) - allowed)
        if unknown:
            return f"{repo}.{unknown[0]} unknown"
        for key, spec in nested.items():
            inner = info.get(key)
            if not isinstance(inner, dict):
                continue
            extra_fields = sorted(set(inner) - {name for name, _typ in spec})
            if extra_fields:
                return f"{repo}.{key}.{extra_fields[0]} unknown"
    return None


def _consumed_shape(step: StepView, targets: dict) -> tuple[str, str] | None:
    consumed = step.consumed
    if not isinstance(consumed, dict) or not consumed:
        return _invalid(step.name, "pre-check", "consumed")
    detail = _closed_detail(consumed, PIN_FIELDS, targets)
    if detail is None:
        return None
    if detail.startswith("missing repo") or detail.startswith("extra repo"):
        return _invalid(step.name, "pre-check", f"consumed {detail}")
    return _invalid(step.name, "pre-check", f"consumed.{detail}")


def _precheck(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    pre = step.pre_checks
    if not isinstance(pre, dict) or not pre:
        return _invalid(step.name, "pre-check", "missing")
    detail = _closed_detail(pre.get("repos"), PRE_FIELDS[step.name], evidence.targets)
    if detail is not None:
        if detail == "repos":
            detail = "missing"
        return _invalid(step.name, "pre-check", detail)
    hit = _consumed_shape(step, evidence.targets)
    if hit is not None:
        return hit
    if pre.get("ok") is not True:
        reason = pre.get("reason") or "pre-check failed"
        return "step_failed", f"{step.name} did not start: {reason}"
    return None


def _sha(info: dict) -> dict:
    return {"commit": info["commit"], "tree": info["tree"]}


def _check(info: dict) -> dict:
    return {"commit": info["commit"], "tree": info["tree"], "clean": info["clean"], "hidden": info["hidden"]}


def _one(repo: str, row: dict) -> dict:
    return {repo: row}


def _want(evidence: RoundEvidence) -> tuple[dict | None, tuple[str, str] | None]:
    closed, _detail = close_set(evidence.expected_start, evidence.targets, SHA_FIELDS)
    if closed is None:
        return None, ("unknown", "evidence invalid: expected start incomplete in events")
    return closed, None


def _role(evidence: RoundEvidence, repo: str) -> str | None:
    return (evidence.targets.get(repo) or {}).get("role")


def _start_failure(repo: str, role: str | None, got: dict, want: dict, delta: str) -> tuple[str, str]:
    if role == "context":
        return "step_failed", f"context repository {repo} moved"
    if delta == "commit":
        return "step_failed", f"implement did not start: {repo} HEAD {got['commit']} != expected {want['commit']}"
    return "step_failed", f"implement did not start: {repo} tree {got['tree']} != expected {want['tree']}"


def _recorded_failure(repo: str, role: str | None, got: dict, want: dict, delta: str) -> tuple[str, str]:
    if role == "context":
        return "step_failed", f"context repository {repo} moved"
    if delta == "commit":
        return "step_failed", f"implement did not start: {repo} expected {got['commit']} != {want['commit']}"
    return "step_failed", f"implement did not start: {repo} expected tree {got['tree']} != {want['tree']}"


def _start_matches(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    """Found HEAD, recorded expected start, and consumed set against the event start."""
    want, gap = _want(evidence)
    if gap is not None:
        return gap
    found = (step.pre_checks or {}).get("repos") or {}
    if step.name == "implement" and (step.pre_checks or {}).get("kind") != evidence.start_kind:
        got = (step.pre_checks or {}).get("kind")
        return "step_failed", f"implement did not start: start kind {got} != {evidence.start_kind}"
    for repo in sorted(evidence.targets):
        info = found[repo]
        role = _role(evidence, repo)
        delta = set_delta(_one(repo, _sha(info)), _one(repo, want[repo]))
        if delta is not None:
            return _start_failure(repo, role, info, want[repo], delta)
        clean = {**want[repo], "clean": True, "hidden": False}
        if not same_set(_one(repo, _check(info)), _one(repo, clean)):
            if info["clean"] is not True:
                return "step_failed", f"implement did not start: {repo} worktree is dirty"
            return "step_failed", f"hidden index flag in {repo}"
        if info["kind"] != evidence.start_kind:
            return "step_failed", f"implement did not start: {repo} start kind {info['kind']} != {evidence.start_kind}"
        recorded = info["expected"]
        delta = set_delta(_one(repo, _sha(recorded)), _one(repo, want[repo]))
        if delta is not None:
            return _recorded_failure(repo, role, recorded, want[repo], delta)
    consumed = step.consumed or {}
    for repo in sorted(evidence.targets):
        info = consumed[repo]
        delta = set_delta(_one(repo, _sha(info)), _one(repo, want[repo]))
        if delta is not None:
            return _start_failure(repo, _role(evidence, repo), info, want[repo], delta)
    return None


def _sha_row(step: str, repo: str, info: dict, pin: dict) -> tuple[str, str] | None:
    if not same_set(_one(repo, _sha(info)), _one(repo, _sha(pin))):
        return "step_failed", f"{step} ran on a different SHA set"
    clean = {**_sha(pin), "clean": True, "hidden": False}
    if not same_set(_one(repo, _check(info)), _one(repo, clean)):
        if info["clean"] is not True:
            return "step_failed", f"snapshot of {repo} changed during {step}"
        return "step_failed", f"hidden index flag in {repo}"
    if not same_set(_one(repo, _sha(info["consumed"])), _one(repo, _sha(pin))):
        return "step_failed", f"{step} ran on a different SHA set"
    return None


def _invariance(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    pinned, pin_gap = _closed_pin(evidence)
    if pin_gap is not None:
        return pin_gap
    pre_repos = (step.pre_checks or {}).get("repos") or {}
    for repo in sorted(evidence.targets):
        hit = _sha_row(step.name, repo, pre_repos[repo], pinned[repo])
        if hit is not None:
            return hit
    checks = step.checks if isinstance(step.checks, dict) else None
    if not isinstance(checks, dict) or "repos" not in checks:
        return _invalid(step.name, "post-check", "missing")
    detail = _closed_detail(checks.get("repos"), POST_FIELDS[step.name], evidence.targets)
    if detail is not None:
        word = "missing" if detail == "repos" else detail
        return _invalid(step.name, "post-check", word)
    for repo in sorted(evidence.targets):
        hit = _sha_row(step.name, repo, checks["repos"][repo], pinned[repo])
        if hit is not None:
            return hit
    changed = checks.get("snapshot_changed") or []
    if changed:
        return "step_failed", f"snapshot of {changed[0]} changed during {step.name}"
    hidden = checks.get("hidden_flags") or []
    if hidden:
        return "step_failed", f"hidden index flag in {hidden[0]}"
    git_failed = checks.get("git_failed")
    if git_failed:
        return "step_failed", f"snapshot of {git_failed} changed during {step.name}"
    consumed, consumed_detail = close_set(step.consumed, evidence.targets, SHA_FIELDS)
    if consumed_detail is not None:
        return _invalid(step.name, "pre-check", "consumed")
    if not same_set(consumed, pinned):
        return "step_failed", f"{step.name} ran on a different SHA set"
    return None


def _closed_pin(evidence: RoundEvidence) -> tuple[dict | None, tuple[str, str] | None]:
    pinned, detail = close_set(evidence.steps["implement"].pinned, evidence.targets, SHA_FIELDS)
    if detail is not None:
        return None, ("unknown", "evidence invalid: expected pinned incomplete in events")
    return pinned, None


def _pin(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    started = _start_matches(evidence, step)
    if started is not None:
        return started
    if not isinstance(step.pinned, dict):
        return _invalid(step.name, "pinned", "missing")
    detail = _closed_detail(step.pinned, PIN_FIELDS, evidence.targets)
    if detail is not None:
        word = "missing" if detail == "repos" else detail
        return _invalid(step.name, "pinned", word)
    checks = step.checks or {}
    pin_error = checks.get("pin_error")
    if isinstance(pin_error, dict) and pin_error.get("repo"):
        return "step_failed", f"cannot pin {pin_error['repo']}: {pin_error.get('error')}"
    pinned = step.pinned
    replace = checks.get("replace_or_grafts") or []
    if replace:
        return "step_failed", f"{replace[0]} has replace refs or grafts"
    submodules = checks.get("submodules") or []
    if submodules:
        path = submodules[0].get("path") if isinstance(submodules[0], dict) else submodules[0]
        return "step_failed", f"submodule at {path}: recursive pinning is not implemented"
    want, gap = _want(evidence)
    if gap is not None:
        return gap
    for repo, meta in sorted(evidence.targets.items()):
        if meta.get("role") != "context":
            continue
        if not same_set(_one(repo, _sha(pinned[repo])), _one(repo, want[repo])):
            return "step_failed", f"context repository {repo} moved"
    change = [repo for repo, meta in evidence.targets.items() if meta.get("role") == "change"]
    if not change or all((pinned.get(repo) or {}).get("commit") == evidence.targets[repo].get("target_sha") for repo in change):
        return "step_failed", "implement produced no commit"
    for repo in change:
        # A commit identifies one tree. Staying on the start commit while the
        # tree changes is not a pin, including when another repository did move.
        if set_delta(_one(repo, _sha(pinned[repo])), _one(repo, want[repo])) == "tree":
            return "unknown", f"evidence invalid: {repo} commit unchanged but tree changed"
    export_moved = checks.get("export_moved") or []
    if export_moved:
        return "step_failed", f"cannot export {export_moved[0]}: HEAD moved"
    bundles = step.bundles or {}
    for repo in sorted(change):
        if (pinned.get(repo) or {}).get("commit") == evidence.targets[repo].get("target_sha"):
            continue
        bundle = bundles.get(repo)
        if not isinstance(bundle, dict) or not isinstance(bundle.get("length"), int) or not isinstance(bundle.get("sha256"), str):
            return "step_failed", f"cannot export {repo}: HEAD moved"
    for item in evidence.rejected:
        if int(item.get("round") or 0) >= evidence.round_no:
            continue
        rejected, detail = close_set(item.get("sha_set"), evidence.targets, SHA_FIELDS)
        if detail is not None:
            return "unknown", "evidence invalid: expected sha_set incomplete in events"
        if same_set(pinned, rejected):
            return "step_failed", f"no new commit since round {item['round']} said fix first"
    return None


def _verify_text(step: StepView, code: int | None) -> tuple[str, str] | None:
    line = (step.fields or {}).get("stdout_last_line") or ""
    if line == VERDICT_FAIL or line.startswith("VERDICT: FAIL ("):
        return "verify_failed", line
    if code == 1:
        return "step_failed", "verify exited 1 without a FAIL verdict"
    if code == 0 and line != VERDICT_PASS:
        return "step_failed", "verify produced no verdict"
    return None


def _review_text(step: StepView) -> tuple[str, str] | None:
    report = step.report or {}
    if not report.get("present") or report.get("length", 0) == 0:
        return "step_failed", "review produced no report"
    fields = step.fields or {}
    first = fields.get("report_first_line") or ""
    last = fields.get("report_last_line") or ""
    if last != END_MARK:
        return "step_failed", "review report is truncated"
    if first not in (VERDICT_FIX, VERDICT_SAFE):
        return "step_failed", "review produced no verdict"
    if first == VERDICT_FIX:
        return (
            "changes_requested",
            f"fix first (P1 {fields.get('p1', 0)}, P2 {fields.get('p2', 0)}, P3 {fields.get('p3', 0)})",
        )
    return None
