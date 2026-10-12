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
    if not _members_ok(seen, dups):
        return i, False
    if i >= len(b) or b[i] != 0x7D:  # top ends after four members
        return i, False
    return i + 1, True


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


def _encoding_forbidden(present: bool) -> bool:
    return present


def _chunk_frame_complete(final_crlf: bool) -> bool:
    return final_crlf


def _length_complete(got: int, want: int) -> bool:
    return got == want


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
        fp = _Reader(sock, deadline)
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


class _Reader:
    """Bytes from the connection. Every recv is armed with the time left to the one absolute deadline, so no
    sequence of partial deliveries can add up to more than the budget (a buffered file object re-reads under one
    relative timeout and can)."""

    def __init__(self, sock, deadline: float) -> None:
        self._sock = sock
        self._deadline = deadline
        self._buf = bytearray()
        self._eof = False

    def _fill(self) -> bool:
        if self._eof:
            return False
        _arm(self._sock, self._deadline)
        data = self._sock.recv(4096)
        if not data:
            self._eof = True
            return False
        self._buf += data
        return True

    def readline(self, limit: int) -> bytes:
        """Up to and including the first LF, at most limit bytes; what is left when the stream ends."""
        while True:
            j = self._buf.find(b"\n", 0, limit)
            if j >= 0:
                return self._take(j + 1)
            if len(self._buf) >= limit:
                return self._take(limit)
            if not self._fill():
                return self._take(len(self._buf))

    def read(self, n: int) -> bytes:
        """Exactly n bytes, or fewer when the stream ends first."""
        while len(self._buf) < n:
            if not self._fill():
                break
        return self._take(min(n, len(self._buf)))

    def _take(self, n: int) -> bytes:
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def _arm(sock, deadline: float) -> None:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("timeout")
    sock.settimeout(left)


def _finished_in_time(deadline: float) -> bool:
    return time.monotonic() <= deadline  # rule: clear only when the response was complete before the deadline


def _read_http(fp, sock, deadline, token, host, port, ctx, dial) -> Decision:
    interim = 0
    while True:
        _arm(sock, deadline)
        status, headers = _read_head(fp, sock, deadline)
        if _encoding_forbidden(any(name == "content-encoding" for name, _value in headers)):
            return _unread("content-encoding")
        if status in (100, 102, 103):
            interim += 1
            if interim > MAX_INTERIM:
                return _unread("too many interim responses")
            continue
        if status == 101 or 100 <= status < 200:
            return _unread(f"HTTP {status}")
        if 300 <= status < 400:  # rule: a redirect is not followed
            return _unread(f"HTTP {status}")
        body = _read_body(fp, sock, deadline, headers)
        got = decide_http(status, body)
        if got.verdict == "clear" and not _finished_in_time(deadline):
            return _unread("timeout")
        return got


