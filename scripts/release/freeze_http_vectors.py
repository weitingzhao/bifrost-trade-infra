"""Raw HTTP responses for the freeze gate, with the verdict the design requires for each (design 3.2, language H).

This file is test material. It holds a recogniser written from the productions of H and L — not from the Go reader
and not from the Python reader — and a fixed list of responses. `freeze_http_vectors.json` is its output; the same
bytes are in the platform repository (`api/internal/releasefreeze/testdata/`). Both implementations must give, for
every response, exactly the verdict recorded here.

    python3 scripts/release/freeze_http_vectors.py > scripts/release/freeze_http_vectors.json
"""

from __future__ import annotations

import json
import re
import sys

# ---- the recogniser of L (the body), by recursive descent over the productions ----

_WS = b"\x20\x09\x0a\x0d"


class _P:
    def __init__(self, b: bytes) -> None:
        self.b = b
        self.i = 0

    def w(self) -> bool:
        while self.i < len(self.b) and self.b[self.i] in _WS:
            self.i += 1
        return True

    def lit(self, t: bytes) -> bool:
        if self.b.startswith(t, self.i):
            self.i += len(t)
            return True
        return False

    def q(self, t: bytes) -> bool:
        return self.lit(b'"' + t + b'"')

    def qd(self) -> bool:
        if not self.lit(b'"'):
            return False
        j = self.i
        while self.i < len(self.b) and 0x30 <= self.b[self.i] <= 0x39:
            self.i += 1
        return 1 <= self.i - j <= 32 and self.lit(b'"')

    def colon(self) -> bool:
        return self.w() and self.lit(b":") and self.w()

    def r(self) -> bool:
        return self.q(b"resourceVersion") and self.colon() and self.qd()

    def c(self) -> bool:
        return self.q(b"continue") and self.colon() and self.q(b"")

    def meta(self) -> bool:
        if not (self.lit(b"{") and self.w()):
            return False
        if self.b.startswith(b'"c', self.i):
            ok = self.c() and self.w() and self.lit(b",") and self.w() and self.r()
        else:
            ok = self.r() and self.w()
            if ok and self.lit(b","):
                ok = self.w() and self.c()
        return ok and self.w() and self.lit(b"}")

    def m(self, seen: set) -> bool:
        self.w()
        if self.q(b"apiVersion"):
            k, ok = "a", self.colon() and self.q(b"release.bifrost.io/v1")
        elif self.q(b"kind"):
            k, ok = "k", self.colon() and self.q(b"FreezeList")
        elif self.q(b"metadata"):
            k, ok = "m", self.colon() and self.meta()
        elif self.q(b"items"):
            k, ok = "i", self.colon() and self.lit(b"[") and self.w() and self.lit(b"]")
        else:
            return False
        if not ok or k in seen:
            return False
        seen.add(k)
        return True

    def top(self) -> bool:
        seen: set = set()
        if not self.lit(b"{"):
            return False
        for n in range(4):
            if n and not (self.w() and self.lit(b",")):
                return False
            if not self.m(seen):
                return False
        return self.w() and self.lit(b"}") and len(seen) == 4


def in_l(body: bytes) -> bool:
    p = _P(bytes(body))
    return p.w() and p.top() and p.w() and p.i == len(p.b)


# ---- the recogniser of H (status line, field lines, framing), line by line with regular expressions ----

_FT = rb"[\t\x20-\x7e]"
_STATUS = re.compile(rb"\AHTTP/1\.1 ([0-9]{3})(?: " + _FT + rb"*)?\Z")
_FIELD = re.compile(rb"\A([!#$%&'*+\-.^_`|~0-9A-Za-z]+):(" + _FT + rb"*)\Z")
_DEC = re.compile(rb"\A[0-9]{1,4}\Z")
_HEX = re.compile(rb"\A[0-9A-Fa-f]{1,4}\Z")


class _NotH(Exception):
    pass


