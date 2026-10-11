"""Offline classification. Reads a bundle and writes rows. Never emits a refusal."""

from __future__ import annotations

from typing import Any

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
from identities import assemble, check_review_context, context, inventory
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


def _primaries(reviews: list[dict]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    seen_ids: dict[str, int] = {}
    for review in reviews:
        seen_ids[review["id"]] = seen_ids.get(review["id"], 0) + 1
        if review.get("retry_of"):
            continue
        found.setdefault(review["id"], []).append(review)
    for qid, count in seen_ids.items():
        primaries = len(found.get(qid, []))
        retries = count - primaries
        if primaries > 1:
            raise MatrixExit(2, f"bundle: {qid}: two answers")
        if count > 1 and retries == 0:
            raise MatrixExit(2, f"bundle: {qid}: duplicate question id")
        if primaries == 0 and count > 1:
            raise MatrixExit(2, f"bundle: {qid}: duplicate question id")
    return found


def _check_review(review: dict) -> dict:
    request = review.get("request")
    if not isinstance(request, dict) or not isinstance(request.get("spec"), dict):
        raise MatrixExit(2, f"bundle: {review.get('id')}: malformed request")
    spec = request["spec"]
    check_review_context(spec)
    digest = sha256_hex(spec)
    if digest != review.get("request_hash") or question_id(digest) != review.get("id"):
        raise MatrixExit(2, f"bundle: {review.get('id')}: request hash does not match")
    response = review.get("response")
    if not isinstance(response, dict) or response.get("request_hash") != digest:
        raise MatrixExit(2, f"bundle: {review.get('id')}: response request hash does not match")
    return spec


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
    questions = list(targets["questions"])
    fixed_rows = list(fixed["rows"])
    prepared = prepare(list(exceptions["exceptions"]), today)
    lists = inventory(bundle["commands"])
    identities = assemble(lists, fixed_rows)
    planned = expand(identities, questions)
    question_count = len(planned)
    if over_budget(question_count):
        return truncated(question_count)
    ids = [item["id"] for item in planned]
    if len(ids) != len(set(ids)):
        raise MatrixExit(2, "bundle: duplicate question id")
    assert_asked_discovered(questions, lists["resources"])
    primaries = _primaries(bundle["reviews"])
    expected = {item["id"]: item for item in planned}
    for review in primaries.values():
        _check_review(review[0])
    missing = sorted(set(expected) - set(primaries))
    if missing:
        raise MatrixExit(2, f"bundle: {missing[0]}: missing answer")
    extra = sorted(set(primaries) - set(expected))
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
        review = primaries[item["id"]][0]
        verdict = interpret(review["response"])
        subject = item["identity"]["context"]
        question = item["question"]
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
        if not identity.get("risk"):
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
