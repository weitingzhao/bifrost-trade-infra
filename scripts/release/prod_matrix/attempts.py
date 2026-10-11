"""One attempt per request. Replay keeps a single chain for each request hash.

A page is its own read (path plus continue). The collector does not merge attempts.
The result body is stored verbatim; body_sha256 is the canonical digest of that body,
so a one-node edit of the body cannot replay as a smaller inventory.
"""

from __future__ import annotations

from typing import Any

from canon import QUESTION_LIMIT, READ_LIMIT, MatrixExit, sha256_hex

LIST_PATHS = (
    "/api/v1/namespaces",
    "/api/v1/serviceaccounts",
    "/api/v1/nodes",
    "/apis/rbac.authorization.k8s.io/v1/roles",
    "/apis/rbac.authorization.k8s.io/v1/rolebindings",
    "/apis/rbac.authorization.k8s.io/v1/clusterroles",
    "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings",
)


def seal_result(body: Any, ok: bool, status_code: int) -> dict:
    return {"body": body, "body_sha256": sha256_hex(body), "ok": ok, "status_code": status_code}


def reseal(attempt: dict) -> dict:
    """Recompute hashes after a test edits the request or the body on purpose."""
    result = attempt["result"]
    result["body_sha256"] = sha256_hex(result["body"])
    if attempt["kind"] == "review":
        attempt["request_hash"] = sha256_hex(attempt["request"]["body"]["spec"])
    else:
        attempt["request_hash"] = sha256_hex(attempt["request"])
    return attempt


def _fail(attempt: dict, message: str) -> None:
    number = attempt.get("attempt", "?")
    raise MatrixExit(2, f"bundle: attempt {number}: {message}")


def verify_hashes(attempt: dict) -> None:
    if not isinstance(attempt, dict):
        raise MatrixExit(2, "bundle: attempt is not an object")
    result = attempt.get("result")
    if not isinstance(result, dict):
        _fail(attempt, "missing result")
    if result.get("body_sha256") != sha256_hex(result.get("body")):
        _fail(attempt, "body hash does not match")
    request = attempt.get("request")
    if not isinstance(request, dict):
        _fail(attempt, "missing request")
    if attempt.get("kind") == "review":
        body = request.get("body")
        if not isinstance(body, dict) or not isinstance(body.get("spec"), dict):
            _fail(attempt, "malformed request")
        if sha256_hex(body["spec"]) != attempt.get("request_hash"):
            _fail(attempt, "request hash does not match")
        return
    if attempt.get("kind") != "read":
        _fail(attempt, "kind is not read or review")
    if sha256_hex(request) != attempt.get("request_hash"):
        _fail(attempt, "request hash does not match")


def budget(attempts: list) -> None:
    if not isinstance(attempts, list):
        raise MatrixExit(2, "bundle: attempts is not a list")
    reads = 0
    reviews = 0
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise MatrixExit(2, "bundle: attempt is not an object")
        kind = attempt.get("kind")
        if kind == "read":
            reads += 1
        elif kind == "review":
            reviews += 1
        else:
            raise MatrixExit(2, "bundle: attempt kind")
    if reads > READ_LIMIT:
        raise MatrixExit(2, "budget: read attempts exceed 500")
    if reviews > QUESTION_LIMIT:
        raise MatrixExit(2, "budget: review attempts exceed 20000")


def chains(attempts: list) -> dict[str, dict]:
    """Group by request hash. Each group is one chain; the result is the last attempt."""
    numbers: dict[int, dict] = {}
    for attempt in attempts:
        verify_hashes(attempt)
        number = attempt.get("attempt")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            _fail(attempt, "attempt is not a positive integer")
        if number in numbers:
            raise MatrixExit(2, f"bundle: attempt {number}: duplicate attempt")
        numbers[number] = attempt
    grouped: dict[str, list[dict]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt["request_hash"], []).append(attempt)
    chosen: dict[str, dict] = {}
    for digest, group in grouped.items():
        group.sort(key=lambda item: item["attempt"])
        if "retry_of" in group[0]:
            _fail(group[0], "retry does not start a chain")
        for item in group:
            retry = item.get("retry_of")
            if retry is None:
                continue
            if isinstance(retry, bool) or not isinstance(retry, int):
                _fail(item, "retry_of is not an attempt")
            if retry == item["attempt"]:
                _fail(item, "retry points at itself")
            if retry > item["attempt"]:
                _fail(item, "retry points at a later attempt")
            target = numbers.get(retry)
            if target is None:
                _fail(item, "retry_of does not point at an attempt")
            if target["request_hash"] != digest:
                _fail(item, "retry points at another request")
        for prev, cur in zip(group, group[1:]):
            if cur.get("retry_of") != prev["attempt"]:
                _fail(cur, "not a chain")
        chosen[digest] = group[-1]
    return chosen


def _body(attempt: dict) -> Any:
    result = attempt["result"]
    if not result.get("ok") or result.get("status_code") == 410:
        _fail(attempt, f"read failed ({result.get('status_code')})")
    return result.get("body")


def _meta_continue(body: Any, attempt: dict) -> str:
    if not isinstance(body, dict):
        _fail(attempt, "body is not an object")
    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    if body.get("metadata") is not None and not isinstance(body.get("metadata"), dict):
        _fail(attempt, "metadata is not an object")
    token = meta.get("continue") or ""
    if not isinstance(token, str):
        _fail(attempt, "continue is not a string")
    return token


