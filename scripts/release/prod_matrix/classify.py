"""Offline classification. Reads a bundle and writes rows. Never emits a refusal."""

from __future__ import annotations

from typing import Any

from attempts import budget, chains, group_result, response_request_hash
from canon import (
    QUESTION_LIMIT,
    REQUEST_FAMILY,
    SUMMARY_1,
    MatrixExit,
    dump_line,
    question_id,
    sha256_hex,
    summary_line,
)
from exceptions import (
    assert_asked_discovered,
    match_risk,
    matches,
    prepare,
    surface_reason,
    target_namespaces,
)
from exceptions import cells_of
from identities import assemble, assert_target_namespaces, check_review_context, context, inventory
from questions import expand, over_budget

BLANK = context("user", "", [], {"state": "unknown"}, {"state": "unknown"}, "")


def row_key(subject: dict, group: str, resource: str, subresource: str, namespace: str, name: str, verb: str) -> str:
    payload = {
        "executor": subject,
        "group": group,
        "name": name,
        "namespace": namespace,
        "request_family": REQUEST_FAMILY,
        "resource": resource,
        "subject": subject,
        "subresource": subresource,
        "verb": verb,
    }
    return sha256_hex(payload)


def _base_row(kind: str, reason: str, subject: dict | None, question: dict | None) -> dict:
    row: dict[str, Any] = {"kind": kind, "reason": reason, "request_family": REQUEST_FAMILY}
    group = resource = subresource = namespace = name = verb = ""
    scope = ""
    if question:
        group = question["group"]
        resource = question["resource"]
        subresource = question["subresource"]
        namespace = "" if question.get("scope") == "cluster" else question["namespace"]
        name = question["name"]
        verb = question["verb"]
        scope = question["scope"]
        row.update(
            {
                "group": group,
                "resource": resource,
                "subresource": subresource,
                "namespace": namespace,
                "scope": scope,
                "name": name,
                "verb": verb,
                "version": question["version"],
            }
        )
        if name:
            row["only"] = name
    if subject is not None:
        row["subject"] = subject
        row["executor"] = subject
        row["row_key"] = row_key(subject, group, resource, subresource, namespace, name, verb)
    else:
        row["row_key"] = row_key(BLANK, group, resource, subresource, namespace, name, verb)
    return row


def _context_unconfirmed(subject: dict, confirmed: bool) -> bool:
    """Unknown uid or extra is not a denial unless the chain is confirmed as RBAC and Node only."""
    if confirmed:
        return False
    return subject["uid"]["state"] != "known" or subject["extra"]["state"] != "known"


def interpret(response: Any) -> str:
    if not isinstance(response, dict) or response.get("kind") != "SubjectAccessReview":
        return "malformed"
    status = response.get("status", None)
    if not isinstance(status, dict):
        return "missing-status"
    if status.get("evaluationError"):
        return "evaluation-error"
    allowed = status.get("allowed", None)
    denied = status.get("denied", False)
    if not isinstance(allowed, bool) or not isinstance(denied, bool):
        return "malformed"
    if allowed and denied:
        return "contradictory"
    if allowed:
        return "allowed"
    if denied:
        return "denied"
    return "no-opinion"


def truncated(question_count: int) -> tuple[int, str]:
    row = {"kind": "unclassified", "reason": "derivation truncated", "request_family": REQUEST_FAMILY}
    lines = [
        SUMMARY_1,
        summary_line(0, 0, 0),
        f"question count: {question_count}; limit {QUESTION_LIMIT}",
        "unclassified: derivation truncated",
        dump_line(row),
    ]
    return 2, "\n".join(lines) + "\n"


def _review_answers(chosen: dict[str, dict]) -> dict[str, dict]:
    """The answer is the last attempt of that request. The question id is derived from the hash."""
    answers: dict[str, dict] = {}
    for digest, attempt in chosen.items():
        if attempt["kind"] != "review":
            continue
        response_request_hash(attempt, group_result(attempt))
        spec = attempt["request"]["body"]["spec"]
        check_review_context(spec)
        qid = question_id(digest)
        if qid in answers:
            raise MatrixExit(2, f"bundle: {qid}: duplicate question id")
        answers[qid] = attempt
    return answers


def render(rows: list[dict], denied: int, expired: int, question_count: int, matched: dict[str, int]) -> tuple[int, str]:
    counts = {"not-asked": 0, "names-not-enumerated": 0, "named-subresource-not-asked": 0}
    for row in rows:
        if row["reason"] in counts:
            counts[row["reason"]] += 1
    rows = sorted(
        rows,
        key=lambda row: (
            row["kind"],
            row["reason"],
            row.get("namespace", ""),
            row.get("group", ""),
            row.get("resource", ""),
            row.get("subresource", ""),
            row.get("verb", ""),
            row.get("name", ""),
            (row.get("subject") or {}).get("user", ""),
        ),
    )
    lines = [
        SUMMARY_1,
        summary_line(counts["not-asked"], counts["names-not-enumerated"], counts["named-subresource-not-asked"]),
        f"question count: {question_count}; limit {QUESTION_LIMIT}",
        f"asked-not-allowed: {denied}",
        f"expired exceptions: {expired}",
        f"exceptions trust-root: {matched['trust-root']}",
        f"exceptions field: {matched['field']}",
    ]
    lines.extend(dump_line(row) for row in rows)
    # Read-only half: exit 3 wins over exit 1. Exit 0 is not produced.
    return 3, "\n".join(lines) + "\n"