class _Cursor:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.pos = 0

    def line(self) -> bytes:
        j = self.raw.find(b"\n", self.pos)
        if j < 0 or j + 1 - self.pos > 1024:
            raise _NotH
        whole = self.raw[self.pos:j + 1]
        if not whole.endswith(b"\r\n"):
            raise _NotH
        self.pos = j + 1
        return whole[:-2]

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.raw):
            raise _NotH
        out = self.raw[self.pos:self.pos + n]
        self.pos += n
        return out

    def fields(self) -> list:
        out = []
        while True:
            ln = self.line()
            if ln == b"":
                return out
            m = _FIELD.match(ln)
            if m is None or len(out) == 64:
                raise _NotH
            out.append((m.group(1).lower(), m.group(2).strip(b" \t")))

    def head(self) -> tuple:
        m = _STATUS.match(self.line())
        if m is None:
            raise _NotH
        return m.group(1), self.fields()


def body_of(raw: bytes) -> bytes:
    """The body H assigns to this response; raises _NotH when the response is not in H."""
    cur = _Cursor(raw)
    interim = 0
    while True:
        code, fields = cur.head()
        if b"content-encoding" in [n for n, _v in fields]:
            raise _NotH
        if code in (b"100", b"102", b"103"):
            interim += 1
            if interim > 8:
                raise _NotH
            continue
        break
    if code != b"200":
        raise _NotH
    te = [v for n, v in fields if n == b"transfer-encoding"]
    cl = [v for n, v in fields if n == b"content-length"]
    if not te:
        if len(cl) != 1 or _DEC.match(cl[0]) is None or int(cl[0].decode("ascii")) > 4096:
            raise _NotH
        return cur.take(int(cl[0].decode("ascii")))
    if cl or len(te) != 1 or te[0].lower() != b"chunked":
        raise _NotH
    body = b""
    while True:
        size = cur.line()
        if _HEX.match(size) is None:
            raise _NotH
        n = int(size.decode("ascii"), 16)
        if n == 0:
            break
        if len(body) + n > 4096:
            raise _NotH
        body += cur.take(n)
        if cur.take(2) != b"\r\n":
            raise _NotH
    for name, _v in cur.fields():
        if name in (b"content-encoding", b"content-length", b"transfer-encoding"):
            raise _NotH
    return body


def clear(raw: bytes) -> bool:
    try:
        return in_l(body_of(raw))
    except _NotH:
        return False


# ---- the responses ----

M = b'{"apiVersion":"release.bifrost.io/v1","items":[],"kind":"FreezeList","metadata":{"continue":"","resourceVersion":"84135567"}}\n'
N = len(M)


def _cl(status=b"HTTP/1.1 200 OK", name=b"Content-Length", value=None, extra=(), body=M, eol=b"\r\n", pre=b""):
    v = str(len(body)).encode() if value is None else value
    lines = [status] + list(extra) + [name + b": " + v]
    return pre + eol.join(lines) + eol + eol + body


def _ch(size=None, term=b"0\r\n\r\n", extra=(), te=b"Transfer-Encoding: chunked", body=M, status=b"HTTP/1.1 200 OK"):
    s = ("%x" % len(body)).encode() if size is None else size
    return b"\r\n".join([status] + list(extra) + [te]) + b"\r\n\r\n" + s + b"\r\n" + body + b"\r\n" + term


