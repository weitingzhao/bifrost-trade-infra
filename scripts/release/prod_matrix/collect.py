"""Collect discovery, identities, and explicit SubjectAccessReviews via kubectl.

This module is the only one that starts a process. Replay does not import it.
Concurrency stays at one in-flight request, under the cap of 8. Each request is
one attempt. A retried request is a new attempt. Pages are not folded together.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable
from attempts import seal_result
from canon import READ_LIMIT, TOOL_VERSION, WALL_SECONDS, MatrixExit, sha256_hex
from identities import context, discovery_paths_from

Transport = Callable[[str, str, str | None], tuple[int, str, str]]

LISTS = (
    ("/api/v1/namespaces", "", "namespaces"),
    ("/api/v1/serviceaccounts", "", "serviceaccounts"),
    ("/api/v1/nodes", "", "nodes"),
    ("/apis/rbac.authorization.k8s.io/v1/roles", "rbac.authorization.k8s.io", "roles"),
    ("/apis/rbac.authorization.k8s.io/v1/rolebindings", "rbac.authorization.k8s.io", "rolebindings"),
    ("/apis/rbac.authorization.k8s.io/v1/clusterroles", "rbac.authorization.k8s.io", "clusterroles"),
    ("/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", "rbac.authorization.k8s.io", "clusterrolebindings"),
)
SAR_PATH = "/apis/authorization.k8s.io/v1/subjectaccessreviews"


def kubectl_transport(method: str, path: str, body: str | None) -> tuple[int, str, str]:
    if method == "WHOAMI":
        command = ["kubectl", "auth", "whoami", "-o", "json"]
        data = None
    elif method == "GET":
        command = ["kubectl", "get", "--raw", path]
        data = None
    else:
        command = ["kubectl", "create", "--raw", path, "-f", "-"]
        data = body
    try:
        proc = subprocess.run(command, input=data, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except OSError as exc:
        return 1, "", f"connection {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(code: int, stdout: str, stderr: str) -> tuple[int, Any, bool]:
    """Return HTTP status, parsed JSON or None, and whether to retry."""
    if code == 0:
        try:
            return 200, json.loads(stdout), False
        except json.JSONDecodeError:
            return 200, {"raw": stdout}, False
    text = f"{stderr}\n{stdout}"
    if "timeout" in text or "connection " in text:
        return 0, None, True
    mapping = (
        ("Gone", 410, False),
        ("Too Many Requests", 429, True),
        ("Service Unavailable", 503, True),
        ("Internal Server Error", 500, True),
        ("Forbidden", 403, False),
    )
    for marker, status, retry in mapping:
        if marker in text:
            try:
                payload = json.loads(stdout) if stdout.strip() else None
            except json.JSONDecodeError:
                payload = None
            return status, payload, retry
    if any(token in text for token in (" 502", " 504", "Bad Gateway", "Gateway Timeout")):
        return 502, None, True
    return 400, None, False


class Session:
    def __init__(self, transport: Transport, wall_seconds: float = WALL_SECONDS) -> None:
        self.transport = transport
        self.wall_seconds = wall_seconds
        self.attempts: list[dict] = []
        self.reads = 0
        self.questions_sent = 0
        self.seq = 1
        self.started: float | None = None
        self.started_at = _now()
        self.clock = time.monotonic

    def _tick(self) -> None:
        now = self.clock()
        if self.started is None:
            self.started = now
            return
        if now - self.started > self.wall_seconds:
            raise MatrixExit(2, "budget: wall clock exceeded")

    def _note(self, bucket: str) -> None:
        if bucket == "read":
            self.reads += 1
            if self.reads > READ_LIMIT:
                raise MatrixExit(2, "budget: read limit")
        else:
            self.questions_sent += 1
            if self.questions_sent > 20000:
                raise MatrixExit(2, "budget: question limit")

    def call(self, method: str, path: str, body: str | None, bucket: str, params: dict | None = None) -> tuple[int, Any]:
        params = {} if params is None else params
        if bucket == "read" and self.reads >= READ_LIMIT:
            raise MatrixExit(2, "budget: read limit")
        if bucket == "review" and self.questions_sent >= 20000:
            raise MatrixExit(2, "budget: question limit")
        payload = None
        status = 0
        first = 0
        stored_method = "GET" if method in {"GET", "WHOAMI"} else "POST"
        request: dict[str, Any] = {"method": stored_method, "params": params, "path": path}
        if stored_method == "POST":
            request["body"] = json.loads(body) if isinstance(body, str) else body
        for retry_index in range(3):
            self._tick()
            self._note(bucket)
            code, stdout, stderr = self.transport(method, path, body)
            self._tick()
            status, payload, retry = _status(code, stdout, stderr)
            number = self.seq
            self.seq += 1
            if retry_index == 0:
                first = number
            kind = "review" if bucket == "review" else "read"
            digest = sha256_hex(request["body"]["spec"]) if kind == "review" else sha256_hex(request)
            record = {
                "attempt": number,
                "finished_at": _now(),
                "kind": kind,
                "request": request,
                "request_hash": digest,
                "result": seal_result(payload, status == 200, status or 0),
                "started_at": _now(),
            }
            if retry_index:
                record["retry_of"] = first
            self.attempts.append(record)
            if status == 200:
                return number, payload
            if not retry or retry_index == 2:
                break
        raise MatrixExit(2, f"bundle: attempt {first}: read failed ({status})")


def _attrs(verb: str, group: str, resource: str) -> dict:
    return {
        "group": group,
        "name": "",
        "namespace": "",
        "resource": resource,
        "subresource": "",
        "verb": verb,
        "version": "v1",
    }


def _self_check(session: Session, verb: str, group: str, resource: str) -> None:
    body = {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": _attrs(verb, group, resource)},
    }
    _, payload = session.call("POST", "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews", json.dumps(body), "read")
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict) or status.get("allowed") is not True:
        raise MatrixExit(2, f"self-check: {verb} {resource} is not allowed")


def _paged(session: Session, path: str) -> None:
    token = ""
    while True:
        params = {"limit": "500"}
        if token:
            params["continue"] = token
        _, payload = session.call("GET", path, None, "read", params=params)
        if not isinstance(payload, dict):
            raise MatrixExit(2, f"bundle: {path}: list is not an object")
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        token = str(meta.get("continue") or "")
        if not token:
            return


def _caller(payload: dict) -> dict:
    status = payload.get("status") if isinstance(payload, dict) else None
    info = status.get("userInfo") if isinstance(status, dict) else None
    if not isinstance(info, dict):
        info = payload if isinstance(payload, dict) else {}
    user = str(info.get("username") or info.get("user") or "")
    if not user:
        raise MatrixExit(2, "whoami: missing username")
    groups = [str(item) for item in info.get("groups") or []]
    if info.get("uid"):
        uid = {"state": "known", "value": str(info["uid"])}
    else:
        uid = {"state": "unknown"}
    extra_raw = info.get("extra")
    if isinstance(extra_raw, dict):
        extra = {"state": "known", "value": {key: [str(part) for part in value] for key, value in extra_raw.items()}}
    else:
        extra = {"state": "unknown"}
    kind = "serviceaccount" if user.startswith("system:serviceaccount:") else "user"
    return context(kind, user, groups, uid, extra, "kubectl-auth-whoami")


def read_identities(transport: Transport, wall_seconds: float = WALL_SECONDS) -> tuple[Session, dict]:
    """Whoami, self-checks, and identity lists. No discovery and no SubjectAccessReview."""
    session = Session(transport, wall_seconds)
    _, who = session.call("WHOAMI", "/apis/authentication.k8s.io/v1/selfsubjectreviews", None, "read")
    caller = _caller(who if isinstance(who, dict) else {})
    for path, group, resource in LISTS:
        _self_check(session, "list", group, resource)
        _paged(session, path)
    return session, caller


def read_discovery(session: Session) -> None:
    """Root discovery, then every served version. Stops before any review is sent."""
    _, api = session.call("GET", "/api", None, "read")
    _, apis = session.call("GET", "/apis", None, "read")
    for path in discovery_paths_from(api if isinstance(api, dict) else {}, apis if isinstance(apis, dict) else {}):
        _paged(session, path)


def read_inventory(transport: Transport, wall_seconds: float = WALL_SECONDS) -> tuple[Session, dict]:
    """Whoami, self-checks, lists, and discovery. No SubjectAccessReview yet."""
    session, caller = read_identities(transport, wall_seconds)
    read_discovery(session)
    return session, caller


def send_questions(session: Session, caller: dict, planned: list[dict]) -> dict:
    from questions import sar_body

    if len({item["id"] for item in planned}) != len(planned):
        raise MatrixExit(2, "bundle: duplicate question id")
    _self_check(session, "create", "authorization.k8s.io", "subjectaccessreviews")
    for item in planned:
        _, payload = session.call("POST", SAR_PATH, json.dumps(sar_body(item["spec"])), "review")
        if not isinstance(payload, dict):
            raise MatrixExit(2, f"bundle: {item['id']}: malformed response")
    return {
        "attempts": session.attempts,
        "caller": caller,
        "finished_at": _now(),
        "schema_version": 1,
        "started_at": session.started_at,
        "tool_version": TOOL_VERSION,
    }


def announce_count(count: int) -> str:
    from canon import QUESTION_LIMIT

    return f"question count: {count}; limit {QUESTION_LIMIT}"
