"""Vectors and one HTTP/1.1 read. Clear is the binary verdict."""

from __future__ import annotations

import base64
import hashlib
import http.client
import io
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import freeze_gate as fg

HERE = Path(__file__).resolve().parent
VECTORS = HERE / "freeze_vectors.json"
FREEZE_VECTORS_SHA256 = "b20086845a61e9a0d92765472aa932ebbc517dd5c0f4d107e5ff959080c3bf72"
CLEAR = (
    b'{"apiVersion":"release.bifrost.io/v1","items":[],"kind":"FreezeList",'
    b'"metadata":{"continue":"","resourceVersion":"84135567"}}\n'
)


def _body(case: dict) -> bytes:
    if case.get("body_base64"):
        return base64.standard_b64decode(case["body_base64"])
    return case.get("body", "").encode("utf-8")


def _cert(root: Path, name: str, san: str) -> tuple[Path, Path]:
    cert = root / f"{name}.pem"
    key = root / f"{name}.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", f"/CN={name}",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _http(status: str, headers: str, body: bytes) -> bytes:
    head = f"HTTP/1.1 {status}\r\n{headers}"
    low = headers.lower()
    if "content-length" not in low and "transfer-encoding" not in low:
        head += f"Content-Length: {len(body)}\r\n"
    if not head.endswith("\r\n"):
        head += "\r\n"
    head += "\r\n"
    return head.encode("ascii") + body