def cases() -> list:
    out: list = []

    def add(label: str, raw: bytes) -> None:
        out.append((label, raw))

    add("base content-length", _cl())
    add("base chunked", _ch())
    for s in [b"HTTP/1.1 200", b"HTTP/1.1 200 ", b"HTTP/1.1 200 OK\t(fine)", b"HTTP/1.1 +200 OK", b"HTTP/1.1 \t200 OK", b"HTTP/1.1 2_00 OK",
              b"HTTP/1.1 0200 OK", b"HTTP/1.1 2000 OK", b"HTTP/1.1 20 OK", b"HTTP/1.1 200\tOK", b"HTTP/1.1  200 OK", b"HTTP/1.0 200 OK",
              b"http/1.1 200 OK", b"HTTP/1.1 200.0 OK", b"HTTP/1.1 2e2 OK", b"HTTP/1.1 \xa0200 OK", b"HTTP/1.1 200\xa0 OK", b"HTTP/1.1 200 \xa0OK",
              b"HTTP/1.1 200 O\x00K", b"HTTP/1.1 200 O\x7fK", b"HTTP/1.1 \x1c200 OK", b"HTTP/1.1 201 Created", b"HTTP/1.1 204 No Content",
              b"HTTP/1.1 206 Partial", b"HTTP/1.1 299 x", b"HTTP/1.1 301 Moved", b"HTTP/1.1 404 Not Found", b"HTTP/1.1 403 Forbidden",
              b"HTTP/1.1 500 x", b"HTTP/1.1 101 Switching", b"HTTP/1.1 199 x", b"HTTP/1.1 -200 OK", b"HTTP/1.1 00200 OK", b"HTTP/1.1 200OK",
              b" HTTP/1.1 200 OK", b"HTTP/1.1\t200 OK", b"HTTP/2 200", b"HTTP/1.1 \xd9\xa2\xd9\xa0\xd9\xa0 OK", b"HTTP/1.1 000 x", b"HTTP/1.1"]:
        add("status line %r" % s, _cl(status=s))
    for n in [b"content-length", b"CONTENT-LENGTH", b"cOnTeNt-LeNgTh", b"Content-Length ", b" Content-Length", b"Content-Length\t", b"Content-Length\xa0",
              b"Content-Length\x1f", b"Content-Length\x0c", b"Content-Length\x0b", b"Content-Length\x85", b"\xa0Content-Length", b"Content-Lenqth",
              b"Content_Length", b"Content-Length\x00", b"Content\xe2\x84\xaa-Length"]:
        add("content-length name %r" % n, _cl(name=n))
    for v in [b" 126 ", b"\t126\t", b"+126", b"0126", b"00126", b"1_26", b"126\xa0", b"\xa0126", b"126\x1c", b"126\x0c", b"126\x0b", b"0x7e", b"126.0",
              b"1e2", b"", b"126, 126", b"-1", b"12 6", b"126;", b"0b1111110", b"0o176", b"00000000000000000000126", b"1__26", b"_126", b"126_",
              b"125", b"127", b"0", b"\xd9\xa1\xd9\xa2\xd9\xa6", b"126\x00"]:
        add("content-length value %r" % v, _cl(value=v))
    extras = [b"X-Junk", b": empty-name", b"Content-Encoding: identity", b"content-encoding:", b"CONTENT-ENCODING: gzip", b"Content-Encoding\xa0: gzip",
              b"Content-Encoding\x1f: gzip", b" Content-Encoding: gzip", b"\tContent-Encoding: gzip", b"Content-Encoding : gzip", b"Content-Encoding\x0c: gzip",
              b"Content-Encoding\x85: gzip", b"X: y\r\n Content-Encoding: gzip", b"Content-Length: 126", b"Content-Length: 125", b"content-length: 126",
              b"Transfer-Encoding: identity", b"Transfer-Encoding: Chunked", b"Transfer-Encoding: notchunked", b"Transfer-Encoding: gzip, chunked",
              b"Transfer-Encoding: chunked", b"Transfer-Encoding:\tCHUNKED \t", b"Tran\xc5\xbffer-Encoding: chunked", b"Transfer-Encoding\xa0: chunked",
              b"Transfer-Encoding\x1f: chunked", b"X-No-Value:", b"X:\x00", b"X: \x80", b"X: a\x7fb", b"X: a\rb", b"X Junk: 1", b"X-Junk : 1", b"X-Junk\x80: 1",
              b"X-Junk: 1\n", b"Connection: close", b"Content-Type: application/json", b"\xe2\x84\xaa: v", b"X-Junk no colon here", b"=", b"Location: /x",
              b"!#$%&'*+-.^_`|~0aZ: every token byte", b"X(: 1", b"X\": 1", b"X,: 1", b"X/: 1", b"X;: 1", b"X@: 1", b"X[: 1", b"X{: 1"]
    for e in extras:
        add("extra field %r" % e[:44], _cl(extra=(e,)))
        add("extra field, chunked %r" % e[:44], _ch(extra=(e,)))
    for s in [b"7E", b"007e", b"0007e", b"0x7e", b"0X7E", b"7_e", b"+7e", b" 7e", b"7e ", b"7e;ext=1", b"7e ;ext", b"7e;", b"7e\xa0", b"\xa07e", b"7e\x1c",
              b"7e\x0c", b"-7e", b"7g", b"", b"0b1", b"7e\t", b"\t7e", b"7__e", b"7d", b"7f"]:
        add("chunk size %r" % s, _ch(size=s))
    for t in [b"0\r\n", b"0\r\n\n", b"0\n\r\n", b"0\r\nX: y\r\n\r\n", b"0\r\nX: y\r\n", b"0\r\nX: y\r\n\n", b"0\r\nno-colon\r\n\r\n", b"00\r\n\r\n", b"0000\r\n\r\n",
              b"00000\r\n\r\n", b"-0\r\n\r\n", b"+0\r\n\r\n", b"0x0\r\n\r\n", b"0;x\r\n\r\n", b"0 \r\n\r\n", b" 0\r\n\r\n", b"0_0\r\n\r\n", b"", b"0", b"0\r", b"0\r\n\r",
              b"0\r\n\r\nextra", b"0\r\nContent-Encoding: gzip\r\n\r\n", b"0\r\nContent-Length: 1\r\n\r\n", b"0\r\ntransfer-encoding: chunked\r\n\r\n",
              b"0\r\nX: \x80\r\n\r\n", b"0\r\n\r\n\r\n", b"0\xa0\r\n\r\n", b"0\x1c\r\n\r\n",
              b"0\r\n" + b"X: y\r\n" * 64 + b"\r\n", b"0\r\n" + b"X: y\r\n" * 65 + b"\r\n"]:
        add("chunk terminator %r" % t[:40] + (" (%d bytes)" % len(t) if len(t) > 40 else ""), _ch(term=t))
    half = N // 2
    two = (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + ("%x" % half).encode() + b"\r\n" + M[:half] + b"\r\n"
           + ("%X" % (N - half)).encode() + b"\r\n" + M[half:] + b"\r\n0\r\n\r\n")
    add("two chunks", two)
    add("two chunks, no CRLF after the first", two.replace(M[:half] + b"\r\n", M[:half], 1))
    add("two bytes that are not CRLF after the chunk data", b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n7e\r\n" + M + b"XY0\r\n\r\n")
    add("one byte per chunk", b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + b"".join(b"1\r\n" + bytes([c]) + b"\r\n" for c in M) + b"0\r\n\r\n")
    add("chunked and content-length together", _ch(extra=(b"Content-Length: 126",)))
    add("chunked and a wrong content-length", _ch(extra=(b"Content-Length: 5",)))
    add("content-length body that looks chunked, both fields", _cl(extra=(b"Transfer-Encoding: chunked",)))
    add("two transfer-encoding fields", _ch(extra=(b"Transfer-Encoding: chunked",)))
    for te in [b"Transfer-Encoding: notchunked", b"Transfer-Encoding: gzip, chunked", b"Transfer-Encoding: identity", b"Transfer-Encoding: CHUNKED",
               b"transfer-encoding:chunked", b"Transfer-Encoding: chunked;q=1", b"Transfer-Encoding: chunked, chunked", b"Transfer-Encoding:"]:
        add("one transfer-encoding field %r" % te, _ch(te=te))
    add("no framing at all", b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + M)
    add("content-length, body truncated", _cl()[:-10])
    add("content-length, bytes after the body", _cl() + b"junk")
    add("content-length shorter than the body", _cl(value=b"100"))
    for eol in (b"\n", b"\r", b"\r\r\n", b"\n\r"):
        add("line ending %r everywhere" % eol, _cl(eol=eol))
    add("bare LF after the status line", _cl().replace(b"OK\r\n", b"OK\n", 1))
    add("bare LF ends the head", _cl().replace(b"\r\n\r\n", b"\r\n\n", 1))
    for pre in [b"HTTP/1.1 100 Continue\r\n\r\n", b"HTTP/1.1 102 Processing\r\n\r\n", b"HTTP/1.1 103 Early Hints\r\nLink: </x>\r\n\r\n",
                b"HTTP/1.1 100 Continue\r\n\r\n" * 8, b"HTTP/1.1 100 Continue\r\n\r\n" * 9, b"HTTP/1.1 101 Switching Protocols\r\n\r\n",
                b"HTTP/1.1 100 Continue\r\nContent-Encoding: gzip\r\n\r\n", b"HTTP/1.1 100 Continue\r\nno-colon\r\n\r\n",
                b"HTTP/1.1 100 Continue\r\nContent-Length: 3\r\n\r\nabc", b"\r\n", b"HTTP/1.1 1_00 Continue\r\n\r\n", b"HTTP/1.1 +100 Continue\r\n\r\n",
                b"HTTP/1.1 100\r\n\r\n", b"HTTP/1.1 104 x\r\n\r\n", b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"]:
        add("before the response %r" % pre[:44] + (" x%d" % (len(pre) // 25) if len(pre) > 60 else ""), _cl(pre=pre))
    # the limits, one case on each side
    pad = lambda n: b"X-Pad: " + b"a" * (n - len(b"X-Pad: ") - 2)  # noqa: E731 - a field line of n bytes with its CRLF
    add("a field line of 1024 bytes", _cl(extra=(pad(1024),)))
    add("a field line of 1025 bytes", _cl(extra=(pad(1025),)))
    add("a status line of 1024 bytes", _cl(status=b"HTTP/1.1 200 " + b"a" * (1024 - 15)))
    add("a status line of 1025 bytes", _cl(status=b"HTTP/1.1 200 " + b"a" * (1025 - 15)))
    add("64 field lines", _cl(extra=tuple(b"X-%d: v" % i for i in range(63))))
    add("65 field lines", _cl(extra=tuple(b"X-%d: v" % i for i in range(64))))
    big = b" " * (4096 - N) + M
    add("4096 bytes of body", _cl(body=big))
    add("4097 bytes of body", _cl(body=b" " + big))
    add("4096 bytes, chunked", _ch(body=big))
    add("4097 bytes, chunked", _ch(body=b" " + big))
    add("4096 bytes in two chunks of 2048", b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n800\r\n" + big[:2048] + b"\r\n800\r\n" + big[2048:] + b"\r\n0\r\n\r\n")
    add("a second chunk that passes 4096", b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n800\r\n" + big[:2048] + b"\r\n801\r\n " + big[2048:] + b"\r\n0\r\n\r\n")
    add("a body that is not in L", _cl(body=M.replace(b"[]", b"[{}]")))
    add("a body with one freeze record", _cl(body=M.replace(b"[]", b'[{"metadata":{"name":"f1"}}]')))
    add("an empty body", _cl(body=b""))
    add("the member without its LF", _cl(body=M[:-1]))
    add("the member with CRLF in place of LF", _cl(body=M[:-1] + b"\r\n"))
    add("empty input", b"")
    add("a status line and nothing else", b"HTTP/1.1 200 OK\r\n")
    add("a head that never ends", b"HTTP/1.1 200 OK\r\nContent-Length: 126\r\n")
    seen: set = set()
    uniq = []
    for label, raw in out:
        if raw in seen:
            continue
        seen.add(raw)
        uniq.append((label, raw))
    return uniq


def document() -> str:
    rows = [{"name": label, "hex": raw.hex(), "clear": clear(raw)} for label, raw in cases()]
    return json.dumps({"cases": rows}, ensure_ascii=True, indent=0, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(document())
