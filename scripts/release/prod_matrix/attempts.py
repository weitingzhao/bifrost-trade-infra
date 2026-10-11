"""One attempt per request. Replay keeps a single chain for each request hash.

A page is its own read (path plus continue). The collector does not merge attempts.
The result body is stored verbatim; body_sha256 is the canonical digest of that body,
so a one-node edit of the body cannot replay as a smaller inventory.
"""

from __future__ import annotations

from typing import Any

from canon import QUESTION_LIMIT, READ_LIMIT, MatrixExit, sha256_hex

# One declaration of the reads and reviews the collector sends. Replay accepts only these.
IDENTITY_LISTS = (
    ("/api/v1/namespaces", "", "namespaces"),
    ("/api/v1/serviceaccounts", "", "serviceaccounts"),
    ("/api/v1/nodes", "", "nodes"),
    ("/apis/rbac.authorization.k8s.io/v1/roles", "rbac.authorization.k8s.io", "roles"),
    ("/apis/rbac.authorization.k8s.io/v1/rolebindings", "rbac.authorization.k8s.io", "rolebindings"),
    ("/apis/rbac.authorization.k8s.io/v1/clusterroles", "rbac.authorization.k8s.io", "clusterroles"),
    ("/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", "rbac.authorization.k8s.io", "clusterrolebindings"),
)
LIST_PATHS = tuple(path for path, _group, _resource in IDENTITY_LISTS)
SAR_PATH = "/apis/authorization.k8s.io/v1/subjectaccessreviews"
SSAR_PATH = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
WHOAMI_PATH = "/apis/authentication.k8s.io/v1/selfsubjectreviews"
PAGE_LIMIT = "500"
AUTHZ_VERSION = "authorization.k8s.io/v1"


def seal_result(body: Any, ok: bool, status_code: int) -> dict:
    return {"body": body, "body_sha256": sha256_hex(body), "ok": ok, "status_code": status_code}


def group_result(attempt: dict) -> Any:
    """Body of a group's last attempt, and only when that attempt is ok with a 2xx status.

    Otherwise the group has no result: exit 2, naming the request. No kind is exempt.
    Callers interpret a response body only by calling this function. The seal check
    hashes the stored bytes; it does not interpret them.
    """
    result = attempt.get("result")
    if not isinstance(result, dict):
        _fail(attempt, "missing result")
    ok = result.get("ok", None)
    status = result.get("status_code", None)
    kind = "review" if attempt.get("kind") == "review" else "read"
    if ok is not True or isinstance(status, bool) or not isinstance(status, int) or status < 200 or status > 299:
        _fail(attempt, f"{kind} failed ({status})")
    if "body" not in result:
        _fail(attempt, f"{kind} has no body")
    return result["body"]


def self_check_body(verb: str, group: str, resource: str) -> dict:
    """The SelfSubjectAccessReview the collector posts before a list or a review."""
    return {
        "apiVersion": AUTHZ_VERSION,
        "kind": "SelfSubjectAccessReview",
        "spec": {
            "resourceAttributes": {
                "group": group,
                "name": "",
                "namespace": "",
                "resource": resource,
                "subresource": "",
                "verb": verb,
                "version": "v1",
            }
        },
    }


def collector_self_checks() -> tuple[dict, ...]:
    bodies = [self_check_body("list", group, resource) for _path, group, resource in IDENTITY_LISTS]
    bodies.append(self_check_body("create", "authorization.k8s.io", "subjectaccessreviews"))
    return tuple(bodies)


def canonical_path(path: str) -> bool:
    """Absolute and canonical: a leading slash, no trailing slash, no empty or dot segment, no query."""
    if not isinstance(path, str) or not path.startswith("/") or path.endswith("/"):
        return False
    if "?" in path or "#" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts[1:])


def is_group_version(path: str) -> bool:
    """A discovery document: /api/<version> or /apis/<group>/<version>. The path must be canonical."""
    if not canonical_path(path):
        return False
    parts = path.split("/")
    if len(parts) == 3 and parts[1] == "api":
        return True
    return len(parts) == 4 and parts[1] == "apis"


