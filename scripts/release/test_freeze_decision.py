"""Fail-closed freeze decision and in-flight outcomes. No cluster."""

from __future__ import annotations

import http.client
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import freeze_decision as fd  # noqa: E402
import freeze_inflight as fi  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK = ROOT / "k8s/cicd/tekton/task-release-freeze-check.yaml"

FROZEN = {
    "frozen": "true",
    "seq": "1",
    "reason": "incident",
    "who": "ada@host",
    "frozen_at": "2026-10-10T09:00:00Z",
}

UNFROZEN = {
    "frozen": "false",
    "seq": "1",
    "reason": "incident",
    "who": "ada@host",
    "frozen_at": "2026-10-10T09:00:00Z",
    "unfreeze_seq": "1",
    "unfreeze_frozen_at": "2026-10-10T09:00:00Z",
    "unfreeze_at": "2026-10-10T10:00:00Z",
    "unfreeze_by": "owner@host",
    "unfreeze_text": "unfreeze frozen_at=2026-10-10T09:00:00Z at=2026-10-10T10:00:00Z by=owner@host\n",
    "unfreeze_sig": "signed",
}


def unread(what: str) -> str:
    return fd.REFUSE_UNREADABLE.format(what=what)


class DecideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = mock.patch.object(fd, "checked_at", return_value="2026-10-11T08:00:00Z")
        self.clock.start()

    def tearDown(self) -> None:
        self.clock.stop()

    def test_initial_object_is_the_only_bare_allow(self) -> None:
        initial = fd.schema()["initial"]
        allow, line = fd.decide(dict(initial))
        self.assertTrue(allow)
        self.assertEqual(line, "未冻结：2026-10-11T08:00:00Z")
        code, text = fd.render(dict(initial))
        self.assertEqual(code, 0)
        self.assertEqual(text, "未冻结：2026-10-11T08:00:00Z\n")

    def test_frozen_true_refuses_with_reason_and_time(self) -> None:
        allow, line = fd.decide(dict(FROZEN))
        self.assertFalse(allow)
        self.assertEqual(
            line,
            "拒绝：发布已冻结（incident，2026-10-10T09:00:00Z）；解冻要 Owner 签名",
        )
        self.assertEqual(fd.render(dict(FROZEN))[0], 1)

    def test_not_found_other_http_timeout_and_unparsable(self) -> None:
        self.assertEqual(fd.decide(fd.ReadError("404"))[1], unread("404"))
        self.assertEqual(fd.decide(fd.ReadError("HTTP 500"))[1], unread("HTTP 500"))
        self.assertEqual(fd.decide(fd.ReadError("timeout"))[1], unread("timeout"))
        self.assertEqual(fd.decide(["not", "a", "map"])[1], unread("unparsable response"))
        self.assertEqual(fd.decide(fd.ReadError("unparsable response"))[1], unread("unparsable response"))
        self.assertIsInstance(fd.data_from_envelope({"kind": "Pod", "data": {}}), fd.ReadError)
        self.assertIsInstance(fd.data_from_envelope({"kind": "ConfigMap"}), fd.ReadError)
        self.assertEqual(fd.data_from_envelope({"kind": "ConfigMap", "data": {"frozen": "false", "seq": "0"}}),
                         {"frozen": "false", "seq": "0"})

    def test_http_errors_map_to_the_same_causes(self) -> None:
        not_found = urllib.error.HTTPError(fd.FREEZE_URL, 404, "missing", {}, None)
        other = urllib.error.HTTPError(fd.FREEZE_URL, 403, "denied", {}, None)
        self.assertEqual(fd.failure_from_http(not_found).what, "404")
        self.assertEqual(fd.failure_from_http(other).what, "HTTP 403")
        self.assertEqual(fd.failure_from_http(TimeoutError()).what, "timeout")
        self.assertEqual(fd.failure_from_http(json.JSONDecodeError("bad", "x", 0)).what, "unparsable response")

    def test_missing_field_unknown_field_and_bool_frozen(self) -> None:
        broken = dict(FROZEN)
        del broken["reason"]
        self.assertEqual(fd.decide(broken)[1], unread("missing field reason"))
        extra = dict(fd.schema()["initial"])
        extra["note"] = "hello"
        self.assertEqual(fd.decide(extra)[1], unread("unknown field note"))
        self.assertEqual(fd.decide({"frozen": True, "seq": "0"})[1], unread("field frozen is not a string"))
        self.assertEqual(fd.decide({"frozen": False, "seq": "0"})[1], unread("field frozen is not a string"))
        self.assertEqual(fd.decide({"frozen": "yes", "seq": "0"})[1], unread('frozen is not "true" or "false"'))
        self.assertEqual(fd.decide({"frozen": " true", "seq": "0"})[1], unread('frozen is not "true" or "false"'))

    def test_unfreeze_shape_is_allowed_without_verifying_the_signature(self) -> None:
        code, text = fd.render(dict(UNFROZEN))
        self.assertEqual(code, 0)
        self.assertEqual(
            text,
            "未冻结：2026-10-11T08:00:00Z\nnote: un-freeze signature not verified (slice C)\n",
        )
        partial = dict(UNFROZEN)
        del partial["unfreeze_sig"]
        self.assertEqual(fd.decide(partial)[1], unread("missing field unfreeze_sig"))
        self.assertNotIn("ssh-keygen", Path(fd.__file__).read_text(encoding="utf-8"))

    def test_frozen_shape_rejects_a_zero_seq_and_an_unfreeze_field(self) -> None:
        zero = dict(FROZEN)
        zero["seq"] = "0"
        self.assertEqual(fd.decide(zero)[1], unread("field seq is 0 while frozen"))
        extra = dict(FROZEN)
        extra["unfreeze_sig"] = "signed"
        self.assertEqual(fd.decide(extra)[1], unread("unknown field unfreeze_sig"))

    def test_allow_writes_passed_cut_at_and_refusal_does_not(self) -> None:
        dest = HERE / "_passed_cut_at"
        try:
            with mock.patch.object(fd, "load_freeze", return_value=dict(fd.schema()["initial"])):
                with mock.patch.dict("os.environ", {"PASSED_CUT_AT_PATH": str(dest)}):
                    self.assertEqual(fd.main(), 0)
            self.assertEqual(dest.read_text(encoding="utf-8"), "2026-10-11T08:00:00Z")
            dest.unlink()
            with mock.patch.object(fd, "load_freeze", return_value=dict(FROZEN)):
                with mock.patch.dict("os.environ", {"PASSED_CUT_AT_PATH": str(dest)}):
                    buf = io.StringIO()
                    with mock.patch("sys.stdout", buf):
                        self.assertEqual(fd.main(), 1)
            self.assertFalse(dest.exists())
            self.assertTrue(buf.getvalue().startswith("拒绝：发布已冻结（"))
        finally:
            dest.unlink(missing_ok=True)

    def test_missing_ca_corrupt_ca_bad_utf8_and_truncated_body(self) -> None:
        class Body:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def read(self) -> bytes:
                if isinstance(self.payload, BaseException):
                    raise self.payload
                return self.payload  # type: ignore[return-value]

            def __enter__(self) -> "Body":
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

        def refusal(line: str, what: str) -> None:
            self.assertEqual(line, unread(what))
            self.assertFalse(line.startswith("Traceback"))

        def run_main() -> str:
            out = io.StringIO()
            err = io.StringIO()
            with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
                code = fd.main()
            self.assertEqual(code, 1)
            self.assertEqual(err.getvalue(), "")
            first = out.getvalue().splitlines()[0]
            refusal(first, first.split("（", 1)[1].split("）", 1)[0])
            return first

        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token"
            token.write_text("token", encoding="utf-8")
            missing = Path(tmp) / "missing.crt"
            corrupt = Path(tmp) / "ca.crt"
            corrupt.write_text("not a certificate\n", encoding="utf-8")
            with mock.patch.object(fd, "TOKEN_PATH", str(token)):
                with mock.patch.object(fd, "CA_PATH", str(missing)):
                    self.assertEqual(run_main(), unread("missing CA"))
                with mock.patch.object(fd, "CA_PATH", str(corrupt)):
                    self.assertEqual(run_main(), unread("corrupt CA"))
                with mock.patch.object(fd, "CA_PATH", str(corrupt)), mock.patch.object(
                    fd.ssl, "create_default_context", return_value=object()
                ):
                    with mock.patch.object(fd.urllib.request, "urlopen", return_value=Body(b"\xff\xfe")):
                        self.assertEqual(run_main(), unread("invalid UTF-8"))
                    with mock.patch.object(
                        fd.urllib.request,
                        "urlopen",
                        return_value=Body(http.client.IncompleteRead(b'{"data":')),
                    ):
                        self.assertEqual(run_main(), unread("truncated body"))
                    with mock.patch.object(
                        fd.urllib.request,
                        "urlopen",
                        return_value=Body(b'{"kind":"ConfigMap","data":'),
                    ):
                        self.assertEqual(run_main(), unread("unparsable response"))


