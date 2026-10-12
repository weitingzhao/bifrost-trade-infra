#!/usr/bin/env python3
"""One complete LIST of freezes.release.bifrost.io. No memory, no retry.

Clear only when the status is 200 and the body is one well-formed FreezeList
with an empty items array. Anything else refuses. Exit 0 only for clear.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FREEZE_URL = "https://kubernetes.default.svc/apis/release.bifrost.io/v1/freezes"
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
READ_TIMEOUT_S = 10

API_VERSION = "release.bifrost.io/v1"
LIST_KIND = "FreezeList"

LINE_CLEAR = "未冻结：0 条记录"
LINE_FROZEN = "拒绝：发布已冻结（{n} 条记录）；解冻由 Owner 删除记录：release.sh unfreeze"
LINE_UNREAD = "拒绝：读不到冻结状态（{what}），按冻结处理"

# Closed list, the same tokens as the Go gate. HTTP <code> and
# "item <i> is malformed" are patterns, not entries.
REASON_TOKENS = (
    "timeout",
    "connection failed",
    "context canceled",
    "invalid utf-8",
    "bom",
    "not a JSON object",
    "duplicate key",
    "wrong apiVersion",
    "wrong kind",
    "metadata is not an object",
    "continue is not a string",
    "continue is not empty",
    "items is not a list",
    "missing token",
    "missing CA",
    "corrupt CA",
)


class JObj(dict):
    """Object that remembers the original key sequence, so a repeated key is visible."""

    def __init__(self, pairs: list[tuple[object, object]]) -> None:
        self.keys_seen = [k for k, _ in pairs]
        super().__init__(pairs)

    def duplicated(self) -> bool:
        return len(self.keys_seen) != len(set(self.keys_seen))


@dataclass
class Record:
    name: str
    uid: str
    who: str
    reason: str
    at: str
    via: str


@dataclass
class Decision:
    verdict: str
    reason: str = ""
    records: list[Record] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def decide_transport(token: str) -> Decision:
    return _unread(token)


def decide_http(status: int, body: bytes) -> Decision:
    """The list rule. A status other than 200 does not look at the body."""
    if status != 200:
        return _unread(f"HTTP {status}")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return _unread("invalid utf-8")
    if text.startswith("\ufeff"):
        return _unread("bom")
    try:
        value = json.loads(text, object_pairs_hook=JObj)
    except json.JSONDecodeError:
        return _unread("not a JSON object")
    if not isinstance(value, JObj):
        return _unread("not a JSON object")
    if _watched_dup(value):
        return _unread("duplicate key")
    api = value.get("apiVersion")
    if not isinstance(api, str) or api != API_VERSION:
        return _unread("wrong apiVersion")
    kind = value.get("kind")
    if not isinstance(kind, str) or kind != LIST_KIND:
        return _unread("wrong kind")
    meta = value.get("metadata")
    if not isinstance(meta, JObj):
        return _unread("metadata is not an object")
    if "continue" in meta:
        cont = meta.get("continue")
        if not isinstance(cont, str):
            return _unread("continue is not a string")
        if cont != "":
            return _unread("continue is not empty")
    items = value.get("items")
    if not isinstance(items, list):
        return _unread("items is not a list")
    records: list[Record] = []
    for index, item in enumerate(items):
        rec = _item_record(item)
        if rec is None:
            return _unread(f"item {index} is malformed")
        records.append(rec)
    if not records:
        return Decision(verdict="clear", lines=[LINE_CLEAR])
    records.sort(key=lambda rec: rec.name)
    lines = [LINE_FROZEN.format(n=len(records))]
    for rec in records:
        lines.append(
            f"{rec.name}  who={_flat(rec.who)}  at={_flat(rec.at)}  reason={_flat(rec.reason)}"
        )
    return Decision(verdict="frozen", records=records, lines=lines)


def read_freeze(
    url: str = FREEZE_URL,
    token_path: str = TOKEN_PATH,
    ca_path: str = CA_PATH,
) -> Decision:
    """One HTTPS GET. The URL, token and CA come from the arguments, never from the environment."""
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return _unread("missing token")
    except UnicodeDecodeError:
        return _unread("invalid utf-8")
    except OSError:
        return _unread("missing token")
    if token == "":
        return _unread("missing token")
    if not os.path.isfile(ca_path):
        return _unread("missing CA")
    try:
        ctx = ssl.create_default_context(cafile=ca_path)
    except (ssl.SSLError, OSError):
        return _unread("corrupt CA")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=ctx),
    )
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token}, method="GET")
    try:
        with opener.open(req, timeout=READ_TIMEOUT_S) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            body = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001 — the status is already a refusal
            body = b""
        return decide_http(exc.code, body)
    except (TimeoutError, socket.timeout):
        return _unread("timeout")
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return _unread("timeout")
        if "timed out" in str(reason).lower():
            return _unread("timeout")
        return _unread("connection failed")
    except OSError:
        return _unread("connection failed")
    return decide_http(status, body)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is not a successful list. One attempt, then the 3xx status."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        return None


def main() -> int:
    found = read_freeze()
    lines = list(found.lines)
    if found.verdict == "clear":
        path = os.environ.get("PASSED_CUT_AT_PATH", "")
        if path:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            lines.append(stamp)
            Path(path).write_text(stamp + "\n", encoding="utf-8")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0 if found.verdict == "clear" else 1


def _unread(what: str) -> Decision:
    return Decision(verdict="unreadable", reason=what, lines=[LINE_UNREAD.format(what=what)])


def _flat(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def _watched_dup(top: JObj) -> bool:
    if top.duplicated():
        return True
    meta = top.get("metadata")
    if isinstance(meta, JObj) and meta.duplicated():
        return True
    items = top.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, JObj):
            continue
        if item.duplicated():
            return True
        item_meta = item.get("metadata")
        if isinstance(item_meta, JObj) and item_meta.duplicated():
            return True
    return False


def _item_record(item: object) -> Record | None:
    if not isinstance(item, JObj):
        return None
    meta = item.get("metadata")
    if not isinstance(meta, JObj):
        return None
    name = meta.get("name")
    if not isinstance(name, str) or name == "":
        return None
    uid = meta.get("uid")
    uid_s = uid if isinstance(uid, str) else ""
    spec = item.get("spec")
    spec_o = spec if isinstance(spec, JObj) else None
    via = ""
    if spec_o is not None and isinstance(spec_o.get("via"), str):
        via = spec_o["via"]
    return Record(
        name=name,
        uid=uid_s,
        who=_field_or_q(spec_o, "who"),
        reason=_field_or_q(spec_o, "reason"),
        at=_field_or_q(spec_o, "at"),
        via=via,
    )


def _field_or_q(spec: JObj | None, key: str) -> str:
    if spec is None:
        return "?"
    value = spec.get(key)
    if not isinstance(value, str):
        return "?"
    return value


if __name__ == "__main__":
    sys.exit(main())