def is_namespaced_list(path: str) -> bool:
    """One resource listed inside one namespace. The collector does not send this shape."""
    if not canonical_path(path):
        return False
    parts = path.split("/")
    if len(parts) == 6 and parts[1] == "api" and parts[3] == "namespaces":
        return True
    return len(parts) == 7 and parts[1] == "apis" and parts[4] == "namespaces"


def is_paged_path(path: str) -> bool:
    return path in LIST_PATHS or is_group_version(path) or is_namespaced_list(path)


def continue_token(body: Any, attempt: dict | None = None) -> str:
    """The continue field, type-checked before any emptiness check. 0 is not an empty token."""

    def fail(message: str) -> None:
        if attempt is not None:
            _fail(attempt, message)
        raise MatrixExit(2, f"bundle: {message}")

    if not isinstance(body, dict):
        fail("body is not an object")
    if "metadata" not in body or body.get("metadata") is None:
        return ""
    meta = body["metadata"]
    if not isinstance(meta, dict):
        fail("metadata is not an object")
    if "continue" not in meta:
        return ""
    token = meta["continue"]
    if not isinstance(token, str):
        fail("continue is not a string")
    return token


def request_continue(attempt: dict) -> str:
    params = attempt["request"].get("params")
    if params is None:
        return ""
    if not isinstance(params, dict):
        _fail(attempt, "params is not an object")
    if "continue" not in params:
        return ""
    token = params["continue"]
    if not isinstance(token, str):
        _fail(attempt, "continue is not a string")
    return token


def reseal(attempt: dict) -> dict:
    """Recompute hashes after a test edits the request or the body on purpose."""
    result = attempt["result"]
    result["body_sha256"] = sha256_hex(result["body"])
    if attempt["kind"] == "review":
        attempt["request_hash"] = sha256_hex(attempt["request"]["body"]["spec"])
    else:
        attempt["request_hash"] = sha256_hex(attempt["request"])
    return attempt


def _request_name(attempt: dict) -> str:
    request = attempt.get("request") if isinstance(attempt.get("request"), dict) else {}
    method = request.get("method") if isinstance(request.get("method"), str) else "?"
    raw = request.get("path")
    path = raw if isinstance(raw, str) and raw else "(empty path)"
    return f"{method} {path}"


def _fail(attempt: dict, message: str) -> None:
    number = attempt.get("attempt", "?")
    raise MatrixExit(2, f"bundle: attempt {number}: {_request_name(attempt)}: {message}")


def not_implied(attempt: dict) -> None:
    """The group is a well-formed request this inventory does not imply."""
    _fail(attempt, "not implied by this inventory")


def _empty_params(attempt: dict, params: Any) -> None:
    if not isinstance(params, dict):
        _fail(attempt, "params is not an object")
    if params:
        _fail(attempt, "params are not the ones the collector sends")


def _page_params(attempt: dict, params: Any) -> None:
    if not isinstance(params, dict):
        _fail(attempt, "params is not an object")
    keys = set(params)
    if keys not in ({"limit"}, {"limit", "continue"}):
        _fail(attempt, "page parameters must be limit=500 and an optional continue token")
    if params.get("limit") != PAGE_LIMIT:
        _fail(attempt, "page parameters must be limit=500 and an optional continue token")
    if "continue" in params:
        token = params["continue"]
        if not isinstance(token, str) or not token:
            _fail(attempt, "continue is not a page token")


