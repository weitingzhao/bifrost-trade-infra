"""freeze_lift.sh against a fake API server, using the real kubectl."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "freeze_lift.sh"
NAME = "freeze-" + ("0" * 32)
UID = "11111111-1111-1111-1111-111111111111"
STALE = "22222222-2222-2222-2222-222222222222"


class FakeAPI:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.uid = UID
        self.present = True
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args) -> None:
                return

            def do_DELETE(self) -> None:  # noqa: N802
                self._take("DELETE")

            def do_GET(self) -> None:  # noqa: N802
                self._take("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._take("POST")

            def do_PUT(self) -> None:  # noqa: N802
                self._take("PUT")

            def do_PATCH(self) -> None:  # noqa: N802
                self._take("PATCH")

            def _body(self) -> bytes:
                encoding = (self.headers.get("Transfer-Encoding") or "").lower()
                if "chunked" in encoding:
                    chunks = []
                    while True:
                        line = self.rfile.readline()
                        size = int(line.split(b";", 1)[0].strip() or b"0", 16)
                        if size == 0:
                            while True:
                                trailer = self.rfile.readline()
                                if trailer in (b"\r\n", b"\n", b""):
                                    break
                            break
                        chunks.append(self.rfile.read(size))
                        self.rfile.read(2)
                    return b"".join(chunks)
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def _take(self, method: str) -> None:
                raw = self._body()
                parsed = urllib.parse.urlsplit(self.path)
                body = raw.decode("utf-8", errors="replace")
                fake.requests.append({
                    "method": method,
                    "path": parsed.path,
                    "query": parsed.query,
                    "body": body,
                    "headers": {key: value for key, value in self.headers.items()},
                })
                code, payload = fake.answer(method, parsed.path, body)
                encoded = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def answer(self, method: str, path: str, body: str) -> tuple[int, dict]:
        if method == "DELETE" and path == f"/apis/release.bifrost.io/v1/freezes/{NAME}":
            try:
                doc = json.loads(body) if body else {}
            except json.JSONDecodeError:
                doc = {}
            uid = ((doc.get("preconditions") or {}).get("uid"))
            if uid == self.uid and self.present:
                self.present = False
                return 200, {"kind": "Status", "apiVersion": "v1", "status": "Success"}
            return 409, {
                "kind": "Status",
                "apiVersion": "v1",
                "status": "Failure",
                "message": "the UID in the precondition does not match",
                "reason": "Conflict",
                "code": 409,
            }
        return 404, {"kind": "Status", "apiVersion": "v1", "status": "Failure", "message": "not found", "code": 404}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def kubeconfig(url: str, directory: Path) -> Path:
    path = directory / "kubeconfig"
    path.write_text(
        "apiVersion: v1\n"
        "kind: Config\n"
        "clusters:\n"
        "- name: fake\n"
        "  cluster:\n"
        f"    server: {url}\n"
        "users:\n"
        "- name: none\n"
        "  user: {}\n"
        "contexts:\n"
        "- name: fake\n"
        "  context:\n"
        "    cluster: fake\n"
        "    user: none\n"
        "current-context: fake\n",
        encoding="utf-8",
    )
    return path


class FreezeLiftTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("kubectl") is None:
            self.skipTest("kubectl is not on PATH")
        self.tmp = Path(tempfile.mkdtemp())
        self.owner = FakeAPI()
        self.decoy = FakeAPI()
        self.owner_config = kubeconfig(self.owner.url, self.tmp)
        nested = self.tmp / "nested"
        nested.mkdir()
        self.decoy_config = kubeconfig(self.decoy.url, nested)

    def tearDown(self) -> None:
        if hasattr(self, "owner"):
            self.owner.close()
            self.decoy.close()
            shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, *args: str, owner: str | None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["KUBECONFIG"] = str(self.decoy_config)
        if owner is None:
            env.pop("BIFROST_OWNER_KUBECONFIG", None)
        else:
            env["BIFROST_OWNER_KUBECONFIG"] = owner
        return subprocess.run(
            [str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_missing_owner_kubeconfig_sends_nothing(self) -> None:
        res = self.run_script(NAME, UID, owner=None)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.owner.requests, [])
        self.assertEqual(self.decoy.requests, [])
        self.assertIn("BIFROST_OWNER_KUBECONFIG", res.stderr)

    def test_matching_uid_is_one_delete_and_the_record_is_gone(self) -> None:
        res = self.run_script(NAME, UID, owner=str(self.owner_config))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.decoy.requests, [])
        self.assertEqual(len(self.owner.requests), 1, self.owner.requests)
        got = self.owner.requests[0]
        self.assertEqual(got["method"], "DELETE")
        self.assertEqual(got["path"], f"/apis/release.bifrost.io/v1/freezes/{NAME}")
        self.assertEqual(got["query"], "")
        self.assertEqual(json.loads(got["body"]), {
            "kind": "DeleteOptions",
            "apiVersion": "v1",
            "preconditions": {"uid": UID},
            "propagationPolicy": "Background",
        })
        self.assertFalse(self.owner.present)

    def test_stale_uid_is_409_and_the_record_stays(self) -> None:
        res = self.run_script(NAME, STALE, owner=str(self.owner_config))
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.decoy.requests, [])
        self.assertEqual(len(self.owner.requests), 1, self.owner.requests)
        got = self.owner.requests[0]
        self.assertEqual(got["method"], "DELETE")
        self.assertEqual(got["path"], f"/apis/release.bifrost.io/v1/freezes/{NAME}")
        self.assertEqual(got["query"], "")
        self.assertEqual(json.loads(got["body"])["preconditions"]["uid"], STALE)
        self.assertTrue(self.owner.present)
        self.assertIn("the UID in the precondition does not match", res.stdout + res.stderr)

    def test_quote_backslash_and_injection_send_nothing(self) -> None:
        samples = [
            'uid"probe',
            "uid\\probe",
            'x"},"preconditions":null,"ignored":{"uid":"x',
        ]
        for uid in samples:
            with self.subTest(uid=uid):
                res = self.run_script(NAME, uid, owner=str(self.owner_config))
                self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertEqual(self.owner.requests, [])
                self.assertEqual(self.decoy.requests, [])

    def test_encoder_emits_one_preconditions_key(self) -> None:
        res = subprocess.run(
            ["bash", "-c", 'source "$1"; encode_delete_body "$2"', "bash", str(SCRIPT), UID],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        body = res.stdout
        self.assertEqual(body.count('"preconditions"'), 1, body)
        self.assertEqual(json.loads(body), {
            "kind": "DeleteOptions",
            "apiVersion": "v1",
            "preconditions": {"uid": UID},
            "propagationPolicy": "Background",
        })


if __name__ == "__main__":
    unittest.main()
