"""What a freeze does to a PipelineRun already in flight (W-56 step 1, slice B).

The freeze-check task is the cut. These outcomes are what the tests pin.
Listing the runs is not built in this slice.
"""

from __future__ import annotations

# A run that passed the cut leaves this result on its freeze-check TaskRun.
# The value is the same UTC timestamp the task prints after 未冻结：.
PASSED_CUT_RESULT = "passed_cut_at"

# How a reader finds those runs. Not executed here.
# TaskRuns of bifrost-release-freeze-check carry label tekton.dev/pipelineTask=freeze-check
# and label tekton.dev/pipelineRun=<PipelineRun name>. A run whose freeze-check
# TaskRun has result passed_cut_at, and whose PipelineRun is still running, is
# past the cut. A freeze receipt names that PipelineRun. Nothing in this slice
# lists them.
LIST_HINT = (
    "taskruns of bifrost-release-freeze-check with result passed_cut_at, "
    "joined by label tekton.dev/pipelineRun to a PipelineRun that is still running"
)

# position -> outcome, once a freeze is in force (or the check itself fails).
OUTCOMES = {
    # Still before the check: the check runs fail-closed and the run stops.
    "pending_before_check": "refused",
    "paused_before_check": "refused",
    # The check already wrote passed_cut_at. No second check runs before rollout.
    "past_cut": "continues",
    # The check task itself did not succeed, so the PipelineRun is refused.
    "check_timeout": "refused",
    "check_cancelled": "refused",
    # One image push landed and the other failed or was cancelled. Recorded as
    # the run already recorded it. This slice does not undo or prevent that.
    "partial_push": "recorded_as_is",
}


def outcome(position: str) -> str:
    if position not in OUTCOMES:
        raise KeyError(position)
    return OUTCOMES[position]


def receipt_name(passed_cut_at: str, pipeline_run: str, still_running: bool) -> str:
    """PipelineRun name a freeze receipt would carry, or empty when it would not."""
    if passed_cut_at and still_running and pipeline_run:
        return pipeline_run
    return ""
