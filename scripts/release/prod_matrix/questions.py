"""Explicit questions, the one wildcard question, and the request hash."""

from __future__ import annotations

from typing import Any

from canon import QUESTION_LIMIT, question_id, sha256_hex

WILDCARD = {
    "group": "*",
    "version": "",
    "resource": "*",
    "subresource": "",
    "namespace": "",
    "scope": "cluster",
    "name": "",
    "verb": "*",
    "wildcard": True,
}


def sar_spec(ctx: dict, question: dict) -> dict:
    """Canonical SubjectAccessReview spec. Unknown uid/extra are omitted."""
    attributes = {
        "group": question["group"],
        "name": question["name"],
        "namespace": "" if question.get("scope") == "cluster" else question["namespace"],
        "resource": question["resource"],
        "subresource": question["subresource"],
        "verb": question["verb"],
        "version": question["version"],
    }
    spec: dict[str, Any] = {
        "groups": sorted(set(ctx["groups"])),
        "resourceAttributes": attributes,
        "user": ctx["user"],
    }
    if ctx["uid"]["state"] == "known":
        spec["uid"] = ctx["uid"]["value"]
    if ctx["extra"]["state"] == "known":
        raw = ctx["extra"]["value"]
        spec["extra"] = {key: sorted(raw[key]) for key in sorted(raw)}
    return spec


def sar_body(spec: dict) -> dict:
    return {"apiVersion": "authorization.k8s.io/v1", "kind": "SubjectAccessReview", "spec": spec}


def _selected(identity: dict, question: dict) -> bool:
    if not identity["ask"]:
        return False
    match = question.get("identity_scope", {}).get("match", "all")
    return match == "all"


def expand(identities: list[dict], questions: list[dict]) -> list[dict]:
    """One entry per (identity, explicit question), then one wildcard per askable identity."""
    planned: list[dict] = []
    askable = [item for item in identities if item["ask"]]
    for question in questions:
        for identity in askable:
            if not _selected(identity, question):
                continue
            spec = sar_spec(identity["context"], question)
            digest = sha256_hex(spec)
            planned.append(
                {
                    "identity": identity,
                    "question": question,
                    "spec": spec,
                    "request_hash": digest,
                    "id": question_id(digest),
                    "wildcard": False,
                }
            )
    for identity in askable:
        spec = sar_spec(identity["context"], WILDCARD)
        digest = sha256_hex(spec)
        planned.append(
            {
                "identity": identity,
                "question": WILDCARD,
                "spec": spec,
                "request_hash": digest,
                "id": question_id(digest),
                "wildcard": True,
            }
        )
    return planned


def count_questions(identities: list[dict], questions: list[dict]) -> int:
    return len(expand(identities, questions))


def over_budget(count: int) -> bool:
    return count > QUESTION_LIMIT


def fixed_askable(fixed_rows: list[dict]) -> list[dict]:
    """Lower bound on identities, known before any cluster read."""
    from identities import fixed_identity

    askable = []
    for row in fixed_rows:
        if row["record"] == "auth-chain":
            continue
        ctx, ask = fixed_identity(row)
        if ask:
            askable.append({"context": ctx, "ask": True, "risk": False, "reason": ""})
    return askable
