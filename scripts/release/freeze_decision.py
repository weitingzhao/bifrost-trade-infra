#!/usr/bin/env python3
"""Fail-closed read of ConfigMap cicd/bifrost-release-freeze (W-56 step 1, slice B).

Allow only a successfully read object whose data matches one unfrozen shape
and whose frozen value is the string "false". Anything else refuses.
Slice C verifies the un-freeze signature; this file only reserves the shape.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FREEZE_URL = (
    "https://kubernetes.default.svc/api/v1/namespaces/cicd/configmaps/bifrost-release-freeze"
)
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
READ_TIMEOUT_S = 10

REFUSE_FROZEN = "拒绝：发布已冻结（{reason}，{frozen_at}）；解冻要 Owner 签名"
REFUSE_UNREADABLE = "拒绝：读不到冻结状态（{what}），按冻结处理"
ALLOW_PREFIX = "未冻结："

# SLICE C EXTENSION POINT.
# A frozen="false" object whose seq is not "0" must carry the unfreeze fields
# named in freeze_schema.json. This slice accepts that object and prints
# SLICE_C_NOTE. It does not check the signature, the seq binding, or replay.
# Do not add a partial verification here.
SLICE_C_NOTE = "note: un-freeze signature not verified (slice C)"


class ReadError:
    """The ConfigMap was not read as a JSON object. `what` fills the refusal line."""

    def __init__(self, what: str) -> None:
        self.what = what


def schema() -> dict:
    path = Path(__file__).resolve().parent / "freeze_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def checked_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unread(what: str) -> tuple[bool, str]:
    return False, REFUSE_UNREADABLE.format(what=what)


def _seq_ok(value: str) -> bool:
    return re.fullmatch(schema()["seq_pattern"], value) is not None


def decide(object_or_error: object) -> tuple[bool, str]:
    """Return (allow, first output line). Allow only the two unfrozen shapes."""
    if isinstance(object_or_error, ReadError):
        return _unread(object_or_error.what)
    if not isinstance(object_or_error, dict):
        return _unread("unparsable response")

    data = object_or_error
    for key in sorted(data):
        if not isinstance(data[key], str):
            return _unread(f"field {key} is not a string")
    if "frozen" not in data:
        return _unread("missing field frozen")
    frozen = data["frozen"]
    if frozen not in ("true", "false"):
        return _unread('frozen is not "true" or "false"')

    spec = schema()
    if frozen == "true":
        return _decide_frozen(data, spec)
    return _decide_unfrozen(data, spec)


def _decide_frozen(data: dict, spec: dict) -> tuple[bool, str]:
    shape = _shape_error(data, spec["frozen_fields"], spec["frozen_nonempty"])
    if shape:
        return _unread(shape)
    if not _seq_ok(data["seq"]):
        return _unread("field seq is not a decimal string")
    if data["seq"] == "0":
        return _unread("field seq is 0 while frozen")
    line = REFUSE_FROZEN.format(reason=data["reason"], frozen_at=data["frozen_at"])
    return False, line


def _decide_unfrozen(data: dict, spec: dict) -> tuple[bool, str]:
    initial = spec["initial"]
    if set(data) == set(initial) and all(data[key] == value for key, value in initial.items()):
        return True, ALLOW_PREFIX + checked_at()

    # Any other frozen=false object must be the full unfrozen shape.
    # SLICE C EXTENSION POINT: presence only, no signature check.
    shape = _shape_error(data, spec["unfrozen_fields"], spec["unfrozen_nonempty"])
    if shape:
        return _unread(shape)
    if not _seq_ok(data["seq"]):
        return _unread("field seq is not a decimal string")
    if data["seq"] == "0":
        return _unread("field seq is 0 on an unfrozen object")
    return True, ALLOW_PREFIX + checked_at()


def _shape_error(data: dict, fields: list[str], nonempty: list[str]) -> str:
    keys = set(data)
    expected = set(fields)
    extra = sorted(keys - expected)
    if extra:
        return f"unknown field {extra[0]}"
    missing = sorted(expected - keys)
    if missing:
        return f"missing field {missing[0]}"
    for name in nonempty:
        if data[name] == "":
            return f"missing field {name}"
    return ""


def slice_c_note(object_or_error: object) -> bool:
    """True when the allow path is the unfrozen shape, not the initial object."""
    if not isinstance(object_or_error, dict):
        return False
    return "unfreeze_seq" in object_or_error


def render(object_or_error: object) -> tuple[int, str]:
    """Exit code and stdout. The first line is the decision; the note is second."""
    allow, line = decide(object_or_error)
    lines = [line]
    if allow and slice_c_note(object_or_error):
        lines.append(SLICE_C_NOTE)
    return (0 if allow else 1), "\n".join(lines) + "\n"


def data_from_envelope(doc: object) -> ReadError | dict:
    if not isinstance(doc, dict):
        return ReadError("unparsable response")
    kind = doc.get("kind")
    if kind not in (None, "ConfigMap"):
        return ReadError("unparsable response")
    data = doc.get("data")
    if not isinstance(data, dict):
        return ReadError("unparsable response")
    return data


def failure_from_http(exc: BaseException) -> ReadError:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return ReadError("404")
        return ReadError(f"HTTP {exc.code}")
    if isinstance(exc, http.client.IncompleteRead):
        return ReadError("truncated body")
    if isinstance(exc, UnicodeDecodeError):
        return ReadError("invalid UTF-8")
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ReadError("timeout")
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return ReadError("timeout")
        if "timed out" in str(reason).lower():
            return ReadError("timeout")
        return ReadError(f"HTTP transport ({type(reason).__name__})")
    if isinstance(exc, json.JSONDecodeError):
        return ReadError("unparsable response")
    if isinstance(exc, FileNotFoundError):
        return ReadError("missing CA")
    return ReadError(f"read error ({type(exc).__name__})")


def _load_freeze() -> ReadError | dict:
    if not os.path.exists(TOKEN_PATH):
        return ReadError("no service account token")
    try:
        token = Path(TOKEN_PATH).read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        return failure_from_http(exc)
    except OSError as exc:
        return ReadError(f"read error ({type(exc).__name__})")
    if not os.path.exists(CA_PATH):
        return ReadError("missing CA")
    try:
        ctx = ssl.create_default_context(cafile=CA_PATH)
    except ssl.SSLError:
        return ReadError("corrupt CA")
    except OSError as exc:
        return failure_from_http(exc)
    req = urllib.request.Request(FREEZE_URL, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=READ_TIMEOUT_S) as resp:
            raw_bytes = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, http.client.IncompleteRead) as exc:
        return failure_from_http(exc)
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return failure_from_http(exc)
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        return failure_from_http(exc)
    return data_from_envelope(doc)


def load_freeze() -> ReadError | dict:
    """Read the ConfigMap. Every read or decode failure is a ReadError, never a traceback."""
    try:
        return _load_freeze()
    except Exception as exc:  # noqa: BLE001 — fail closed; the refusal line is the output
        return failure_from_http(exc)


def main() -> int:
    found = load_freeze()
    code, text = render(found)
    sys.stdout.write(text)
    if code == 0:
        path = os.environ.get("PASSED_CUT_AT_PATH", "")
        if path:
            stamp = text.split("\n", 1)[0].split("：", 1)[1]
            Path(path).write_text(stamp, encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
