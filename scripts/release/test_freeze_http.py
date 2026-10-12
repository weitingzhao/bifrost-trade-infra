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
HTTP_VECTORS_SHA256 = "daf5e79f9893370e738eb0b5d15a9057caa2a36008fb5e1135aed940ddeaa5f5"
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
        if wrong:
            self.fail("wrong verdicts: " + "; ".join(wrong))
        self.assertGreaterEqual(sum(1 for c in cases if c["clear"]), 40)

    def test_byte_classes(self) -> None:
        """Every byte value at every position outside the body interior: the reader agrees with the recogniser on all 256."""
        classes = json.loads(VECTORS.read_bytes())["byte_classes"]
        total = 0
        wrong = []
        for base in classes:
            raw = bytes.fromhex(base["base"])
            if not base["positions"] or base["positions"][0] != 0:
                self.fail("%s: the first byte of the status line is not a position" % base["name"])
            total += len(base["positions"]) + len(base["insert_positions"])
            self.assertEqual(len(base["positions"]), len(base["replace"]), base["name"])
            self.assertEqual(len(base["insert_positions"]), len(base["insert"]), base["name"])
            for mode, positions, masks, insert in (
                ("replace", base["positions"], base["replace"], False),
                ("insert", base["insert_positions"], base["insert"], True),
            ):
                for k, mask_hex in zip(positions, masks):
                    mask = bytes.fromhex(mask_hex)
                    self.assertEqual(len(mask), 32)
                    for v in range(256):
                        trial = raw[:k] + bytes((v,)) + (raw[k:] if insert else raw[k + 1 :])
                        want = bool(mask[v >> 3] >> (v & 7) & 1)
                        if read_from_memory(trial) != want:
                            wrong.append("%s %s %d 0x%02x" % (base["name"], mode, k, v))
        self.assertGreaterEqual(total, 400, "byte-class positions %d" % total)
        if wrong:
            self.fail("wrong verdicts: " + "; ".join(wrong[:40]))

    def test_second_deadline_hold(self) -> None:
        """The bytes are all available at once. Holding the decision past the deadline, with no socket wait, is not clear."""
        body = freeze_http_vectors.M
        raw = b"HTTP/1.1 200\r\nContent-Length: %d\r\n\r\n" % len(body) + body
        start = time.monotonic()
        fast = freeze_gate._read_http(io.BufferedReader(io.BytesIO(raw)), _Sock(), start + 0.1, "t", freeze_gate.ORIGIN_HOST, 443, None, None)
        self.assertEqual(fast.verdict, "clear")
        original = freeze_gate.decide_http

        def slow(status, data):
            time.sleep(0.12)
            return original(status, data)

        freeze_gate.decide_http = slow
        try:
            start = time.monotonic()
            got = freeze_gate._read_http(io.BufferedReader(io.BytesIO(raw)), _Sock(), start + 0.1, "t", freeze_gate.ORIGIN_HOST, 443, None, None)
        finally:
            freeze_gate.decide_http = original
        self.assertNotEqual(got.verdict, "clear")

    def test_timing(self) -> None:
        """The same bytes at different moments, over a real socket pair: one deadline to the last byte H needs."""
        import socket
        import threading

        wrong = []
        for case in json.loads(VECTORS.read_bytes())["timing"]:
            a, b = socket.socketpair()
            start = time.monotonic()
            stop = threading.Event()

            def serve(steps=case["steps"], peer=b, t0=start, halt=stop) -> None:
                try:
                    for step in steps:
                        if halt.wait(max(0.0, t0 + step["at_ms"] / 1000 - time.monotonic())):
                            return
                        peer.sendall(bytes.fromhex(step["hex"]))
                except OSError:
                    pass

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            deadline = start + case["budget_ms"] / 1000
            try:
                got = freeze_gate._read_http(freeze_gate._Reader(a, deadline), a, deadline, "t", freeze_gate.ORIGIN_HOST, 443, None, None)
                is_clear = got.verdict == "clear"
            except Exception:
                is_clear = False
            took = time.monotonic() - start
            stop.set()
            a.close()
            thread.join(2)
            b.close()
            if is_clear != case["clear"]:
                wrong.append("%s (clear %s after %.3f s)" % (case["name"], is_clear, took))
            elif took > case["budget_ms"] / 1000 + 0.25:
                wrong.append("%s (answered only after %.3f s)" % (case["name"], took))
        if wrong:
            self.fail("wrong verdicts: " + "; ".join(wrong))

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
