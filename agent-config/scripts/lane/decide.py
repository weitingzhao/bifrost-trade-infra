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

from query import CLOSING_KINDS, STEPS, same_set, short_set

VERDICT_FAIL = "VERDICT: FAIL"
VERDICT_PASS = "VERDICT: pass"
VERDICT_FIX = "VERDICT: fix first"
VERDICT_SAFE = "VERDICT: safe to merge"
END_MARK = "END OF REPORT"


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


def decide(evidence: RoundEvidence) -> tuple[str, str | None]:
    closing = [row for row in evidence.resolutions if row.get("kind") in CLOSING_KINDS]
    if closing:
        row = closing[0]
        return "step_failed", f"{row['step']} closed as {row['kind']} by {row['operator']}: {row['reason']}"
    if evidence.order_defect:
        return "unknown", evidence.order_defect
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
    hit = _precheck(step)
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


def _precheck(step: StepView) -> tuple[str, str] | None:
    pre = step.pre_checks
    if not isinstance(pre, dict) or not pre.get("repos"):
        return "unknown", f"evidence invalid: {step.name} pre-check missing"
    if pre.get("ok") is not True:
        reason = pre.get("reason") or "pre-check failed"
        return "step_failed", f"{step.name} did not start: {reason}"
    return None


def _commit(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None
    commit = info.get("commit")
    return commit if isinstance(commit, str) and commit else None


def _start_matches(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    """Compare the recorded start with the start computed from events."""
    found = (step.pre_checks or {}).get("repos") or {}
    consumed = step.consumed or {}
    names = sorted(set(evidence.targets) | set(evidence.expected_start) | set(found) | set(consumed))
    for repo in names:
        meta = (evidence.targets or {}).get(repo) or {}
        expected = _commit(evidence.expected_start.get(repo)) or meta.get("target_sha")
        got = _commit(found.get(repo))
        consumed_commit = _commit(consumed.get(repo))
        role = meta.get("role")
        if role == "context" and (got != expected or (consumed_commit is not None and consumed_commit != expected)):
            return "step_failed", f"context repository {repo} moved"
        if got != expected or (consumed_commit is not None and consumed_commit != expected):
            return "step_failed", f"implement did not start: {repo} HEAD {got} != expected {expected}"
        expected_tree = (evidence.expected_start.get(repo) or {}).get("tree")
        found_tree = (found.get(repo) or {}).get("tree")
        if expected_tree and found_tree and expected_tree != found_tree:
            return "step_failed", f"implement did not start: {repo} HEAD {got} != expected {expected}"
        if (found.get(repo) or {}).get("clean") is False:
            return "step_failed", f"implement did not start: {repo} worktree is dirty"
        if (found.get(repo) or {}).get("hidden"):
            return "step_failed", f"hidden index flag in {repo}"
    return None


def _invariance(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    pre_repos = (step.pre_checks or {}).get("repos") or {}
    pinned = evidence.steps["implement"].pinned or {}
    for repo, info in pre_repos.items():
        if info.get("clean") is False:
            return "step_failed", f"snapshot of {repo} changed during {step.name}"
        if info.get("hidden"):
            return "step_failed", f"hidden index flag in {repo}"
        if _commit(info) != _commit(pinned.get(repo)):
            return "step_failed", f"{step.name} ran on a different SHA set"
    checks = step.checks or {}
    changed = checks.get("snapshot_changed") or []
    if changed:
        return "step_failed", f"snapshot of {changed[0]} changed during {step.name}"
    hidden = checks.get("hidden_flags") or []
    if hidden:
        return "step_failed", f"hidden index flag in {hidden[0]}"
    git_failed = checks.get("git_failed")
    if git_failed:
        return "step_failed", f"snapshot of {git_failed} changed during {step.name}"
    pinned = evidence.steps["implement"].pinned
    if not same_set(step.consumed, pinned):
        return "step_failed", f"{step.name} ran on a different SHA set"
    return None


def _pin(evidence: RoundEvidence, step: StepView) -> tuple[str, str] | None:
    started = _start_matches(evidence, step)
    if started is not None:
        return started
    checks = step.checks or {}
    pin_error = checks.get("pin_error")
    if isinstance(pin_error, dict) and pin_error.get("repo"):
        return "step_failed", f"cannot pin {pin_error['repo']}: {pin_error.get('error')}"
    pinned = step.pinned or {}
    for repo in sorted(evidence.targets):
        info = pinned.get(repo) or {}
        if not info.get("commit") or not info.get("tree"):
            return "step_failed", f"cannot pin {repo}: missing"
    replace = checks.get("replace_or_grafts") or []
    if replace:
        return "step_failed", f"{replace[0]} has replace refs or grafts"
    submodules = checks.get("submodules") or []
    if submodules:
        path = submodules[0].get("path") if isinstance(submodules[0], dict) else submodules[0]
        return "step_failed", f"submodule at {path}: recursive pinning is not implemented"
    for repo, meta in sorted(evidence.targets.items()):
        if meta.get("role") == "context" and (pinned.get(repo) or {}).get("commit") != meta.get("target_sha"):
            return "step_failed", f"context repository {repo} moved"
    change = [repo for repo, meta in evidence.targets.items() if meta.get("role") == "change"]
    if not change or all((pinned.get(repo) or {}).get("commit") == evidence.targets[repo].get("target_sha") for repo in change):
        return "step_failed", "implement produced no commit"
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
        if same_set(pinned, item.get("sha_set")):
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