def pages_for(attempts: list[dict], path: str) -> list[dict]:
    """Walk the continue chain. A repeated or missing page is exit 2."""
    by_token: dict[str, dict] = {}
    for attempt in attempts:
        if attempt.get("kind") != "read" or attempt["request"]["path"] != path:
            continue
        token = str((attempt["request"].get("params") or {}).get("continue") or "")
        if token in by_token:
            _fail(attempt, "repeated page")
        by_token[token] = attempt
    if not by_token:
        raise MatrixExit(2, f"bundle: missing read {path}")
    if "" not in by_token:
        raise MatrixExit(2, f"bundle: {path}: missing page")
    ordered = []
    token = ""
    seen: set[int] = set()
    while True:
        attempt = by_token.get(token)
        if attempt is None:
            raise MatrixExit(2, f"bundle: {path}: missing page")
        if attempt["attempt"] in seen:
            _fail(attempt, "page count")
        seen.add(attempt["attempt"])
        body = _body(attempt)
        ordered.append(attempt)
        nxt = _meta_continue(body, attempt)
        if not nxt:
            break
        token = nxt
    if len(ordered) != len(by_token):
        raise MatrixExit(2, f"bundle: {path}: page count")
    return ordered


def parse_items(body: Any, attempt: dict) -> list[dict]:
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        _fail(attempt, "list has no items")
    found = []
    for index, item in enumerate(body["items"]):
        if not isinstance(item, dict):
            _fail(attempt, f"items[{index}] is not an object")
        meta = item.get("metadata")
        name = meta.get("name") if isinstance(meta, dict) else None
        if not isinstance(name, str) or not name:
            _fail(attempt, f"items[{index}] has no metadata.name")
        found.append(item)
    return found


def parse_api_versions(body: Any) -> list[str]:
    if not isinstance(body, dict) or not isinstance(body.get("versions"), list):
        raise MatrixExit(2, "bundle: /api: versions is not a list")
    versions = []
    for index, version in enumerate(body["versions"]):
        if not isinstance(version, str) or not version:
            raise MatrixExit(2, f"bundle: /api: versions[{index}] is not a version name")
        versions.append(version)
    return versions


def parse_api_groups(body: Any) -> list[dict]:
    if not isinstance(body, dict) or not isinstance(body.get("groups"), list):
        raise MatrixExit(2, "bundle: /apis: groups is not a list")
    groups = []
    for index, group in enumerate(body["groups"]):
        if not isinstance(group, dict):
            raise MatrixExit(2, f"bundle: /apis: groups[{index}] is not an object")
        name = group.get("name")
        versions = group.get("versions")
        if not isinstance(name, str) or not name:
            raise MatrixExit(2, f"bundle: /apis: groups[{index}].name is missing")
        if not isinstance(versions, list):
            raise MatrixExit(2, f"bundle: /apis: groups[{index}].versions is not a list")
        parsed = []
        for vindex, version in enumerate(versions):
            if not isinstance(version, dict) or not isinstance(version.get("groupVersion"), str) or not version.get("groupVersion"):
                raise MatrixExit(2, f"bundle: /apis: groups[{index}].versions[{vindex}] is not a version")
            parsed.append(version)
        groups.append({"name": name, "versions": parsed})
    return groups


def parse_resources(body: Any, path: str) -> list[dict]:
    if not isinstance(body, dict) or not isinstance(body.get("resources"), list):
        raise MatrixExit(2, f"bundle: {path}: resources is not a list")
    found = []
    for index, resource in enumerate(body["resources"]):
        if not isinstance(resource, dict):
            raise MatrixExit(2, f"bundle: {path}: resources[{index}] is not an object")
        name = resource.get("name")
        if not isinstance(name, str) or not name:
            raise MatrixExit(2, f"bundle: {path}: resources[{index}].name is missing")
        if not isinstance(resource.get("namespaced"), bool):
            raise MatrixExit(2, f"bundle: {path}: resources[{index}] has no scope")
        verbs = resource.get("verbs")
        if not isinstance(verbs, list) or not all(isinstance(verb, str) for verb in verbs):
            raise MatrixExit(2, f"bundle: {path}: resources[{index}].verbs is not a list")
        if "/" in name:
            parent, sub = name.split("/", 1)
        else:
            parent, sub = name, ""
        found.append(
            {
                "group": "",
                "name": name,
                "namespaced": resource["namespaced"],
                "parent": parent,
                "subresource": sub,
                "verbs": list(verbs),
            }
        )
    return found


def version_paths(api_body: Any, apis_body: Any) -> list[str]:
    paths = [f"/api/{version}" for version in parse_api_versions(api_body)]
    for group in parse_api_groups(apis_body):
        for version in group["versions"]:
            paths.append(f"/apis/{version['groupVersion']}")
    unique = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def last_reads(chosen: dict[str, dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for attempt in chosen.values():
        if attempt["kind"] != "read":
            continue
        grouped.setdefault(attempt["request"]["path"], []).append(attempt)
    return grouped


def response_request_hash(attempt: dict) -> None:
    body = attempt["result"]["body"]
    if isinstance(body, dict) and "request_hash" in body and body["request_hash"] != attempt["request_hash"]:
        _fail(attempt, "response request hash does not match")
