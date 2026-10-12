"""Closed vocabularies and the platform's published limits.

Codes the fold writes are words from these sets. Quoted text never becomes a code.
Nothing here is a permission to merge or to release.
"""

from __future__ import annotations

# --- event shape -----------------------------------------------------------

ENVELOPE = {"type", "v", "seq", "prev_sha256", "at", "by"}
BY = {"coordinator", "wrapper", "observer"}

KINDS = {"implement", "verify", "review", "merge", "other", "release", "ci"}
WATCHES = {"process", "none", "record"}
PROCESS_OR_NONE_KINDS = {"implement", "verify", "review", "merge", "other"}

CLAIMS = {"landed", "stopped", "dropped"}
USUAL_BASIS = {"measured", "declared"}
REPORTED = {"finished", "failed"}
CAN_ACT = {"yes", "not_yet"}
WHERE = {"thread", "console", "terminal"}
CLOSE_HOW = {"done", "withdrawn"}
CONDITIONS = {"True", "False", "Unknown"}

APPROVAL_STATES = {
    "pending",
    "approved",
    "running",
    "executed",
    "failed",
    "rejected",
    "expired",
    "unknown",
}
QUESTION_STATES = {"open", "answered", "withdrawn", "expired"}
APPROVAL_TERMINAL = {"executed", "failed", "rejected", "expired"}
QUESTION_TERMINAL = {"answered", "withdrawn", "expired"}

OBSERVER_ERRORS = {
    "unreachable",
    "forbidden",
    "timeout",
    "bad_reply",
    "not_found",
    "uid_changed",
    "no_credential",
    "append_failed",
}

# reason on a step or an owner item. Includes the eight observer errors.
REASONS = {
    "exited_nonzero",
    "ended_by_signal",
    "reported_failed",
    "record_failed",
    "wrapper_gone",
    "no_observation",
    "no_output",
    "clock_backwards",
    "reader_clock_behind",
    "log_invalid",
    "not_confirmed",
    "no_match",
    "conflicting_observations",
    "start_not_recorded",
    *OBSERVER_ERRORS,
}

STATES = {"waiting", "running", "slow", "quiet", "unknown", "dead", "failed", "done"}
ENDED_STATES = {"done", "failed"}
OPEN_STATES = {"waiting", "running", "slow", "quiet", "unknown"}

ENDED_HOW = {"exit_0", "reported", "record"}
LABELS = {
    "Exited 0",
    "Reported finished by coordinator",
    "Record: Succeeded",
    "Reported started, not watched",
    "Unknown",
}

HOLDERS = {"agents", "unknown", "coordinator", "owner", "nobody"}
WHYS = {
    "step_running",
    "record_created",
    "record_in_flight",
    "step_unknown",
    "log_invalid",
    "run_unrecorded",
    "owner_item_unknown",
    "next_not_sent",
    "owner_can_act",
    "owner_item_not_ready",
    "ended_awaiting_check",
    "fold_incomplete",
    "queue_done",
    "recorder_failed",
}
# When the holder is unknown, exactly one of these, in this order.
UNKNOWN_WHY_ORDER = (
    "recorder_failed",
    "fold_incomplete",
    "run_unrecorded",
    "step_unknown",
    "log_invalid",
    "owner_item_unknown",
)
CAN_ACT_OUT = {"yes", "unknown", "not_yet"}

# Defect codes. An invalid event is skipped; the code says why.
DEFECTS = {
    "bad_number",
    "bad_type",
    "limit_text",
    "unknown_type",
    "unknown_field",
    "missing_field",
    "bad_value",
    "ref_format",
    "bad_exit",
    "not_first",
    "work_id_mismatch",
    "already_closed",
    "closed_with_open_items",
    "after_close",
    "step_exists",
    "kind_watch",
    "process_waiting_on",
    "needs_locator",
    "too_many_steps",
    "unknown_id",
    "superseded",
    "withdraw_started",
    "not_declared",
    "already_started",
    "late_start",
    "waits_open",
    "watch_mismatch",
    "by_mismatch",
    "not_started",
    "run_mismatch",
    "already_ended",
    "already_dead",
    "output_shrunk",
    "sampled_at",
    "never_found",
    "uid_changed",
    "ref_busy",
    "record_fields",
    "commands_where",
    "too_many_waits",
    "wait_missing",
    "not_a_record",
    "already_settled",
    "already_ready",
    "bound_wait",
    "step_missing",
    "wrong_log",
    "round_order",
    "round_size",
    "bad_error",
    "round_conflict",
}