# The response language H of design 3.2: the status line, the field lines and the framing. Every rule is a rule
# on bytes. No library integer or whitespace function is on this path: int() and str.strip() accept more than H
# does, and they accept differently from Go's strconv.Atoi and strings.TrimSpace. A response outside H is not clear.
MAX_LINE = 1024  # rule: a line with its CRLF is at most 1024 bytes
MAX_FIELDS = 64  # rule: at most 64 field lines in a head or a trailer
MAX_INTERIM = 8  # rule: at most 8 interim responses
MAX_LEN_DIGITS = 4  # rule: Content-Length is 1 to 4 digits
MAX_HEX_DIGITS = 4  # rule: a chunk size is 1 to 4 hex digits
_TCHAR = frozenset(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" + b"!#$%&'*+-.^_`|~")  # rule: token bytes
_TRAILER_FORBIDDEN = ("content-encoding", "content-length", "transfer-encoding")  # rule: no framing field in a trailer


def _is_ftext(c: int) -> bool:
    return c == 0x09 or 0x20 <= c <= 0x7E  # rule: field text is HTAB or 0x20-0x7E


def _lower_ascii(b: bytes) -> str:
    return bytes(c + 32 if 0x41 <= c <= 0x5A else c for c in b).decode("latin-1")


def _read_line(fp) -> bytes:
    raw = fp.readline(MAX_LINE + 1)
    if raw == b"":
        raise EOFError("eof")
    if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
        raise OSError("connection failed")
    if len(raw) < 2 or raw[-2] != 0x0D:  # rule: a line ends with CRLF
        raise OSError("connection failed")
    return raw[:-2]


def _parse_status_line(line: bytes) -> int:
    prefix = b"HTTP/1.1 "
    if len(line) < len(prefix) + 3 or line[: len(prefix)] != prefix:
        raise OSError("connection failed")
    d = line[len(prefix):]
    if not (0x30 <= d[0] <= 0x39 and 0x30 <= d[1] <= 0x39 and 0x30 <= d[2] <= 0x39):
        raise OSError("connection failed")
    code = (d[0] - 0x30) * 100 + (d[1] - 0x30) * 10 + (d[2] - 0x30)
    rest = d[3:]
    if len(rest) == 0:
        return code
    if rest[0] != 0x20:  # rule: SP between the status code and the reason
        raise OSError("connection failed")
    for c in rest[1:]:
        if not _is_ftext(c):
            raise OSError("connection failed")
    return code


def _parse_field(line: bytes) -> tuple[str, str]:
    i = 0
    while i < len(line) and line[i] in _TCHAR:
        i += 1
    if i == 0 or i >= len(line) or line[i] != 0x3A:
        raise OSError("connection failed")
    v = line[i + 1:]
    for c in v:
        if not _is_ftext(c):
            raise OSError("connection failed")
    a, b = 0, len(v)
    while a < b and v[a] in (0x20, 0x09):
        a += 1
    while b > a and v[b - 1] in (0x20, 0x09):
        b -= 1
    return _lower_ascii(line[:i]), v[a:b].decode("latin-1")


def _read_fields(fp, sock, deadline) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    while True:
        _arm(sock, deadline)
        line = _read_line(fp)
        if len(line) == 0:
            return out
        if len(out) >= MAX_FIELDS:
            raise OSError("connection failed")
        out.append(_parse_field(line))


def _read_head(fp, sock, deadline) -> tuple[int, list[tuple[str, str]]]:
    status = _parse_status_line(_read_line(fp))
    return status, _read_fields(fp, sock, deadline)


def _parse_decimal(s: str) -> int:
    if len(s) == 0 or len(s) > MAX_LEN_DIGITS:
        raise OSError("connection failed")
    n = 0
    for ch in s:
        if not ("0" <= ch <= "9"):
            raise OSError("connection failed")
        n = n * 10 + (ord(ch) - 0x30)
    return n


def _chunk_size_text(line: bytes) -> bytes:
    return line  # rule: no chunk extension


def _parse_chunk_size(line: bytes) -> int:
    t = _chunk_size_text(line)
    if len(t) == 0 or len(t) > MAX_HEX_DIGITS:
        raise OSError("connection failed")
    n = 0
    for c in t:
        if 0x30 <= c <= 0x39:
            v = c - 0x30
        elif 0x61 <= c <= 0x66:
            v = c - 0x61 + 10
        elif 0x41 <= c <= 0x46:
            v = c - 0x41 + 10
        else:
            raise OSError("connection failed")
        n = n * 16 + v
    return n


def _read_body(fp, sock, deadline, headers) -> bytes:
    tes = [v for n, v in headers if n == "transfer-encoding"]
    cls = [v for n, v in headers if n == "content-length"]
    if len(tes) > 0:
        if len(cls) != 0 or len(tes) != 1:  # rule: chunked excludes content-length and a second transfer-encoding
            raise OSError("connection failed")
        if _lower_ascii(tes[0].encode("latin-1")) != "chunked":  # rule: the only transfer coding is chunked
            raise OSError("connection failed")
        body, final = _read_chunked(fp, sock, deadline)
        if not _chunk_frame_complete(final):
            raise OSError("connection failed")
        return body
    if len(cls) != 1:
        raise OSError("connection failed")
    n = _parse_decimal(cls[0])
    if _body_too_big(n):
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


def _read_exact(fp, sock, deadline, n: int) -> bytes:
    got = bytearray()
    while len(got) < n:
        _arm(sock, deadline)
        chunk = fp.read(n - len(got))
        if not chunk:
            raise OSError("connection failed")
        got += chunk
    return bytes(got)


def _read_chunked(fp, sock, deadline) -> tuple[bytes, bool]:
    body = bytearray()
    while True:
        _arm(sock, deadline)
        size = _parse_chunk_size(_read_line(fp))
        if size == 0:
            return bytes(body), _read_trailers(fp, sock, deadline)
        if _body_too_big(len(body) + size):
            raise OSError("connection failed")
        body += _read_exact(fp, sock, deadline, size)
        if _read_exact(fp, sock, deadline, 2) != b"\r\n":
            raise OSError("connection failed")


def _read_trailers(fp, sock, deadline) -> bool:
    """The trailer section and the empty line that ends the body. A stream that ends first is not final."""
    try:
        fields = _read_fields(fp, sock, deadline)
    except EOFError:
        return False
    for name, _value in fields:
        if name in _TRAILER_FORBIDDEN:
            raise OSError("connection failed")
    return True


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
