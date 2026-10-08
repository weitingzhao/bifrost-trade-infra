"""Decision table for the release window and the CI gate. No cluster."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_gate  # noqa: E402
import window_decision as wd  # noqa: E402


SHA = "a" * 40
OTHER = "b" * 40


def _run(repo: str, sha: str, pipeline: str, succeeded: str | None) -> dict:
    conds = []
    if succeeded is not None:
        conds.append({"type": "Succeeded", "status": succeeded})
    return {
        "metadata": {"name": f"{pipeline}-{repo[:12]}", "labels": {"tekton.dev/pipeline": pipeline}},
        "spec": {"params": [{"name": "repo", "value": repo}, {"name": "revision", "value": sha}]},
        "status": {"conditions": conds},
    }


class WindowTests(unittest.TestCase):
    def test_research_refused_without_a_window(self) -> None:
        msg = wd.decide(None, "bifrost-deliver-research")
        self.assertIn("REFUSED", msg)
        self.assertIn("bifrost-research", msg)

    def test_research_allowed_when_what_names_the_repo(self) -> None:
        window = {"who": "ada@host", "what": "bifrost-research"}
        self.assertEqual(wd.decide(window, "bifrost-deliver-research"), "")
        self.assertEqual(wd.decide(window, "bifrost-build-research-dagster"), "")

    def test_research_refused_when_trade_holds_the_window(self) -> None:
        window = {"who": "ada@host", "what": "bifrost-trade-core,bifrost-trade-api"}
        msg = wd.decide(window, "bifrost-deliver-research")
        self.assertIn("someone else", msg)

    def test_trade_allowed_when_what_names_a_trade_repo(self) -> None:
        window = {"who": "ada@host", "what": ",".join(sorted(wd.TRADE_REPOS))}
        self.assertEqual(wd.decide(window, "bifrost-deliver-stg"), "")
        self.assertEqual(wd.decide(window, "bifrost-deliver-prod"), "")

    def test_trade_refused_while_research_holds_the_window(self) -> None:
        window = {"who": "ada@host", "what": "bifrost-research"}
        self.assertIn("someone else", wd.decide(window, "bifrost-deliver-stg"))

    def test_trade_allowed_when_no_window_is_open(self) -> None:
        self.assertEqual(wd.decide(None, "bifrost-deliver-stg"), "")

    def test_plugin_builds_are_guarded(self) -> None:
        self.assertIn("REFUSED", wd.decide(None, "bifrost-build-market-data"))
        self.assertIn("REFUSED", wd.decide(None, "bifrost-build-flex-query"))
        self.assertIn("REFUSED", wd.decide(None, "bifrost-build-ib-gateway"))
        held = {"who": "ada@host", "what": "bifrost-platform-plugin"}
        self.assertEqual(wd.decide(held, "bifrost-build-ib-gateway"), "")
        self.assertIn("someone else", wd.decide(held, "bifrost-build-market-data"))

    def test_unknown_pipeline_refused_while_a_window_is_open(self) -> None:
        window = {"who": "ada@host", "what": "bifrost-research"}
        self.assertIn("REFUSED", wd.decide(window, "bifrost-smoke"))

    def test_api_requires_the_holders_who(self) -> None:
        window = {"who": "ada@host", "what": "bifrost-research"}
        self.assertEqual(wd.decide_api(window, "bifrost-deliver-research", "ada@host"), "")
        msg = wd.decide_api(window, "bifrost-deliver-research", "bob@host")
        self.assertIn("someone else", msg)
        self.assertIn("REFUSED", wd.decide_api(window, "bifrost-deliver-research", ""))

    def test_api_allows_trade_when_no_window_is_open(self) -> None:
        self.assertEqual(wd.decide_api(None, "bifrost-deliver-stg", ""), "")

    def test_sha_shape(self) -> None:
        self.assertTrue(wd.is_full_sha(SHA))
        self.assertFalse(wd.is_full_sha("main"))
        self.assertFalse(wd.is_full_sha(SHA.upper()))
        self.assertFalse(wd.is_full_sha(SHA[:-1]))


class CiGateTests(unittest.TestCase):
    def test_succeeded_run_passes(self) -> None:
        runs = [_run("bifrost-trade-api", SHA, "bifrost-ci-python", "True")]
        code, text = ci_gate.gate(runs, [("bifrost-trade-api", SHA)], "")
        self.assertEqual(code, 0, text)

    def test_failed_run_refuses_without_allow_red(self) -> None:
        runs = [_run("bifrost-trade-api", SHA, "bifrost-ci-python", "False")]
        code, text = ci_gate.gate(runs, [("bifrost-trade-api", SHA)], "")
        self.assertEqual(code, 1, text)
        self.assertIn("REFUSED", text)

    def test_allow_red_records_the_reason_and_passes(self) -> None:
        runs = [_run("bifrost-trade-api", SHA, "bifrost-ci-python", "False")]
        code, text = ci_gate.gate(runs, [("bifrost-trade-api", SHA)], "owner accepted the lint-only failure")
        self.assertEqual(code, 0, text)
        self.assertIn("allow-red", text)

    def test_missing_run_is_retryable(self) -> None:
        code, _ = ci_gate.gate([], [("bifrost-trade-core", SHA)], "")
        self.assertEqual(code, 2)

    def test_other_sha_does_not_count(self) -> None:
        runs = [_run("bifrost-trade-core", OTHER, "bifrost-ci-python", "True")]
        code, _ = ci_gate.gate(runs, [("bifrost-trade-core", SHA)], "")
        self.assertEqual(code, 2)

    def test_running_run_is_not_a_success(self) -> None:
        runs = [_run("bifrost-trade-core", SHA, "bifrost-ci-python", None)]
        code, _ = ci_gate.gate(runs, [("bifrost-trade-core", SHA)], "")
        self.assertEqual(code, 2)

    def test_cli_on_a_fixture(self) -> None:
        fixture = Path(__file__).with_name("_ci_fixture.json")
        fixture.write_text(json.dumps({"items": [_run("bifrost-trade-worker", SHA, "bifrost-ci-python", "True")]}))
        try:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("ci_gate.py")),
                 "--runs", str(fixture), f"bifrost-trade-worker={SHA}"],
                check=False, capture_output=True, text=True,
            )
        finally:
            fixture.unlink(missing_ok=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


def _load_check_release_chain():
    path = Path(__file__).resolve().parents[1] / "check-release-chain.py"
    spec = importlib.util.spec_from_file_location("check_release_chain", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GuardedPipelineReleaseWindowTests(unittest.TestCase):
    """TD-263: MUST_HOLD pipelines (incl. flex-query sibling YAML) start with release-window."""

    def test_guarded_pipelines_release_window_first(self) -> None:
        workspace = Path(os.environ.get("BIFROST_WORKSPACE", Path(__file__).resolve().parents[2].parent))
        if not (workspace / "bifrost-platform-plugin-flex-query").is_dir():
            self.skipTest("BIFROST_WORKSPACE must name a checkout with bifrost-platform-plugin-flex-query")
        prev = os.environ.get("BIFROST_WORKSPACE")
        os.environ["BIFROST_WORKSPACE"] = str(workspace)
        try:
            crc = _load_check_release_chain()
            failures: list[str] = []
            crc.failures = failures
            crc.assert_guarded_pipelines_release_window_first()
            self.assertEqual(failures, [])
        finally:
            if prev is None:
                os.environ.pop("BIFROST_WORKSPACE", None)
            else:
                os.environ["BIFROST_WORKSPACE"] = prev


if __name__ == "__main__":
    unittest.main()