class InFlightTests(unittest.TestCase):
    def test_positions(self) -> None:
        self.assertEqual(fi.outcome("pending_before_check"), "refused")
        self.assertEqual(fi.outcome("paused_before_check"), "refused")
        self.assertEqual(fi.outcome("past_cut"), "continues")
        self.assertEqual(fi.outcome("check_timeout"), "refused")
        self.assertEqual(fi.outcome("check_cancelled"), "refused")
        self.assertEqual(fi.outcome("partial_push"), "recorded_as_is")

    def test_receipt_names_only_a_running_run_past_the_cut(self) -> None:
        self.assertEqual(fi.receipt_name("2026-10-11T08:00:00Z", "bifrost-deliver-platform-prod-ab", True),
                         "bifrost-deliver-platform-prod-ab")
        self.assertEqual(fi.receipt_name("", "bifrost-deliver-platform-prod-ab", True), "")
        self.assertEqual(fi.receipt_name("2026-10-11T08:00:00Z", "bifrost-deliver-platform-prod-ab", False), "")
        self.assertIn("passed_cut_at", fi.LIST_HINT)
        self.assertIn("tekton.dev/pipelineRun", fi.LIST_HINT)

    def test_task_publishes_the_result_and_does_not_continue_on_error(self) -> None:
        import yaml

        docs = list(yaml.safe_load_all(TASK.read_text(encoding="utf-8")))
        task = next(doc for doc in docs if doc["kind"] == "Task")
        results = task["spec"]["results"]
        self.assertEqual([item["name"] for item in results], [fi.PASSED_CUT_RESULT])
        step = task["spec"]["steps"][0]
        script = step["script"]
        self.assertTrue(script.startswith("#!/bin/sh\n"))
        self.assertNotIn("def decide", script)
        self.assertNotIn("onError", yaml.safe_dump(task))
        self.assertIn("timeout", step)
        mounted = task["spec"]["volumes"][0]["configMap"]["name"]
        config = next(doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == mounted)
        self.assertEqual(config["data"]["freeze_decision.py"], (HERE / "freeze_decision.py").read_text(encoding="utf-8"))
        self.assertEqual(config["data"]["freeze_schema.json"], (HERE / "freeze_schema.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
