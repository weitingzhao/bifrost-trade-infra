"""The Python reader of the freeze gate is held to the verdict the language H gives every raw response."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import freeze_gate  # noqa: E402
import freeze_http_vectors  # noqa: E402

# The platform repository carries the same bytes and the same constant (http_vectors_test.go).
HTTP_VECTORS_SHA256 = "e1e45356cbbd1d41496f634f30c0caa1714ad0319990d017e875cb58a16aa68e"
VECTORS = HERE / "freeze_http_vectors.json"


class _Sock:
    def settimeout(self, _t) -> None:
        pass

    def sendall(self, _b) -> None:
        raise OSError("the gate tried to send a second request")

    def close(self) -> None:
        pass


def read_from_memory(raw: bytes) -> bool:
    """Run the gate's reader over raw response bytes; every recoverable failure is not clear."""
    try:
        got = freeze_gate._read_http(io.BufferedReader(io.BytesIO(raw)), _Sock(), time.monotonic() + 3600, "t", freeze_gate.ORIGIN_HOST, 443, None, None)
    except Exception:
        return False
    return got.verdict == "clear"


class HTTPVectorTests(unittest.TestCase):
    def test_the_file_is_what_the_recogniser_generates(self) -> None:
        raw = VECTORS.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), HTTP_VECTORS_SHA256)
        self.assertEqual(raw.decode("ascii"), freeze_http_vectors.document())

    def test_http_vectors(self) -> None:
        cases = json.loads(VECTORS.read_bytes())["cases"]
        self.assertGreaterEqual(len(cases), 280)
        wrong = [c["name"] for c in cases if read_from_memory(bytes.fromhex(c["hex"])) != c["clear"]]
        self.assertEqual(wrong, [])
        self.assertGreaterEqual(sum(1 for c in cases if c["clear"]), 40)

    def test_the_recogniser_accepts_the_measured_response_shape(self) -> None:
        body = freeze_http_vectors.M
        raw = (
            b"HTTP/1.1 200 OK\r\nAudit-Id: 6f1f0b2e-7a34-4e0b-9d7f-0c1d2e3f4a5b\r\nCache-Control: no-cache, private\r\n"
            b"Content-Type: application/json\r\nX-Kubernetes-Pf-Flowschema-Uid: 0d4c2a6e-3b1f-4c8a-9a57-1e2f3a4b5c6d\r\n"
            b"Date: Sun, 11 Oct 2026 21:00:00 GMT\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        )
        self.assertTrue(freeze_http_vectors.clear(raw))
        self.assertTrue(read_from_memory(raw))


if __name__ == "__main__":
    unittest.main()