# Field-class codes, then relation-class codes. The first one that applies is kept.
DEFECT_ORDER = (
    "bad_number",
    "bad_type",
    "limit_text",
    "unknown_type",
    "unknown_field",
    "missing_field",
    "bad_value",
    "ref_format",
    "bad_exit",
    "not_first",
    "work_id_mismatch",
    "already_closed",
    "closed_with_open_items",
    "after_close",
    "step_exists",
    "kind_watch",
    "process_waiting_on",
    "needs_locator",
    "too_many_steps",
    "unknown_id",
    "superseded",
    "withdraw_started",
    "not_declared",
    "already_started",
    "late_start",
    "waits_open",
    "watch_mismatch",
    "by_mismatch",
    "not_started",
    "run_mismatch",
    "already_ended",
    "already_dead",
    "output_shrunk",
    "sampled_at",
    "never_found",
    "uid_changed",
    "ref_busy",
    "record_fields",
    "commands_where",
    "too_many_waits",
    "wait_missing",
    "not_a_record",
    "already_settled",
    "already_ready",
    "bound_wait",
    "step_missing",
    "wrong_log",
    "round_order",
    "round_size",
    "bad_error",
    "round_conflict",
)

# Keys that are not quoted text. Changing them is allowed to change state.
NAME_LIMIT = 80
TEXT_LIMIT = 200
COMMAND_LIMIT = 400
MAX_COMMANDS = 5
MAX_STEPS = 200
MAX_OPEN_WAITS = 20
MAX_LOGS = 200
MAX_LINE_BYTES = 131072
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 20_000
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_OBSERVER_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 8
TWO53 = 1 << 53
UNREAD_NAMES = 20
GRAPH_CAP = 60
QUEUE_CAP = 30
STEP_EVENTS_CAP = 30
ROUND_ITEM_LIMIT = 400
WORK_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$"
OBSERVER_NAME_RE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}\.jsonl$"
EVENT_VERSION = 2

OBS_VALID_S = 180
QUIET_S = 420
CLOCK_SKEW_S = 2
SAMPLED_LAG_S = 30
SLOW_FACTOR = 1.5
OUTPUT_LARGE_BYTES = 1 << 30
GAP_S = 180

# Platform limits, read from agentprogress schema.go and document.go.
# publish_view stays inside these. Feed and owner_all are tighter on purpose.
PLATFORM_MAX_PUT_BYTES = 262144  # 256 KiB, document.go MaxDocumentBytes
PLATFORM_MAX_WORKS = 30
PLATFORM_MAX_STEPS = 20
PLATFORM_MAX_OWNER_NOW = 10
PLATFORM_MAX_ACTIONS = 10
PLATFORM_MAX_FEED = 50
PLATFORM_MAX_RECENT = 30
PLATFORM_MAX_NEEDS_YOU = 30
PLATFORM_STALE_S = 300
PLATFORM_HOST_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

PUBLISH_TARGET_BYTES = 204800  # 200 KiB
PUBLISH_MAX_FEED = 25
PUBLISH_MAX_OWNER_ALL = 30
PUBLISH_FEED_REDUCED = 10
PUBLISH_UNFINISHED_KEEP = 5
PUBLISH_UNKNOWN_REASONS = 3

# Keys the platform redacts wholesale. A published document must not use them.
SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "cookie",
)