def replay(bundle: dict, targets: dict, fixed: dict, exceptions: dict, nontargets: dict, today) -> tuple[int, str]:
    attempts = list(bundle.get("attempts") or [])
    budget(attempts)
    chosen = chains(attempts)
    questions = list(targets["questions"])
    fixed_rows = list(fixed["rows"])
    prepared = prepare(list(exceptions["exceptions"]), today)
    lists = inventory(attempts, chosen=chosen)
    identities = assemble(lists, fixed_rows)
    planned = expand(identities, questions)
    question_count = len(planned)
    if over_budget(question_count):
        return truncated(question_count)
    ids = [item["id"] for item in planned]
    if len(ids) != len(set(ids)):
        raise MatrixExit(2, "bundle: duplicate question id")
    assert_target_namespaces(lists["namespaces"], questions, fixed_rows)
    assert_asked_discovered(questions, lists["resources"])
    answers = _review_answers(chosen)
    expected = {item["id"]: item for item in planned}
    missing = sorted(set(expected) - set(answers))
    if missing:
        raise MatrixExit(2, f"bundle: {missing[0]}: missing answer")
    extra = sorted(set(answers) - set(expected))
    if extra:
        raise MatrixExit(2, f"bundle: {extra[0]}: unexpected answer")

    confirmed = False
    for row in fixed_rows:
        if row["record"] == "auth-chain":
            confirmed = bool(row["confirmed"])
    denied = 0
    matched = {"trust-root": 0, "field": 0}
    rows: list[dict] = []

    for item in planned:
        review = answers[item["id"]]
        verdict = interpret(group_result(review))
        subject = item["identity"]["context"]
        question = item["question"]
        # Context is first. An exception cannot absorb an unconfirmed allow or denial.
        if verdict in {"allowed", "denied", "no-opinion"} and _context_unconfirmed(subject, confirmed):
            rows.append(_base_row("unknown-surface", "context-unconfirmed", subject, question))
            continue
        if verdict == "allowed":
            exception = next((exc for exc in prepared if matches(exc, subject, question)), None)
            if exception:
                row = _base_row("named-exception", exception["reason"], subject, question)
                row["exception_class"] = exception["class"]
                matched[exception["class"]] += 1
            else:
                reason = "all resources, including those added later" if item["wildcard"] else "allowed"
                row = _base_row("unclassified", reason, subject, question)
            rows.append(row)
            continue
        if verdict == "denied" or (verdict == "no-opinion" and confirmed):
            denied += 1
            continue
        reason = "no-opinion" if verdict == "no-opinion" else verdict
        rows.append(_base_row("unknown-surface", reason, subject, question))

    for cell in cells_of(lists["resources"], lists["namespaces"]):
        reason = surface_reason(cell, questions, nontargets["entries"])
        if not reason:
            continue
        row = _base_row("unknown-surface", reason, None, None)
        row.update(
            {
                "group": cell["group"],
                "resource": cell["resource"],
                "subresource": cell["subresource"],
                "namespace": cell["namespace"],
                "scope": cell["scope"],
            }
        )
        row["row_key"] = row_key(
            BLANK, cell["group"], cell["resource"], cell["subresource"], cell["namespace"], "", ""
        )
        rows.append(row)

    for namespace in target_namespaces(questions):
        row = _base_row("unknown-surface", "names-unreadable", None, None)
        row.update({"resource": "secrets", "namespace": namespace, "scope": "namespaced", "group": "", "subresource": ""})
        row["row_key"] = row_key(BLANK, "", "secrets", "", namespace, "", "")
        rows.append(row)

    if not confirmed:
        rows.append(_base_row("unknown-surface", "auth-chain-unconfirmed", None, None))
    rows.append(_base_row("unknown-surface", "side-effecting tasks not provided", None, None))

    for identity in identities:
        if not identity.get("fixed_id"):
            continue
        exception = next((exc for exc in prepared if match_risk(exc, identity["context"])), None)
        if exception:
            row = _base_row("named-exception", exception["reason"], identity["context"], None)
            row["exception_class"] = exception["class"]
            matched[exception["class"]] += 1
        else:
            row = _base_row("unclassified", identity["reason"], identity["context"], None)
        rows.append(row)

    expired = sum(1 for exc in prepared if exc["expired"])
    return render(rows, denied, expired, question_count, matched)
