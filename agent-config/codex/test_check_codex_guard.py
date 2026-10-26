"""Offline checker regressions; fake RPC peers never change installed hooks."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("codex_guard", Path(__file__).with_name("check-codex-guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
POPEN = subprocess.Popen


def response(cwds):
    return {"id": 2, "result": {"data": [
        {"cwd": cwd, "hooks": [{"eventName": "preToolUse", "command": guard.ADAPTER,
                                "key": "gate", "trustStatus": "trusted", "currentHash": "hash",
                                "enabled": True, "matcher": None}]}
        for cwd in cwds]}}


class HooksRPC(unittest.TestCase):
    def run_peer(self, source, timeout=1):
        children = []

        def launch(_command, **kwargs):
            child = POPEN([sys.executable, "-u", "-c", source], **kwargs)
            children.append(child)
            return child

        try:
            with patch.object(guard.subprocess, "Popen", side_effect=launch), patch.object(guard, "RPC_TIMEOUT", timeout):
                return guard.hooks_list(["/workspace", "/agent-work"])
        finally:
            for child in children:
                self.assertIsNotNone(child.poll(), "checker left its app-server running")

    def test_notifications_and_response_in_one_write(self):
        expected = response(["/workspace", "/agent-work"])
        source = (
            "import sys,json,time\n"
            "sys.stdin.readline()\n"
            "print(json.dumps({'id':1,'result':{}}), flush=True)\n"
            "sys.stdin.readline(); sys.stdin.readline()\n"
            f"sys.stdout.write(json.dumps({{'method':'notice'}})+'\\n'+{json.dumps(json.dumps(expected) + chr(10))})\n"
            "sys.stdout.flush(); time.sleep(5)\n"
        )
        self.assertEqual(self.run_peer(source), expected)

    def test_fragmented_response(self):
        expected = response(["/workspace", "/agent-work"])
        source = (
            "import sys,json,time\n"
            "sys.stdin.readline()\n"
            "print(json.dumps({'id':1,'result':{}}), flush=True)\n"
            "sys.stdin.readline(); sys.stdin.readline()\n"
            f"reply={json.dumps(json.dumps(expected) + chr(10))}\n"
            "sys.stdout.write(reply[:10]); sys.stdout.flush(); time.sleep(.03)\n"
            "sys.stdout.write(reply[10:]); sys.stdout.flush(); time.sleep(5)\n"
        )
        self.assertEqual(self.run_peer(source), expected)

    def test_startup_failure_reports_stderr_and_exit(self):
        with self.assertRaisesRegex(RuntimeError, "exited 7.*Operation not permitted"):
            self.run_peer("import sys; sys.stderr.write('Operation not permitted'); sys.exit(7)")

    def test_rpc_error_is_not_an_empty_success(self):
        with self.assertRaisesRegex(RuntimeError, "RPC 1 failed"):
            self.run_peer("import sys,json,time; sys.stdin.readline(); "
                          "print(json.dumps({'id':1,'error':{'code':-1,'message':'denied'}})); time.sleep(5)")

    def test_timeout_cleans_up(self):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            self.run_peer("import time; time.sleep(5)", timeout=.05)

    def test_malformed_json_fails(self):
        with self.assertRaises(ValueError):
            self.run_peer("import sys,time; sys.stdin.readline(); print('broken json'); time.sleep(5)")


class HookCoverage(unittest.TestCase):
    def test_all_requested_directories_required(self):
        for resp in ({}, {"result": {}}, {"result": {"data": []}}, response(["/workspace"]),
                     response(["/workspace", "/workspace"]), response(["/elsewhere"])):
            with self.subTest(resp=resp), self.assertRaises(RuntimeError):
                guard.validate_hooks_response(resp, ["/workspace", "/agent-work"])

    def test_malformed_hook_fails(self):
        for field, value in (("enabled", "true"), ("matcher", []), ("command", None)):
            resp = response(["/workspace"])
            resp["result"]["data"][0]["hooks"][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                guard.validate_hooks_response(resp, ["/workspace"])

    def test_valid_shape_does_not_change_trust(self):
        resp = response(["/workspace"])
        resp["result"]["data"][0]["hooks"][0]["trustStatus"] = "untrusted"
        guard.validate_hooks_response(resp, ["/workspace"])
        self.assertEqual(resp["result"]["data"][0]["hooks"][0]["trustStatus"], "untrusted")


if __name__ == "__main__":
    unittest.main()