SCHEMAS: dict[str, dict[str, set[str]]] = {
    "work_opened": {"required": {"work_id", "title"}, "optional": {"goal", "work_ref"}},
    "work_closed": {"required": {"claim"}, "optional": set()},
    "step_declared": {
        "required": {"step_id", "name", "kind", "who", "watch"},
        "optional": {
            "locator", "round", "after", "usual_s", "usual_basis", "waiting_on",
            "replaces", "replaces_text",
        },
    },
    "step_superseded": {"required": {"step_id"}, "optional": {"text"}},
    "step_started": {"required": {"step_id", "run_id"}, "optional": {"command", "pid"}},
    "step_seen": {
        "required": {"step_id", "run_id", "sampled_at", "alive"},
        "optional": {"output_bytes", "text"},
    },
    "step_finished": {
        "required": {"step_id", "run_id"},
        "optional": {"exit", "reported", "quote"},
    },
    "record_seen": {
        "required": {"step_id", "sampled_at", "found"},
        "optional": {"uid", "started_at", "ended_at", "condition", "reason_quote"},
    },
    "owner_wait_opened": {
        "required": {"wait_id", "title", "ref"},
        "optional": {
            "can_act",
            "where",
            "reply",
            "reply_needed",
            "reply_words",
            "commands",
            "deadline",
            "no_deadline",
            "blocks_nothing",
            "not_before_text",
            "advice",
            "blocks_text",
            "after_text",
            "after",
            "replaces",
        },
    },
    "owner_wait_seen": {
        "required": {"wait_id", "sampled_at", "ref_state"},
        "optional": {"expires_at", "number"},
    },
    "owner_wait_ready": {"required": {"wait_id"}, "optional": set()},
    "owner_wait_closed": {"required": {"wait_id", "how"}, "optional": set()},
    "note": {"required": {"text"}, "optional": {"step_id"}},
    "observer_round": {
        "required": {"round_id", "started_at", "ended_at", "confirmed", "failed"},
        "optional": {"truncated", "unrecorded"},
    },
    "tail_repaired": {"required": {"repair_id", "bytes", "sha256"}, "optional": set()},
}

# Nested objects and list items. The mutant test walks these tables.
NESTED_FIELDS = {
    "locator": ("cluster", "namespace", "name"),
    "exit": ("code", "signal"),
    "ref": ("kind", "id"),
    "failed_item": ("key", "error"),
    "unrecorded_item": ("work_id", "step_id", "run_id"),
}
LIST_FIELDS = {
    "waiting_on": "str",
    "commands": "str",
    "confirmed": "str",
    "failed": "failed_item",
    "unrecorded": "unrecorded_item",
}

STRING_FIELDS = {
    "work_id",
    "title",
    "goal",
    "work_ref",
    "step_id",
    "name",
    "kind",
    "who",
    "watch",
    "after",
    "usual_basis",
    "replaces",
    "replaces_text",
    "text",
    "run_id",
    "command",
    "quote",
    "reported",
    "uid",
    "condition",
    "reason_quote",
    "wait_id",
    "can_act",
    "where",
    "reply",
    "reply_words",
    "not_before_text",
    "advice",
    "blocks_text",
    "after_text",
    "ref_state",
    "how",
    "round_id",
    "repair_id",
    "sha256",
    "claim",
    "error",
    "key",
}
NUMBER_FIELDS = {
    "at",
    "seq",
    "round",
    "usual_s",
    "pid",
    "sampled_at",
    "output_bytes",
    "started_at",
    "ended_at",
    "deadline",
    "expires_at",
    "number",
    "bytes",
    "started_at",
    "ended_at",
}
BOOL_FIELDS = {"alive", "found", "reply_needed", "no_deadline", "blocks_nothing", "truncated"}
NAME_FIELDS = {"work_id", "title", "name", "who", "step_id", "run_id", "wait_id", "round_id", "work_ref"}


def watch_matches(kind: str, watch: str) -> bool:
    if kind in PROCESS_OR_NONE_KINDS:
        return watch in {"process", "none"}
    if kind == "release":
        return watch == "record"
    if kind == "ci":
        return watch in {"record", "none"}
    return False


def terminal_state(kind: str, ref_state: str) -> bool:
    if kind == "approval":
        return ref_state in APPROVAL_STATES and ref_state in APPROVAL_TERMINAL
    if kind == "question":
        return ref_state in QUESTION_STATES and ref_state in QUESTION_TERMINAL
    return False


def ref_state_ok(kind: str, ref_state: str) -> bool:
    if kind == "approval":
        return ref_state in APPROVAL_STATES
    if kind == "question":
        return ref_state in QUESTION_STATES
    return False