class _Server:
    def __init__(self, cert: Path, key: Path, respond, protos: tuple[str, ...] = ("http/1.1",), drip: float = 0) -> None:
        self.hits: list[bytes] = []
        self._lock = threading.Lock()
        self._respond = respond
        self._drip = drip
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(64)
        self.port = sock.getsockname()[1]
        self._sock = sock
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        ctx.set_alpn_protocols(list(protos))
        self._ctx = ctx
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop:
            try:
                raw, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(raw,), daemon=True).start()

    def _handle(self, raw: socket.socket) -> None:
        try:
            conn = self._ctx.wrap_socket(raw, server_side=True)
        except ssl.SSLError:
            raw.close()
            return
        try:
            conn.settimeout(3)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 8192:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            with self._lock:
                n = len(self.hits)
                self.hits.append(data)
            payload = self._respond(n, data)
            if self._drip:
                for i in range(len(payload)):
                    time.sleep(self._drip)
                    conn.sendall(payload[i:i + 1])
            else:
                conn.sendall(payload)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                raw.close()

    def requests(self) -> list[bytes]:
        with self._lock:
            return list(self.hits)

    def close(self) -> None:
        self._stop = True
        try:
            self._sock.close()
        except OSError:
            pass


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = VECTORS.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != FREEZE_VECTORS_SHA256:
            raise AssertionError(f"vector digest {digest}")
        cls.file = json.loads(raw)
        sibling = HERE.parents[2] / "bifrost-platform" / "api" / "internal" / "releasefreeze" / "testdata" / "freeze_vectors.json"
        if sibling.is_file():
            if sibling.read_bytes() != raw:
                raise AssertionError("platform and infra freeze_vectors.json differ")
        elif os.environ.get("BIFROST_CI"):
            raise AssertionError(f"sibling vectors missing: {sibling}")

    def test_every_case_on_the_binary_verdict(self) -> None:
        self.assertGreaterEqual(len(self.file["cases"]), 20)
        print(f"vector cases {len(self.file['cases'])}")
        for case in self.file["cases"]:
            with self.subTest(case=case["name"]):
                if case.get("transport"):
                    got = fg.decide_transport(case["transport"])
                else:
                    got = fg.decide_http(case["status"], _body(case))
                self.assertEqual(got.verdict == "clear", case["clear"], case["name"])
                if case["clear"]:
                    self.assertEqual(got.lines[0], case["first_line"])

    def test_url_has_no_query_and_the_budget_is_ten_seconds(self) -> None:
        self.assertNotIn("?", fg.FREEZE_URL)
        self.assertEqual(fg.read_freeze.__defaults__, (fg.FREEZE_URL, fg.TOKEN_PATH, fg.CA_PATH))
        self.assertEqual(fg.READ_TIMEOUT_S, 10)


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cert, self.key = _cert(root, "kubernetes.default.svc", "DNS:kubernetes.default.svc,IP:127.0.0.1")
        self.bad_cert, self.bad_key = _cert(root, "wrong.example", "DNS:wrong.example")
        self.token = root / "token"
        self.token.write_text("gate-token\n", encoding="utf-8")
        self.ca = self.cert

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _serve(self, respond, cert=None, key=None, protos=("http/1.1",), drip: float = 0) -> _Server:
        server = _Server(cert or self.cert, key or self.key, respond, protos, drip)
        self.addCleanup(server.close)
        return server

    def _read(self, server: _Server, **kwargs):
        return fg.read_freeze(
            f"https://127.0.0.1:{server.port}/x",
            str(self.token),
            str(self.ca),
            **kwargs,
        )

    def test_one_get_is_http11_and_ignores_proxy_env(self) -> None:
        server = self._serve(lambda _n, _req: _http("200 OK", "", CLEAR))
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:1"
        os.environ["https_proxy"] = "http://127.0.0.1:1"
        try:
            got = self._read(server)
        finally:
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("https_proxy", None)
        self.assertEqual(got.verdict, "clear", got.lines)
        reqs = server.requests()
        self.assertEqual(len(reqs), 1)
        text = reqs[0].decode("latin-1")
        self.assertTrue(text.startswith("GET /apis/release.bifrost.io/v1/freezes HTTP/1.1\r\n"), text)
        self.assertNotIn("?", text.split("\r\n", 1)[0])
        self.assertIn("Accept: application/json\r\n", text)
        self.assertIn("Accept-Encoding: identity\r\n", text)
        self.assertIn("Authorization: Bearer gate-token\r\n", text)
        self.assertIn("Host: kubernetes.default.svc\r\n", text)

    def test_no_redirect(self) -> None:
        def respond(n: int, _req: bytes) -> bytes:
            if n == 0:
                return _http("302 Found", "Location: /elsewhere\r\nContent-Length: 0\r\n", b"")
            return _http("200 OK", "", CLEAR)
        server = self._serve(respond)
        got = self._read(server)
        self.assertNotEqual(got.verdict, "clear")
        self.assertEqual(len(server.requests()), 1)

    def test_content_encoding(self) -> None:
        for headers in (
            "Content-Encoding: gzip\r\n",
            "content-encoding: identity\r\n",
            "Content-Encoding:\r\nContent-Encoding: gzip\r\n",
        ):
            server = self._serve(lambda _n, _req, headers=headers: _http("200 OK", headers, CLEAR))
            self.assertNotEqual(self._read(server).verdict, "clear", headers)

    def test_body_limit(self) -> None:
        def pad(n: int) -> bytes:
            body = CLEAR + b" " * n
            return body[:n]
        self.assertTrue(fg.member_of_l(pad(4096)))
        ok = self._serve(lambda _n, _req: _http("200 OK", "", pad(4096)))
        self.assertEqual(self._read(ok).verdict, "clear")
        big = self._serve(lambda _n, _req: _http("200 OK", "", pad(4097)))
        self.assertNotEqual(self._read(big).verdict, "clear")

    def test_truncated_content_length(self) -> None:
        raw = _http("200 OK", f"Content-Length: {len(CLEAR) + 8}\r\n", CLEAR)
        server = self._serve(lambda _n, _req: raw)
        self.assertNotEqual(self._read(server).verdict, "clear")

    def test_chunked(self) -> None:
        def framed(tail: str) -> bytes:
            head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            return head + f"{len(CLEAR):x}\r\n".encode() + CLEAR + b"\r\n" + tail.encode()
        ok = self._serve(lambda _n, _req: framed("0\r\n\r\n"))
        self.assertEqual(self._read(ok).verdict, "clear", self._read(ok).lines)
        short = self._serve(lambda _n, _req: framed("0\r\n"))
        self.assertNotEqual(self._read(short).verdict, "clear")
        open_chunk = self._serve(lambda _n, _req: framed(""))
        self.assertNotEqual(self._read(open_chunk).verdict, "clear")

    def test_interim(self) -> None:
        for code in ("100 Continue", "102 Processing", "103 Early Hints"):
            payload = _http(code, "", b"") + _http("200 OK", "", CLEAR)
            server = self._serve(lambda _n, _req, payload=payload: payload)
            self.assertEqual(self._read(server).verdict, "clear", code)
        payload = _http("101 Switching Protocols", "", b"") + _http("200 OK", "", CLEAR)
        server = self._serve(lambda _n, _req: payload)
        self.assertNotEqual(self._read(server).verdict, "clear")

    def test_wrong_hostname(self) -> None:
        server = self._serve(
            lambda _n, _req: _http("200 OK", "", CLEAR),
            cert=self.bad_cert,
            key=self.bad_key,
        )
        got = fg.read_freeze(
            f"https://127.0.0.1:{server.port}/x",
            str(self.token),
            str(self.bad_cert),
        )
        self.assertNotEqual(got.verdict, "clear", got.lines)

    def test_clear_returns_without_waiting_for_the_peer_to_read(self) -> None:
        """A clear response is complete at 0.6 of the budget; the peer then reads nothing. The answer comes back at once."""
        body = CLEAR
        raw = b"HTTP/1.1 200\r\nContent-Length: %d\r\n\r\n" % len(body) + body
        for budget in (0.2, 10.0):
            stop = threading.Event()
            threads: list[threading.Thread] = []

            def dial(_host, _port, ctx, deadline, budget=budget, stop=stop):
                a, b = socket.socketpair()
                sc = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                sc.minimum_version = ssl.TLSVersion.TLSv1_2
                sc.load_cert_chain(certfile=self.cert, keyfile=self.key)
                sc.set_alpn_protocols(["http/1.1"])

                def serve() -> None:
                    server = sc.wrap_socket(b, server_side=True)
                    try:
                        req = b""
                        while b"\r\n\r\n" not in req:
                            chunk = server.recv(4096)
                            if not chunk:
                                return
                            req += chunk
                        time.sleep(budget * 0.6)
                        server.sendall(raw)
                        stop.wait()
                    finally:
                        server.close()

                thread = threading.Thread(target=serve)
                thread.start()
                threads.append(thread)
                fg._arm(a, deadline)
                return ctx.wrap_socket(a, server_hostname=fg.ORIGIN_HOST)

            start = time.monotonic()
            got = fg.read_freeze(token_path=str(self.token), ca_path=str(self.cert), dial=dial, budget=budget)
            elapsed = time.monotonic() - start
            stop.set()
            for thread in threads:
                thread.join(budget + 2)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(got.verdict, "clear", (budget, got.lines, elapsed))
            self.assertLessEqual(elapsed, budget + 0.25, (budget, elapsed))

    def test_slow_drip(self) -> None:
        server = self._serve(lambda _n, _req: _http("200 OK", "", CLEAR), drip=0.015)
        start = time.monotonic()
        got = self._read(server, budget=0.2)
        elapsed = time.monotonic() - start
        self.assertNotEqual(got.verdict, "clear", got.lines)
        self.assertLess(elapsed, 2.0, elapsed)

    def test_failing_dial(self) -> None:
        server = self._serve(lambda _n, _req: _http("200 OK", "", CLEAR))

        def dial(*_args, **_kwargs):
            raise ValueError("dial failed")

        got = self._read(server, dial=dial)
        self.assertNotEqual(got.verdict, "clear")

        def wrap(_fp):
            class Bad:
                def read(self, _n=-1):
                    raise OSError("read failed")

                def readline(self, _n=-1):
                    raise OSError("read failed")
            return Bad()

        self.assertNotEqual(self._read(server, wrap=wrap).verdict, "clear")

        def hook():
            raise RuntimeError("hook")

        self.assertNotEqual(self._read(server, hook=hook).verdict, "clear")

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self._read(server, hook=interrupt)

    def test_http_client_does_not_refuse_a_zero_chunk_at_eof(self) -> None:
        """stdlib http.client accepts 0\\r\\n then EOF. The gate must not."""
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        body = CLEAR
        payload = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n"
        )

        def once() -> None:
            conn, _ = sock.accept()
            try:
                conn.recv(4096)
                conn.sendall(payload)
            finally:
                conn.close()

        threading.Thread(target=once, daemon=True).start()
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request("GET", "/")
        resp = client.getresponse()
        got = resp.read()
        self.assertEqual(got, body)
        sock.close()
        print(f"python {sys.version.split()[0]} http.client accepted a zero chunk at EOF")

    def test_clear_writes_the_cut_stamp(self) -> None:
        server = self._serve(lambda _n, _req: _http("200 OK", "", CLEAR))
        path = Path(self.tmp.name) / "cut"
        os.environ["PASSED_CUT_AT_PATH"] = str(path)
        real = fg.read_freeze

        def patched(*_a, **_k):
            return real(f"https://127.0.0.1:{server.port}/x", str(self.token), str(self.ca))

        fg.read_freeze = patched
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = fg.main()
        finally:
            fg.read_freeze = real
            os.environ.pop("PASSED_CUT_AT_PATH", None)
        self.assertEqual(code, 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], fg.LINE_CLEAR)
        self.assertRegex(lines[1], r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
        written = datetime.strptime(lines[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs(datetime.now(timezone.utc) - written), timedelta(seconds=5))

    def test_refusal_does_not_write_the_cut_path(self) -> None:
        path = Path(self.tmp.name) / "cut-no"
        os.environ["PASSED_CUT_AT_PATH"] = str(path)
        real = fg.read_freeze
        fg.read_freeze = lambda *_a, **_k: fg.decide_http(404, b"")
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = fg.main()
        finally:
            fg.read_freeze = real
            os.environ.pop("PASSED_CUT_AT_PATH", None)
        self.assertEqual(code, 1)
        self.assertFalse(path.exists())
        self.assertTrue(buf.getvalue().startswith("拒绝："))

    def test_missing_token_and_ca(self) -> None:
        missing = fg.read_freeze(fg.FREEZE_URL, str(Path(self.tmp.name) / "no-token"), str(self.ca))
        self.assertNotEqual(missing.verdict, "clear")
        self.assertEqual(missing.reason, "missing token")
        no_ca = fg.read_freeze(fg.FREEZE_URL, str(self.token), str(Path(self.tmp.name) / "no-ca"))
        self.assertEqual(no_ca.reason, "missing CA")
        self.assertNotEqual(no_ca.verdict, "clear")


if __name__ == "__main__":
    unittest.main()
