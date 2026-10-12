"""Table B markers kept at each reduction level. One pair is one line."""

from __future__ import annotations

KEEP = {
    (0, "logs_unread"),
    (0, "log_invalid_at"),
    (0, "torn_tail"),
    (0, "recorder_failed"),
    (0, "unrecorded_runs"),
    (0, "log_full"),
    (0, "defects"),
    (0, "step_unknown"),
    (0, "owner_unknown"),
    (0, "observer"),
    (0, "internal_errors"),
    (0, "conservation"),
    (0, "gap"),
    (1, "logs_unread"),
    (1, "log_invalid_at"),
    (1, "torn_tail"),
    (1, "recorder_failed"),
    (1, "unrecorded_runs"),
    (1, "log_full"),
    (1, "defects"),
    (1, "step_unknown"),
    (1, "owner_unknown"),
    (1, "observer"),
    (1, "internal_errors"),
    (1, "conservation"),
    (1, "gap"),
    (2, "logs_unread"),
    (2, "log_invalid_at"),
    (2, "torn_tail"),
    (2, "recorder_failed"),
    (2, "unrecorded_runs"),
    (2, "log_full"),
    (2, "defects"),
    (2, "step_unknown"),
    (2, "owner_unknown"),
    (2, "observer"),
    (2, "internal_errors"),
    (2, "conservation"),
    (2, "gap"),
    (3, "logs_unread"),
    (3, "log_invalid_at"),
    (3, "torn_tail"),
    (3, "recorder_failed"),
    (3, "unrecorded_runs"),
    (3, "log_full"),
    (3, "defects"),
    (3, "step_unknown"),
    (3, "owner_unknown"),
    (3, "observer"),
    (3, "internal_errors"),
    (3, "conservation"),
    (3, "gap"),
    (4, "logs_unread"),
    (4, "log_invalid_at"),
    (4, "torn_tail"),
    (4, "recorder_failed"),
    (4, "unrecorded_runs"),
    (4, "log_full"),
    (4, "defects"),
    (4, "step_unknown"),
    (4, "owner_unknown"),
    (4, "observer"),
    (4, "internal_errors"),
    (4, "conservation"),
    (4, "gap"),
    (5, "logs_unread"),
    (5, "log_invalid_at"),
    (5, "torn_tail"),
    (5, "recorder_failed"),
    (5, "unrecorded_runs"),
    (5, "log_full"),
    (5, "defects"),
    (5, "step_unknown"),
    (5, "owner_unknown"),
    (5, "observer"),
    (5, "internal_errors"),
    (5, "conservation"),
    (5, "gap"),
    (6, "logs_unread"),
    (6, "log_invalid_at"),
    (6, "torn_tail"),
    (6, "recorder_failed"),
    (6, "unrecorded_runs"),
    (6, "log_full"),
    (6, "defects"),
    (6, "step_unknown"),
    (6, "owner_unknown"),
    (6, "observer"),
    (6, "internal_errors"),
    (6, "conservation"),
    (6, "gap"),
}

# Summary levels must not grow a gap. A mutant sets one of these to 1.
SUMMARY_GAP_3 = 0
SUMMARY_GAP_5 = 0
SUMMARY_GAP_6 = 0


def kept(level: int, marker: str) -> bool:
    return (level, marker) in KEEP


def apply_keep(doc: dict, level: int) -> None:
    """Drop a marker this level does not keep. A complete KEEP changes nothing."""
    if not kept(level, "logs_unread"):
        doc.pop("logs_unread", None)
        doc.pop("logs_unread_names", None)
    if not kept(level, "internal_errors"):
        doc.pop("internal_errors", None)
        doc.pop("internal", None)
    if not kept(level, "observer"):
        doc.pop("observer", None)
        doc.pop("clock", None)
    if not kept(level, "recorder_failed"):
        doc.pop("recorder_failed", None)
    if not kept(level, "conservation"):
        doc.pop("works_total", None)
        doc.pop("owner_all_cut", None)
        doc.pop("omitted_works", None)
        doc.pop("feed_cut", None)
    if not kept(level, "owner_unknown"):
        for item in doc.get("owner_all") or []:
            if type(item) is dict and item.get("can_act") == "unknown":
                item["can_act"] = "yes"
                item.pop("reason", None)
    gap_flag = {3: SUMMARY_GAP_3, 5: SUMMARY_GAP_5, 6: SUMMARY_GAP_6}.get(level, 0)
    for work in doc.get("works") or []:
        if type(work) is not dict:
            continue
        if not kept(level, "log_invalid_at"):
            work.pop("log_invalid_at", None)
            work.pop("log_invalid_why", None)
        if not kept(level, "torn_tail"):
            work.pop("torn_tail", None)
        if not kept(level, "unrecorded_runs"):
            work.pop("unrecorded_runs", None)
        if not kept(level, "log_full"):
            work.pop("log_full", None)
        if not kept(level, "defects"):
            work.pop("defects", None)
            work.pop("defects_count", None)
        if not kept(level, "gap"):
            for step in work.get("steps") or []:
                if type(step) is dict:
                    step.pop("gap", None)
        if not kept(level, "step_unknown"):
            for step in work.get("steps") or []:
                if type(step) is dict and step.get("state") == "unknown":
                    step["state"] = "waiting"
                    step.pop("reason", None)
            counts = work.get("state_counts")
            if type(counts) is dict and counts.get("unknown"):
                counts["waiting"] = counts.get("waiting", 0) + counts["unknown"]
                counts["unknown"] = 0
            work.pop("unknown_reasons", None)
        if gap_flag and "state_counts" in work:
            work["gap"] = True

