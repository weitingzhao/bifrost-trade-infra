"""The freeze gate: vectors, one TLS read, no environment redirect. No cluster."""

from __future__ import annotations

import base64
import hashlib
import http.server
import io
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import freeze_gate as fg

HERE = Path(__file__).resolve().parent
VECTORS = HERE / "freeze_vectors.json"

# Same digest as api/internal/releasefreeze/vectors_test.go.
FREEZE_VECTORS_SHA256 = "a5f19e65ba542bb7de6180462032991c10021467b6642a24dc88ba8ff4f6a3ee"


def _body(case: dict) -> bytes:
    if case.get("body_base64"):
        return base64.standard_b64decode(case["body_base64"])
    return case.get("body", "").encode("utf-8")


def _decide(case: dict) -> fg.Decision:
    if case.get("transport"):
        return fg.decide_transport(case["transport"])
    return fg.decide_http(case["status"], _body(case))


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = VECTORS.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != FREEZE_VECTORS_SHA256:
            raise AssertionError(f"vector digest {digest}")
        cls.file = json.loads(raw)
        cls.patterns = [re.compile(p) for p in cls.file["patterns"]]

    def test_token_list_matches_the_module(self) -> None:
        self.assertEqual(list(fg.REASON_TOKENS), self.file["tokens"])

    def test_every_case(self) -> None:
        allowed = set(self.file["tokens"])
        for case in self.file["cases"]:
            with self.subTest(case=case["name"]):
                got = _decide(case)
                self.assertEqual(got.verdict, case["verdict"], case["name"])
                self.assertEqual(got.lines[0], case["first_line"], case["name"])
                if case["verdict"] == "unreadable":
                    self.assertTrue(self._reason_ok(got.reason, allowed), got.reason)
                if "lines" in case:
                    self.assertEqual(got.lines, case["lines"])
                if "records" in case:
                    got_recs = [
                        {
                            "name": r.name,
                            "uid": r.uid,
                            "who": r.who,
                            "reason": r.reason,
                            "at": r.at,
                            "via": r.via,
                        }
                        for r in got.records
                    ]
                    self.assertEqual(got_recs, case["records"])

    def _reason_ok(self, reason: str, allowed: set[str]) -> bool:
        if reason in allowed:
            return True
        return any(p.fullmatch(reason) for p in self.patterns)

    def test_url_has_no_query_and_defaults_are_the_constants(self) -> None:
        self.assertNotIn("?", fg.FREEZE_URL)
        self.assertEqual(fg.read_freeze.__defaults__, (fg.FREEZE_URL, fg.TOKEN_PATH, fg.CA_PATH))
        self.assertEqual(fg.READ_TIMEOUT_S, 10)


def _self_signed(root: Path) -> tuple[Path, Path]:
    cert = root / "ca.pem"
    key = root / "ca.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        cert, key = _self_signed(root)
        self.token = root / "token"
        self.token.write_text("gate-token\n", encoding="utf-8")
        self.ca = cert
        self.hits: list[tuple[str, str, str, str]] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = self.path.split("?", 1)
                query = parsed[1] if len(parsed) > 1 else ""
                outer.hits.append((self.command, parsed[0], query, self.headers.get("Authorization", "")))
                body = b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{},"items":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args) -> None:
                return

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        port = self.httpd.server_address[1]
        self.url = f"https://127.0.0.1:{port}/apis/release.bifrost.io/v1/freezes"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.tmp.cleanup()

    def test_one_get_without_a_query_and_a_verified_ca(self) -> None:
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
        os.environ["https_proxy"] = "http://127.0.0.1:1"
        os.environ["FREEZE_URL"] = "https://127.0.0.1:1/elsewhere"
        try:
            got = fg.read_freeze(self.url, str(self.token), str(self.ca))
        finally:
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("https_proxy", None)
            os.environ.pop("FREEZE_URL", None)
        self.assertEqual(got.verdict, "clear", got.lines)
        self.assertEqual(len(self.hits), 1)
        method, path, query, auth = self.hits[0]
        self.assertEqual((method, path, query), ("GET", "/apis/release.bifrost.io/v1/freezes", ""))
        self.assertEqual(auth, "Bearer gate-token")

    def test_reused_and_fresh_calls_match(self) -> None:
        first = fg.read_freeze(self.url, str(self.token), str(self.ca))
        second = fg.read_freeze(self.url, str(self.token), str(self.ca))
        self.assertEqual(first.lines, second.lines)
        self.assertEqual(len(self.hits), 2)

    def test_clear_writes_the_cut_stamp(self) -> None:
        path = Path(self.tmp.name) / "cut"
        os.environ["PASSED_CUT_AT_PATH"] = str(path)
        real = fg.read_freeze
        fg.read_freeze = lambda *a, **k: real(self.url, str(self.token), str(self.ca))
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
        self.assertEqual(path.read_text(encoding="utf-8").strip(), lines[1])
        stamp = datetime.now(timezone.utc)
        written = datetime.strptime(lines[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs(stamp - written), timedelta(seconds=5))

    def test_refusal_does_not_write_the_cut_path(self) -> None:
        path = Path(self.tmp.name) / "cut-no"
        os.environ["PASSED_CUT_AT_PATH"] = str(path)
        real = fg.read_freeze
        fg.read_freeze = lambda *a, **k: fg.decide_http(404, b"")
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
        self.assertEqual(len(buf.getvalue().splitlines()), 1)

    def test_missing_token_missing_ca_and_connection_failure(self) -> None:
        missing = fg.read_freeze(self.url, str(Path(self.tmp.name) / "no-token"), str(self.ca))
        self.assertEqual(missing.reason, "missing token")
        no_ca = fg.read_freeze(self.url, str(self.token), str(Path(self.tmp.name) / "no-ca"))
        self.assertEqual(no_ca.reason, "missing CA")
        closed = fg.read_freeze(
            "https://127.0.0.1:1/apis/release.bifrost.io/v1/freezes",
            str(self.token),
            str(self.ca),
        )
        self.assertEqual(closed.reason, "connection failed")
        self.assertEqual(closed.verdict, "unreadable")

    def test_timeout_maps_to_the_timeout_token(self) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        old = fg.READ_TIMEOUT_S
        fg.READ_TIMEOUT_S = 0.2
        try:
            got = fg.read_freeze(
                f"https://127.0.0.1:{port}/apis/release.bifrost.io/v1/freezes",
                str(self.token),
                str(self.ca),
            )
        finally:
            fg.READ_TIMEOUT_S = old
            sock.close()
        self.assertEqual(got.reason, "timeout", got.lines)


if __name__ == "__main__":
    unittest.main()
