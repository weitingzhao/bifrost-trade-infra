"""Collect discovery, identities, and explicit SubjectAccessReviews via kubectl.

This module is the only one that starts a process. Replay does not import it.
Concurrency stays at one in-flight request, under the cap of 8, so the bundle
order matches the question order. Retries are separate command records.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from canon import READ_LIMIT, TOOL_VERSION, WALL_SECONDS, MatrixExit
from identities import context
from questions import sar_body

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
        self.commands: list[dict] = []
        self.reviews: list[dict] = []
        self.reads = 0
        self.questions_sent = 0
        self.seq = 1
        self.started: float | None = None
        self.started_at = _now()

    def _tick(self) -> None:
        now = time.monotonic()
        if self.started is None:
            self.started = now
            return
        if now - self.started > self.wall_seconds:
            raise MatrixExit(2, "budget: wall clock exceeded")

    def _budget(self, bucket: str) -> None:
        if bucket == "read" and self.reads >= READ_LIMIT:
            raise MatrixExit(2, "budget: read limit")
        if bucket == "question" and self.questions_sent >= 20000:
            raise MatrixExit(2, "budget: question limit")

    def call(self, method: str, path: str, body: str | None, bucket: str) -> tuple[str, Any]:
        self._budget(bucket)
        logical = f"c-{self.seq:04d}"
        self.seq += 1
        payload = None
        status = 0
        for attempt in range(3):
            self._tick()
            if bucket == "read":
                self.reads += 1
            else:
                self.questions_sent += 1
            self._budget_after_increment(bucket)
            code, stdout, stderr = self.transport(method, path, body)
            status, payload, retry = _status(code, stdout, stderr)
            token = ""
            if isinstance(payload, dict):
                token = str((payload.get("metadata") or {}).get("continue") or "")
            entry = {
                "id": logical if attempt == 0 else f"{logical}-r{attempt}",
                "request": {"method": "GET" if method in {"GET", "WHOAMI"} else "POST", "path": path, "params": {}},
                "pages": [{"body": payload if isinstance(payload, dict) else {"empty": True}, "continue": token}],
                "ok": status == 200,
                "status_code": status or 0,
                "started_at": _now(),
                "finished_at": _now(),
            }
            if attempt:
                entry["retry_of"] = logical
            self.commands.append(entry)
            if status == 200:
                return logical, payload
            if not retry or attempt == 2:
                break
        raise MatrixExit(2, f"bundle: {logical}: read failed ({status})")

    def _budget_after_increment(self, bucket: str) -> None:
        if bucket == "read" and self.reads > READ_LIMIT:
            raise MatrixExit(2, "budget: read limit")
        if bucket == "question" and self.questions_sent > 20000:
            raise MatrixExit(2, "budget: question limit")


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
    _, payload = session.call(
        "POST",
        "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
        json.dumps(body),
        "read",
    )
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict) or status.get("allowed") is not True:
        raise MatrixExit(2, f"self-check: {verb} {resource} is not allowed")


def _paged(session: Session, path: str) -> dict:
    pages: list[dict] = []
    token = ""
    logical_id = ""
    while True:
        params = {"limit": "500"}
        if token:
            params["continue"] = token
        full = path + "?" + urlencode(params)
        logical_id, payload = session.call("GET", full, None, "read")
        if not isinstance(payload, dict):
            raise MatrixExit(2, f"bundle: {logical_id}: list is not an object")
        continue_token = str((payload.get("metadata") or {}).get("continue") or "")
        pages.append({"body": payload, "continue": continue_token})
        if not continue_token:
            break
        token = continue_token
    # Fold successful page calls into one list command and drop the per-page copies
    # that call() already stored, replacing them with a single paged record.
    page_ids = []
    kept = []
    for command in session.commands:
        if command["request"]["path"].split("?", 1)[0] == path and not command.get("retry_of"):
            page_ids.append(command["id"])
        else:
            kept.append(command)
    if not page_ids:
        raise MatrixExit(2, f"bundle: missing command {path}")
    folded = {
        "id": page_ids[0],
        "request": {"method": "GET", "path": path, "params": {"limit": "500"}},
        "pages": pages,
        "ok": True,
        "status_code": 200,
        "started_at": _now(),
        "finished_at": _now(),
    }
    session.commands = kept + [folded]
    return folded


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


def _discovery_paths(api: Any, apis: Any) -> list[str]:
    paths = []
    versions = api.get("versions") if isinstance(api, dict) else []
    for version in versions or []:
        paths.append(f"/api/{version}")
    groups = apis.get("groups") if isinstance(apis, dict) else []
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        preferred = group.get("preferredVersion") or {}
        group_version = preferred.get("groupVersion")
        if group_version:
            paths.append(f"/apis/{group_version}")
    return paths


def read_inventory(transport: Transport, wall_seconds: float = WALL_SECONDS) -> tuple[Session, dict]:
    """Whoami, self-checks, lists, and discovery. No SubjectAccessReview yet."""
    session = Session(transport, wall_seconds)
    _, who = session.call("WHOAMI", "/apis/authentication.k8s.io/v1/selfsubjectreviews", None, "read")
    caller = _caller(who if isinstance(who, dict) else {})
    for path, group, resource in LISTS:
        _self_check(session, "list", group, resource)
        _paged(session, path)
    _self_check(session, "create", "authorization.k8s.io", "subjectaccessreviews")
    _, api = session.call("GET", "/api", None, "read")
    _, apis = session.call("GET", "/apis", None, "read")
    for path in _discovery_paths(api, apis):
        _paged(session, path)
    return session, caller


def send_questions(session: Session, caller: dict, planned: list[dict]) -> dict:
    return _finish(session, caller, planned)


def _finish(session: Session, caller: dict, planned: list[dict]) -> dict:
    if len({item["id"] for item in planned}) != len(planned):
        raise MatrixExit(2, "bundle: duplicate question id")
    for item in planned:
        body = sar_body(item["spec"])
        _, payload = session.call(
            "POST",
            "/apis/authorization.k8s.io/v1/subjectaccessreviews",
            json.dumps(body),
            "question",
        )
        if not isinstance(payload, dict):
            raise MatrixExit(2, f"bundle: {item['id']}: malformed response")
        response = dict(payload)
        response["request_hash"] = item["request_hash"]
        session.reviews.append(
            {
                "id": item["id"],
                "request": body,
                "request_hash": item["request_hash"],
                "response": response,
            }
        )
    if session.questions_sent != len(planned):
        # Retries increment questions_sent above the planned count. That is allowed.
        pass
    bundle = {
        "caller": caller,
        "commands": session.commands,
        "finished_at": _now(),
        "reviews": sorted(session.reviews, key=lambda item: item["id"]),
        "schema_version": 1,
        "started_at": session.started_at,
        "tool_version": TOOL_VERSION,
    }
    return bundle


def announce_count(count: int) -> str:
    from canon import QUESTION_LIMIT

    return f"question count: {count}; limit {QUESTION_LIMIT}"