def check_request(attempt: dict) -> None:
    """Bind a recorded attempt to the method, endpoint, and parameters the collector sends.

    A review is a POST to the SubjectAccessReview endpoint. A self-review goes to its
    own endpoint. A read is a GET of a discovery root, a group-version, or a list with
    the collector's page parameters. The path is absolute and canonical. Which
    group-version documents this inventory implies is checked once root discovery is
    read; shape alone does not accept them. The request hash is not changed here.
    """
    request = attempt.get("request")
    if not isinstance(request, dict):
        _fail(attempt, "missing request")
    method = request.get("method")
    path = request.get("path")
    params = request.get("params")
    body = request.get("body") if "body" in request else None
    body_kind = body.get("kind") if isinstance(body, dict) else None
    kind = attempt.get("kind")
    if kind == "review" or body_kind == "SubjectAccessReview" or path == SAR_PATH:
        if kind != "review" or method != "POST" or path != SAR_PATH:
            _fail(attempt, f"review is not POST {SAR_PATH}")
        _empty_params(attempt, params)
        if not isinstance(body, dict) or body.get("apiVersion") != AUTHZ_VERSION or body_kind != "SubjectAccessReview":
            _fail(attempt, "review body is not a SubjectAccessReview")
        return
    if body_kind == "SelfSubjectAccessReview" or path == SSAR_PATH:
        if kind != "read" or method != "POST" or path != SSAR_PATH:
            _fail(attempt, f"self-review is not POST {SSAR_PATH}")
        _empty_params(attempt, params)
        if body not in collector_self_checks():
            _fail(attempt, "self-review is not one the collector sends")
        return
    if body_kind == "SelfSubjectReview" or path == WHOAMI_PATH:
        if kind != "read" or method != "GET" or path != WHOAMI_PATH or "body" in request:
            _fail(attempt, f"whoami is not GET {WHOAMI_PATH}")
        _empty_params(attempt, params)
        return
    if kind != "read" or method != "GET" or not isinstance(path, str):
        _fail(attempt, "read is not GET")
    if not canonical_path(path):
        _fail(attempt, "path is not canonical")
    if path in {"/api", "/apis"}:
        _empty_params(attempt, params)
        return
    if is_paged_path(path):
        _page_params(attempt, params)
        return
    _fail(attempt, "read path is not one the collector can produce")


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
        check_request(attempt)
        return
    if attempt.get("kind") != "read":
        _fail(attempt, "kind is not read or review")
    if sha256_hex(request) != attempt.get("request_hash"):
        _fail(attempt, "request hash does not match")
    check_request(attempt)


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
    if sorted(numbers) != list(range(1, len(attempts) + 1)):
        raise MatrixExit(2, "bundle: attempt numbers are not 1..n")
    if [item.get("attempt") for item in attempts] != list(range(1, len(attempts) + 1)):
        raise MatrixExit(2, "bundle: attempts are not in order")
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
    # Every group, including whoami and the permission self-checks. No caller picks which ones matter.
    for attempt in chosen.values():
        group_result(attempt)
    return chosen


def pages_for(attempts: list[dict], path: str) -> list[dict]:
    """Walk the continue chain. A repeated or missing page is exit 2."""
    by_token: dict[str, dict] = {}
    for attempt in attempts:
        if attempt.get("kind") != "read" or attempt["request"]["path"] != path:
            continue
        token = request_continue(attempt)
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
        body = group_result(attempt)
        ordered.append(attempt)
        nxt = continue_token(body, attempt)
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


def _first(group: list[dict]) -> dict:
    return min(group, key=lambda item: item["attempt"])


def assert_implied_reads(reads: dict[str, list[dict]], discovery_paths: list[str]) -> None:
    """Request groups for reads equal the set this inventory implies.

    Discovery paths are exactly the versions named by the recorded /api and /apis
    documents. List requests are exactly the continue chain of each collector list:
    the first page is limit=500, and each later page carries the previous body's
    continue token. Whoami and the permission self-checks are the collector's fixed
    preamble. Any other read, including a version the root did not name and a list of
    a resource inside a namespace, is exit 2 naming the request.
    """
    allowed = set(discovery_paths) | set(LIST_PATHS) | {"/api", "/apis", WHOAMI_PATH, SSAR_PATH}
    for path in sorted(reads):
        if path not in allowed:
            not_implied(_first(reads[path]))
    for path in list(discovery_paths) + list(LIST_PATHS):
        pages = pages_for(reads.get(path, []), path)
        token = ""
        for attempt in pages:
            expected = {"limit": PAGE_LIMIT}
            if token:
                expected["continue"] = token
            if attempt["request"].get("params") != expected:
                not_implied(attempt)
            token = continue_token(group_result(attempt), attempt)


def last_reads(chosen: dict[str, dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for attempt in chosen.values():
        if attempt["kind"] != "read":
            continue
        grouped.setdefault(attempt["request"]["path"], []).append(attempt)
    return grouped


def response_request_hash(attempt: dict, body: Any) -> None:
    """body comes from group_result. This does not read the stored body itself."""
    if isinstance(body, dict) and "request_hash" in body and body["request_hash"] != attempt["request_hash"]:
        _fail(attempt, "response request hash does not match")
