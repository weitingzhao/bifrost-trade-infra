#!/usr/bin/env python3
"""One LIST of freezes.release.bifrost.io. Clear is membership in L over HTTP/1.1.

The recogniser follows the productions in design §3.2. It does not call json
on that path. Anything recoverable is not clear. Exit 0 only for clear.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FREEZE_URL = "https://kubernetes.default.svc/apis/release.bifrost.io/v1/freezes"
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
READ_TIMEOUT_S = 10
LIST_PATH = "/apis/release.bifrost.io/v1/freezes"
ORIGIN_HOST = "kubernetes.default.svc"

LINE_CLEAR = "未冻结：0 条记录"
LINE_FROZEN = "拒绝：发布已冻结（{n} 条记录）；解冻由 Owner 删除记录：release.sh unfreeze"
LINE_UNREAD = "拒绝：读不到冻结状态（{what}），按冻结处理"

MIN_DIGITS = 1
MAX_DIGITS = 32
MAX_BODY = 4096


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


def _is_w(c: int) -> bool:
    return c == 0x20 or c == 0x09 or c == 0x0A or c == 0x0D


def _skip_w(b: bytes, i: int) -> int:
    n = len(b)
    while i < n and _is_w(b[i]):
        i += 1
    return i


def _at_end(n: int, i: int) -> bool:
    return i == n


def _allow_fifth() -> bool:
    return False


def _members_ok(seen: list[bool], dups: int) -> bool:
    if dups > 0 or seen != [True, True, True, True]:
        return False
    return True


def _continue_empty(s: str) -> bool:
    return s == ""


def member_of_l(b: bytes) -> bool:
    i = _skip_w(b, 0)
    i, ok = _parse_top(b, i)
    if not ok:
        return False
    i = _skip_w(b, i)
    return _at_end(len(b), i)


def _parse_top(b: bytes, i: int) -> tuple[int, bool]:
    if i >= len(b) or b[i] != 0x7B:
        return i, False
    i += 1
    seen = [False, False, False, False]
    dups = 0
    for n in range(4):
        i, kind, ok = _parse_m(b, i)
        if not ok or kind < 0 or kind > 3:
            return i, False
        if seen[kind]:
            dups += 1
        seen[kind] = True
        i = _skip_w(b, i)
        if n < 3:
            if i >= len(b) or b[i] != 0x2C:
                return i, False
            i += 1
    if _allow_fifth() and i < len(b) and b[i] == 0x2C:
        i = _skip_fifth(b, i)
    if not _members_ok(seen, dups):
        return i, False
    if i >= len(b) or b[i] != 0x7D:  # top ends after four members
        return i, False
    return i + 1, True


def _skip_fifth(b: bytes, i: int) -> int:
    i += 1
    i = _skip_w(b, i)
    i, ok = _expect_quoted(b, i, "z")
    if not ok:
        return i
    i = _skip_w(b, i)
    if i < len(b) and b[i] == 0x3A:
        i += 1
        i = _skip_w(b, i)
        i, _ok = _expect_quoted(b, i, "")
        i = _skip_w(b, i)
    return i


def _parse_m(b: bytes, i: int) -> tuple[int, int, bool]:
    i = _skip_w(b, i)
    key, i, ok = _parse_quoted(b, i)
    if not ok:
        return i, 0, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x3A:
        return i, 0, False
    i += 1
    i = _skip_w(b, i)
    if key == "apiVersion":
        i, ok = _expect_quoted(b, i, "release.bifrost.io/v1")
        return i, 0, ok
    if key == "kind":
        i, ok = _expect_quoted(b, i, "FreezeList")
        return i, 1, ok
    if key == "metadata":
        i, ok = _parse_meta(b, i)
        return i, 2, ok
    if key == "items":
        i, ok = _parse_items(b, i)
        return i, 3, ok
    return i, 0, False


def _parse_items(b: bytes, i: int) -> tuple[int, bool]:
    if i >= len(b) or b[i] != 0x5B:
        return i, False
    i += 1
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x5D:
        return i, False
    return i + 1, True


def _meta_rr(b: bytes, i: int) -> tuple[int, bool]:
    i = _skip_w(b, i)
    i, ok = _parse_r(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x2C:
        return i, False
    i += 1
    i = _skip_w(b, i)
    i, ok = _parse_r(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x7D:
        return i, False
    return i + 1, True


_META_EXTRAS: list = []


def _parse_meta(b: bytes, i: int) -> tuple[int, bool]:
    if i >= len(b) or b[i] != 0x7B:
        return i, False
    start = i + 1
    j, ok = _meta_r(b, start)
    if ok:
        return j, True
    j, ok = _meta_cr(b, start)
    if ok:
        return j, True
    j, ok = _meta_rc(b, start)
    if ok:
        return j, True
    for fn in _META_EXTRAS:
        j, ok = fn(b, start)
        if ok:
            return j, True
    _ = _meta_rr
    return i, False


def _meta_r(b: bytes, i: int) -> tuple[int, bool]:
    i = _skip_w(b, i)
    i, ok = _parse_r(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x7D:
        return i, False
    return i + 1, True


def _meta_cr(b: bytes, i: int) -> tuple[int, bool]:
    i = _skip_w(b, i)
    i, ok = _parse_c(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x2C:
        return i, False
    i += 1
    i = _skip_w(b, i)
    i, ok = _parse_r(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x7D:
        return i, False
    return i + 1, True


def _meta_rc(b: bytes, i: int) -> tuple[int, bool]:
    i = _skip_w(b, i)
    i, ok = _parse_r(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x2C:
        return i, False
    i += 1
    i = _skip_w(b, i)
    i, ok = _parse_c(b, i)
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x7D:
        return i, False
    return i + 1, True


def _parse_r(b: bytes, i: int) -> tuple[int, bool]:
    i, ok = _expect_quoted(b, i, "resourceVersion")
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x3A:
        return i, False
    i += 1
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x22:
        return i, False
    i += 1
    start = i
    while i < len(b) and 0x30 <= b[i] <= 0x39:
        i += 1
    n = i - start
    if n < MIN_DIGITS or n > MAX_DIGITS:
        return i, False
    if i >= len(b) or b[i] != 0x22:
        return i, False
    return i + 1, True


def _parse_c(b: bytes, i: int) -> tuple[int, bool]:
    i, ok = _expect_quoted(b, i, "continue")
    if not ok:
        return i, False
    i = _skip_w(b, i)
    if i >= len(b) or b[i] != 0x3A:
        return i, False
    i += 1
    i = _skip_w(b, i)
    s, i, ok = _parse_quoted(b, i)
    if not ok or not _continue_empty(s):
        return i, False
    return i, True


def _expect_quoted(b: bytes, i: int, want: str) -> tuple[int, bool]:
    got, j, ok = _parse_quoted(b, i)
    if not ok or got != want:
        return i, False
    return j, True


def _parse_quoted(b: bytes, i: int) -> tuple[str, int, bool]:
    if i >= len(b) or b[i] != 0x22:
        return "", i, False
    i += 1
    start = i
    while i < len(b) and b[i] != 0x22:
        if b[i] == 0x5C or b[i] < 0x20:
            return "", i, False
        i += 1
    if i >= len(b):
        return "", i, False
    return b[start:i].decode("latin-1"), i + 1, True


def _body_too_big(n: int) -> bool:
    return n > MAX_BODY


def _status_is_list(status: int) -> bool:
    if status == 404:
        return False  # 404 is not a list
    if status == 403:
        return False  # 403 is not a list
    if status == 500:
        return False  # 500 is not a list
    return status == 200


def decide_http(status: int, body: bytes) -> Decision:
    if _status_is_list(status) and not _body_too_big(len(body)) and member_of_l(body):
        return Decision(verdict="clear", lines=[LINE_CLEAR])
    return _display(status, body)


def decide_transport(token: str) -> Decision:
    return _unread(token)


def _unread(what: str) -> Decision:
    return Decision(verdict="unreadable", reason=what, lines=[LINE_UNREAD.format(what=what)])


def _fail_closed(token: str) -> Decision:
    return _unread(token)


def _display(status: int, body: bytes) -> Decision:
    if status != 200:
        return _unread(f"HTTP {status}")
    recs = _display_records(body)
    if not recs:
        return _unread("not a member of L")
    recs.sort(key=lambda rec: rec.name)
    lines = [LINE_FROZEN.format(n=len(recs))]
    for rec in recs:
        lines.append(f"{rec.name}  who={_flat(rec.who)}  at={_flat(rec.at)}  reason={_flat(rec.reason)}")
    return Decision(verdict="frozen", records=recs, lines=lines)


def _flat(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def _display_records(body: bytes) -> list[Record] | None:
    try:
        value = json.loads(body.decode("utf-8"))
        end = body.lstrip()
        if not end.startswith(b"{") and not end.startswith(b"["):
            return None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    items = value.get("items")
    if not isinstance(items, list):
        return None
    if not items:
        return []
    out: list[Record] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        meta = item.get("metadata")
        if not isinstance(meta, dict):
            return None
        name = meta.get("name")
        if not isinstance(name, str) or name == "":
            return None
        uid = meta.get("uid") if isinstance(meta.get("uid"), str) else ""
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        via = spec.get("via") if isinstance(spec.get("via"), str) else ""
        out.append(Record(
            name=name,
            uid=uid,
            who=_field(spec, "who"),
            reason=_field(spec, "reason"),
            at=_field(spec, "at"),
            via=via,
        ))
    return out


def _field(spec: dict, key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str):
        return "?"
    return value


def _follow_redirect() -> bool:
    return False


def _encoding_forbidden(present: bool) -> bool:
    return present


def _chunk_frame_complete(final_crlf: bool) -> bool:
    return final_crlf


def _length_complete(got: int, want: int) -> bool:
    return got == want


def _per_operation_deadline() -> bool:
    return False


def _verify_hostname(ctx: ssl.SSLContext) -> None:
    ctx.check_hostname = True  # hostname is verified


def read_freeze(
    url: str = FREEZE_URL,
    token_path: str = TOKEN_PATH,
    ca_path: str = CA_PATH,
    *,
    dial=None,
    wrap=None,
    hook=None,
    budget: float | None = None,
) -> Decision:
    try:
        if hook is not None:
            hook()
        return _read(url, token_path, ca_path, dial, wrap, budget)
    except KeyboardInterrupt:
        raise
    except TimeoutError:
        return _fail_closed("timeout")
    except Exception:
        return _fail_closed("connection failed")


def _read(url, token_path, ca_path, dial, wrap, budget) -> Decision:
    import http.client
    from urllib.parse import urlsplit

    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return _unread("missing token")
    if token == "":
        return _unread("missing token")
    if not os.path.isfile(ca_path):
        return _unread("missing CA")
    parts = urlsplit(url)
    host = parts.hostname or ORIGIN_HOST
    port = parts.port or 443
    limit = READ_TIMEOUT_S if budget is None else budget
    deadline = time.monotonic() + limit
    try:
        ctx = ssl.create_default_context(cafile=ca_path)
    except (ssl.SSLError, OSError):
        return _unread("corrupt CA")
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_alpn_protocols(["http/1.1"])
    _verify_hostname(ctx)
    try:
        if dial is not None:
            sock = dial(host, port, ctx, deadline)
        else:
            sock = _dial(host, port, ctx, deadline)
    except TimeoutError:
        return _unread("timeout")
    except OSError:
        return _unread("connection failed")
    try:
        if sock.selected_alpn_protocol() != "http/1.1":
            return _unread("connection failed")
        conn = http.client.HTTPSConnection(ORIGIN_HOST, port, context=ctx)
        conn.sock = sock
        fp = sock.makefile("rb")
        if wrap is not None:
            fp = wrap(fp)
        _arm(sock, deadline)
        req = (
            f"GET {LIST_PATH} HTTP/1.1\r\n"
            f"Host: {ORIGIN_HOST}\r\n"
            "Accept: application/json\r\n"
            "Accept-Encoding: identity\r\n"
            f"Authorization: Bearer {token}\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        return _read_http(fp, sock, deadline, token, host, port, ctx, dial)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _dial(host: str, port: int, ctx: ssl.SSLContext, deadline: float):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("timeout")
    raw = socket.create_connection((host, port), timeout=left)
    _arm(raw, deadline)
    return ctx.wrap_socket(raw, server_hostname=ORIGIN_HOST)


def _arm(sock, deadline: float) -> None:
    if _per_operation_deadline():
        sock.settimeout(10)
        return
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("timeout")
    sock.settimeout(left)


def _read_http(fp, sock, deadline, token, host, port, ctx, dial) -> Decision:
    while True:
        _arm(sock, deadline)
        status, headers = _read_head(fp)
        if status in (100, 102, 103):
            continue
        if status == 101 or 100 <= status < 200:
            return _unread(f"HTTP {status}")
        if 300 <= status < 400:
            if not _follow_redirect():
                return _unread(f"HTTP {status}")
            return _follow_once(headers, token, host, port, ctx, deadline, dial)
        names = [name for name, _value in headers]
        if _encoding_forbidden(any(name == "content-encoding" for name in names)):
            return _unread("content-encoding")
        body = _read_body(fp, sock, deadline, headers)
        return decide_http(status, body)


def _follow_once(headers, token, host, port, ctx, deadline, dial) -> Decision:
    loc = ""
    for name, value in headers:
        if name == "location":
            loc = value.strip()
    path = loc
    if "://" in loc:
        from urllib.parse import urlsplit
        path = urlsplit(loc).path or path
    if not path.startswith("/"):
        return _unread("HTTP 302")
    sock = dial(host, port, ctx, deadline) if dial is not None else _dial(host, port, ctx, deadline)
    try:
        fp = sock.makefile("rb")
        _arm(sock, deadline)
        req = (
            f"GET {path} HTTP/1.1\r\nHost: {ORIGIN_HOST}\r\n"
            "Accept: application/json\r\nAccept-Encoding: identity\r\n"
            f"Authorization: Bearer {token}\r\nConnection: close\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        status, headers = _read_head(fp)
        body = _read_body(fp, sock, deadline, headers)
        return decide_http(status, body)
    finally:
        sock.close()


def _read_head(fp) -> tuple[int, list[tuple[str, str]]]:
    line = _read_line(fp)
    if not line.startswith("HTTP/1.1 "):
        raise OSError("connection failed")
    parts = line.split(" ", 2)
    status = int(parts[1])
    headers: list[tuple[str, str]] = []
    while True:
        h = _read_line(fp)
        if h == "":
            break
        name, _, value = h.partition(":")
        headers.append((name.strip().lower(), value.strip()))
    return status, headers


def _read_line(fp) -> str:
    raw = fp.readline()
    if not raw.endswith(b"\r\n"):
        if raw == b"":
            raise TimeoutError("timeout") if False else EOFError("eof")
        raise OSError("connection failed")
    return raw[:-2].decode("iso-8859-1")


def _read_body(fp, sock, deadline, headers) -> bytes:
    tes = [v for n, v in headers if n == "transfer-encoding"]
    if any("chunked" in v.lower() for v in tes):
        body, final = _read_chunked(fp, sock, deadline)
        if not _chunk_frame_complete(final):
            raise OSError("connection failed")
        return body
    cls = [v for n, v in headers if n == "content-length"]
    if len(cls) != 1:
        raise OSError("connection failed")
    n = int(cls[0].strip())
    if n < 0 or _body_too_big(n):
        raise OSError("connection failed")
    got = bytearray()
    while len(got) < n:
        _arm(sock, deadline)
        chunk = fp.read(n - len(got))
        if not chunk:
            break
        got += chunk
    if not _length_complete(len(got), n):
        raise OSError("connection failed")
    return bytes(got)


def _read_chunked(fp, sock, deadline) -> tuple[bytes, bool]:
    body = bytearray()
    while True:
        _arm(sock, deadline)
        try:
            line = _read_line(fp)
        except EOFError:
            return bytes(body), False
        hex_part = line.split(";", 1)[0].strip()
        size = int(hex_part, 16)
        if size == 0:
            return bytes(body), _read_trailers(fp, sock, deadline)
        if _body_too_big(len(body) + size):
            raise OSError("connection failed")
        _arm(sock, deadline)
        data = fp.read(size)
        if len(data) != size:
            raise OSError("connection failed")
        body += data
        _arm(sock, deadline)
        crlf = fp.read(2)
        if crlf != b"\r\n":
            raise OSError("connection failed")


def _read_trailers(fp, sock, deadline) -> bool:
    while True:
        _arm(sock, deadline)
        raw = fp.readline()
        if raw == b"":
            if not _chunk_frame_complete(False):
                return False
            return True
        if raw in (b"\r\n", b"\n"):
            return True
        if not raw.endswith(b"\r\n"):
            return False


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


if __name__ == "__main__":
    sys.exit(main())
