"""release.sh policy / freeze / unfreeze against a fake platform-api (W-42). No cluster."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RELEASE_SH = HERE / "release.sh"


class FakePlatform:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict, dict]] = []
        self.status = {"valid": False, "remaining_seconds": 0, "allow": [], "frozen": False,
                       "reasons": ["no signed policy"], "anchor_fingerprint": ""}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # noqa: D401
                pass

            def _serve(self) -> None:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                fake.requests.append((self.command, self.path, body, dict(self.headers)))
                code, out = fake.answer(self.command, self.path, body)
                raw = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_PUT = do_POST = _serve

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def answer(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        if method == "GET" and path == "/api/v1/release-policy":
            return 200, self.status
        if method == "POST" and path == "/api/v1/release-policy/freeze":
            self.status.update(frozen=True, freeze_reason=body["reason"], frozen_at="2026-10-10T09:00:00Z")
            return 200, self.status
        if method == "POST" and path == "/api/v1/release-policy/unfreeze":
            if not body["text"].startswith(f"unfreeze frozen_at={self.status['frozen_at']} "):
                return 409, {"error": "unfreeze is for another freeze"}
            self.status.update(frozen=False)
            return 200, self.status
        if method == "PUT" and path == "/api/v1/release-policy":
            doc = json.loads(body["policy_yaml"])
            self.status.update(valid=True, policy_id=doc["policy_id"], expires_at=doc["expires_at"],
                               remaining_seconds=90 * 86400, allow=doc["allow"], reasons=[])
            return 200, self.status
        return 404, {"error": "not found"}

    def close(self) -> None:
        self.server.shutdown()


class ReleasePolicyCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.fake = FakePlatform()
        self.key = self.tmp / "owner_key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(self.key)], check=True)
        self.env = dict(os.environ, PLATFORM_API=self.fake.url, ENV_FILE=str(self.tmp / "none.env"),
                        PLATFORM_PROD_OPERATOR_TOKEN="op-token", PLATFORM_PROD_VIEWER_TOKEN="view-token",
                        BIFROST_RELEASE_HOME=str(self.tmp / "home"), BIFROST_RELEASE_KEY=str(self.key),
                        BIFROST_RELEASE_WHO="tester@host")

    def tearDown(self) -> None:
        self.fake.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verifies(self, text: str, sig: str, namespace: str) -> bool:
        sig_file = self.tmp / "check.sig"
        sig_file.write_text(sig)
        signers = self.tmp / "signers"
        signers.write_text("owner " + self.key.with_suffix(".pub").read_text())
        res = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", "owner", "-n", namespace,
                              "-s", str(sig_file)], input=text, capture_output=True, text=True, check=False)
        return res.returncode == 0

    def run_sh(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(RELEASE_SH), *args], env=self.env, capture_output=True, text=True,
                              timeout=60, check=False)

    def test_status_reads_the_platform_with_the_viewer_token(self) -> None:
        res = self.run_sh("policy", "status")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("policy    none", res.stdout)
        self.assertIn("nothing auto-approves", res.stdout)
        method, path, _, headers = self.fake.requests[-1]
        self.assertEqual((method, path), ("GET", "/api/v1/release-policy"))
        self.assertEqual(headers.get("Authorization"), "Bearer view-token")

    def test_freeze_then_signed_unfreeze(self) -> None:
        self.assertNotEqual(self.run_sh("freeze").returncode, 0)
        res = self.run_sh("freeze", "--reason", "incident")
        self.assertEqual(res.returncode, 0, res.stderr)
        _, path, body, headers = self.fake.requests[-1]
        self.assertEqual(path, "/api/v1/release-policy/freeze")
        self.assertEqual(body, {"who": "tester@host", "reason": "incident"})
        self.assertEqual(headers.get("Authorization"), "Bearer op-token")

        res = self.run_sh("unfreeze")
        self.assertEqual(res.returncode, 0, res.stderr)
        _, path, body, _ = self.fake.requests[-1]
        self.assertEqual(path, "/api/v1/release-policy/unfreeze")
        self.assertRegex(body["text"], r"^unfreeze frozen_at=2026-10-10T09:00:00Z at=\S+Z by=tester@host\n$")
        self.assertIn("BEGIN SSH SIGNATURE", body["sig"])
        self.assertTrue(self.verifies(body["text"], body["sig"], "bifrost-release-unfreeze"))
        self.assertIn("frozen    False", res.stdout)
        self.assertIn("not frozen", self.run_sh("unfreeze").stdout)

    def test_sign_renders_signs_and_installs(self) -> None:
        res = self.run_sh("policy", "sign", "--days", "30")
        self.assertEqual(res.returncode, 0, res.stderr)
        method, path, body, _ = self.fake.requests[-1]
        self.assertEqual((method, path), ("PUT", "/api/v1/release-policy"))
        doc = json.loads(body["policy_yaml"])
        self.assertEqual(doc["valid_days"], 30)
        self.assertTrue(self.verifies(body["policy_yaml"], body["policy_sig"], "bifrost-release-policy"))
        self.assertFalse(self.verifies(body["policy_yaml"], body["policy_sig"], "bifrost-release-unfreeze"))
        self.assertIn(f"policy    {doc['policy_id']}", res.stdout)
        kept = self.tmp / "home/policy" / doc["policy_id"]
        self.assertTrue((kept / "policy.yaml").is_file() and (kept / "policy.sig").is_file())

    def test_sign_without_a_key_refuses(self) -> None:
        self.env["BIFROST_RELEASE_KEY"] = str(self.tmp / "missing")
        res = self.run_sh("policy", "sign")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("ssh-keygen -t ed25519", res.stderr)
        self.assertEqual(self.fake.requests, [])


class ReleaseShStaticTests(unittest.TestCase):
    def test_prod_request_follows_a_policy_to_the_direct_route(self) -> None:
        text = RELEASE_SH.read_text(encoding="utf-8")
        body = text[text.index("start_prod_run() {"):]
        body = body[: body.index("\n}\n")]
        self.assertIn("auto_approved_by", body)
        self.assertIn('"${PLATFORM_HTTP}" == "400"', body)
        self.assertIn("/api/v1/delivery/pipelines/bifrost-deliver-prod/runs", body)

    def test_release_sh_judges_no_policy_itself(self) -> None:
        text = RELEASE_SH.read_text(encoding="utf-8")
        self.assertNotIn("policy_check", text)
        self.assertNotIn("allowed_signers", text)
        self.assertIsNone(re.search(r"kubectl[^\n]*bifrost-release-(policy|freeze)", text))

    def test_tekton_freeze_step_reads_the_flag(self) -> None:
        task = (ROOT / "k8s/cicd/tekton/task-release-window.yaml").read_text(encoding="utf-8")
        self.assertIn("- name: freeze", task)
        self.assertIn("configmaps/bifrost-release-freeze", task)
        self.assertIn("exc.code != 404", task)
        rbac = (ROOT / "k8s/cicd/tekton/rbac-release-window.yaml").read_text(encoding="utf-8")
        self.assertIn('"bifrost-release-freeze"', rbac)


if __name__ == "__main__":
    unittest.main()
