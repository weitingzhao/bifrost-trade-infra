"""Release-window decision (TD-162).

One window file (~/.bifrost-release/window.json), mirrored to ConfigMap
cicd/bifrost-release-window. `what` is a comma-separated list of repo names.

The Tekton task bifrost-release-window inlines this function. check-release-chain.py
fails if the two copies drift. platform-api carries the same table in Go.
"""

from __future__ import annotations

GUARDED = {
    "bifrost-deliver-research": frozenset({"bifrost-research"}),
    "bifrost-build-research-dagster": frozenset({"bifrost-research"}),
    "bifrost-build-market-data": frozenset({"bifrost-platform-plugin-market-data"}),
    "bifrost-build-flex-query": frozenset({"bifrost-platform-plugin-flex-query"}),
    "bifrost-build-ib-gateway": frozenset({"bifrost-platform-plugin"}),
}

TRADE_REPOS = frozenset({
    "bifrost-trade-core",
    "bifrost-trade-api",
    "bifrost-trade-worker",
    "bifrost-trade-frontend",
    "bifrost-trade-infra",
})

TRADE_PIPELINES = {
    "bifrost-deliver-stg": TRADE_REPOS,
    "bifrost-deliver-prod": TRADE_REPOS,
    "bifrost-deliver-platform": frozenset({"bifrost-platform", "bifrost-ui"}),
    "bifrost-deliver-platform-prod": frozenset({"bifrost-platform", "bifrost-ui"}),
}

MUST_HOLD = frozenset(GUARDED)

# Pipelines whose revision must be a 40-char lowercase SHA (TD-95, TD-122).
SHA_PIPELINES = frozenset({
    "bifrost-deliver-research",
    "bifrost-build-research-dagster",
    "bifrost-build-ib-gateway",
})


def parse_what(what: str) -> frozenset[str]:
    return frozenset(part.strip() for part in (what or "").split(",") if part.strip())


def is_full_sha(revision: str) -> bool:
    rev = (revision or "").strip()
    return len(rev) == 40 and all(c in "0123456789abcdef" for c in rev)


def window_if_live(window: dict | None) -> dict | None:
    """A missing or unreadable expires_at stays open. A past one is empty."""
    if not window:
        return None
    raw = window.get("expires_at")
    if not raw:
        return window
    from datetime import datetime, timezone

    text = str(raw).strip().replace("Z", "+00:00")
    try:
        exp = datetime.fromisoformat(text)
    except ValueError:
        return window
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= exp:
        return None
    return window


def decide(window: dict | None, pipeline: str) -> str:
    """Return "" to allow, or a REFUSED message.

    An expires_at in the past is the same as no window. Research and plugin
    build pipelines refuse when no window is open, and when the open window's
    `what` does not name their repo. Any other known pipeline is allowed with
    no window, and refused when a window is open for a different repo.
    """
    window = window_if_live(window)
    required = GUARDED.get(pipeline) or TRADE_PIPELINES.get(pipeline)
    if window is None:
        if pipeline in MUST_HOLD:
            repo = ",".join(sorted(GUARDED[pipeline]))
            return (
                f"REFUSED: no release window for {pipeline}. "
                f"Open one first: release.sh hold --what {repo}"
            )
        return ""
    what = parse_what(str(window.get("what", "")))
    holder = window.get("who") or "unknown"
    held = window.get("what", "")
    if required is None:
        return (
            f"REFUSED: release window held by {holder} (what={held}); "
            f"{pipeline} is not part of that release"
        )
    if what & required:
        return ""
    return (
        f"REFUSED: release window held by someone else "
        f"(who={holder} what={held}); "
        f"{pipeline} needs one of {','.join(sorted(required))}"
    )


def decide_api(window: dict | None, pipeline: str, caller_who: str) -> str:
    """platform-api gate. The Tekton task uses decide(); this one also checks who.

    A window opened by release.sh names its holder in `who`. start_pipeline_run
    must send that same who. Anyone else is refused, including a second session
    releasing the same repo.
    """
    msg = decide(window, pipeline)
    if msg or window is None:
        return msg
    holder = str(window.get("who") or "")
    if caller_who.strip() != holder:
        return (
            f"REFUSED: release window held by someone else "
            f"(who={holder} what={window.get('what', '')})"
        )
    return ""
