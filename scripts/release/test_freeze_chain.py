"""Domination ratchet for the freeze check. Fixtures only; no cluster."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import freeze_chain as fc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "freeze-unmodified"

ELEVEN = (
    "bifrost-deliver-stg",
    "bifrost-deliver-prod",
    "bifrost-deliver-platform",
    "bifrost-deliver-platform-prod",
    "bifrost-build-stg",
    "bifrost-build-frontend-stg",
    "bifrost-build-research-pine",
    "bifrost-deliver-research",
    "bifrost-build-research-dagster",
    "bifrost-build-ib-gateway",
    "bifrost-build-market-data",
)

SEVEN = (
    "bifrost-deliver-stg",
    "bifrost-deliver-prod",
    "bifrost-deliver-platform",
    "bifrost-deliver-platform-prod",
    "bifrost-build-stg",
    "bifrost-build-frontend-stg",
    "bifrost-build-research-pine",
)


def pipeline(name: str, tasks: list[dict], finally_tasks: list[dict] | None = None) -> dict:
    spec: dict = {"tasks": tasks}
    if finally_tasks is not None:
        spec["finally"] = finally_tasks
    return {"apiVersion": "tekton.dev/v1", "kind": "Pipeline", "metadata": {"name": name}, "spec": spec}


def freeze(**extra: object) -> dict:
    task: dict = {"name": "freeze-check", "taskRef": {"name": "bifrost-release-freeze-check"}}
    task.update(extra)
    return task


def inline(name: str, run_after: list[str] | None = None) -> dict:
    task: dict = {"name": name, "taskSpec": {"steps": [{"name": "run", "image": "alpine:3.20"}]}}
    if run_after:
        task["runAfter"] = run_after
    return task


def ref(name: str, task_ref: str, run_after: list[str] | None = None) -> dict:
    task: dict = {"name": name, "taskRef": {"name": task_ref}}
    if run_after:
        task["runAfter"] = run_after
    return task


def real(name: str) -> dict:
    path = TEKTON / f"pipeline-{name.removeprefix('bifrost-')}.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["metadata"]["name"] == name
    return doc


class DominationTests(unittest.TestCase):
    def test_a_push_after_the_check_passes(self) -> None:
        doc = pipeline("demo", [freeze(), inline("push", ["freeze-check"])])
        self.assertEqual(fc.violations_for(doc), [])

    def test_a_parallel_root_that_reaches_the_push_fails(self) -> None:
        doc = pipeline("demo", [
            freeze(),
            ref("preflight-stg", "bifrost-release-window"),
            inline("push", ["preflight-stg"]),
        ])
        self.assertEqual(fc.violations_for(doc), ["demo: push is not dominated by the freeze check"])

    def test_a_finally_task_that_pushes_fails(self) -> None:
        doc = pipeline(
            "demo",
            [freeze(), inline("push", ["freeze-check"])],
            [inline("push-anyway")],
        )
        self.assertEqual(
            fc.violations_for(doc),
            ["demo: push-anyway is not dominated by the freeze check"],
        )
        quiet = pipeline("demo", [freeze()], [ref("pin-check", "bifrost-validate-git-sha")])
        self.assertEqual(fc.violations_for(quiet), [])

    def test_a_freeze_check_with_when_dominates_nothing(self) -> None:
        doc = pipeline("demo", [
            freeze(when=[{"input": "yes", "operator": "in", "values": ["yes"]}]),
            inline("push", ["freeze-check"]),
        ])
        self.assertEqual(
            fc.violations_for(doc),
            [
                "demo: freeze-check is not a valid freeze check (when)",
                "demo: push is not dominated by the freeze check",
            ],
        )

    def test_an_unknown_task_name_counts_as_side_effecting(self) -> None:
        effects = fc.load_effects()
        self.assertNotIn("custom-step", effects["read_only_task_ref"])
        self.assertNotIn("custom-step", effects["side_effect"])
        doc = pipeline("demo", [freeze(), inline("custom-step")])
        self.assertEqual(fc.violations_for(doc), ["demo: custom-step is not dominated by the freeze check"])
        self.assertEqual(fc.violations_for(pipeline("demo", [ref("echo", "bifrost-smoke-echo")])), [])

    def test_platform_digest_rollout_explicitly_side_effecting(self) -> None:
        effects = fc.load_effects()
        name = "bifrost-rollout-verify-platform"
        self.assertIn(name, effects["side_effect"])
        task = ref("rollout", name)
        self.assertTrue(fc.is_side_effect(task, effects, "demo"))
        self.assertEqual(fc.violations_for(pipeline("demo", [freeze(), task])),
                         ["demo: rollout is not dominated by the freeze check"])
        task["runAfter"] = ["freeze-check"]
        self.assertEqual(fc.violations_for(pipeline("demo", [freeze(), task])), [])

    def test_inline_taskspec_uses_the_pipeline_task_name(self) -> None:
        doc = pipeline("demo", [freeze(), inline("kaniko", ["freeze-check"])])
        self.assertEqual(fc.violations_for(doc), [])
        self.assertEqual(fc.effect_identity(inline("kaniko")), "kaniko")

    def test_no_pipeline_is_exempt_and_apply_is_dominated(self) -> None:
        effects = fc.load_effects()
        self.assertNotIn("not_this_slice", effects)
        self.assertEqual(set(effects["read_only_task_ref"]) & set(effects["side_effect"]), set())
        apply = next(doc for _path, doc in fc.iter_pipelines(TEKTON)
                     if doc["metadata"]["name"] == "bifrost-apply-manifest")
        run = next(task for task in apply["spec"]["tasks"] if task["name"] == "run")
        self.assertEqual(run["runAfter"], ["freeze-check"])
        self.assertTrue(fc.is_side_effect(run, effects, "bifrost-apply-manifest"))
        self.assertEqual(fc.violations_for(apply), [])
        poisoned = dict(effects)
        poisoned["not_this_slice"] = {"demo": "skip"}
        skipped = pipeline("demo", [inline("push")])
        self.assertEqual(
            fc.violations_for(skipped, poisoned),
            ["demo: push is not dominated by the freeze check"],
        )

    def test_eleven_real_pipelines_pass(self) -> None:
        self.assertEqual(fc.violations_under(TEKTON), [])
        for name in ELEVEN:
            self.assertEqual(fc.violations_for(real(name)), [], name)

    def test_seven_unmodified_pipelines_fail(self) -> None:
        seen = []
        for path in sorted(FIXTURES.glob("pipeline-*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            misses = fc.violations_for(doc)
            self.assertTrue(misses, path.name)
            for line in misses:
                self.assertIn(" is not dominated by the freeze check", line)
            seen.append(doc["metadata"]["name"])
        self.assertEqual(tuple(sorted(seen)), tuple(sorted(SEVEN)))

    def test_prod_chain_one_check_dominates_both_pushes_and_not_rollout_again(self) -> None:
        doc = real("bifrost-deliver-platform-prod")
        tasks = doc["spec"]["tasks"]
        freezes = [task for task in tasks if fc.is_freeze_check(task, fc.load_effects())]
        self.assertEqual([task["name"] for task in freezes], ["freeze-check"])
        self.assertNotIn("when", freezes[0])
        self.assertNotIn("runAfter", freezes[0])
        by_name = {task["name"]: task for task in tasks}
        self.assertEqual(
            by_name["rollout"]["runAfter"],
            ["build-platform-api", "build-platform-console"],
        )
        self.assertNotIn("freeze-check", by_name["rollout"]["runAfter"])
        effects = fc.load_effects()
        self.assertEqual(by_name["rollout"]["taskRef"]["name"], "bifrost-rollout-verify-platform")
        self.assertTrue(fc.is_side_effect(by_name["rollout"], effects, doc["metadata"]["name"]))
        self.assertFalse(fc._path_misses_freeze(tasks, "rollout", {"freeze-check"}))
        self.assertEqual(fc.violations_for(doc), [])
        unguarded = copy.deepcopy(doc)
        unguarded["spec"]["tasks"] = [t for t in unguarded["spec"]["tasks"] if t["name"] != "freeze-check"]
        for task in unguarded["spec"]["tasks"]:
            if "runAfter" in task:
                task["runAfter"] = [n for n in task["runAfter"] if n != "freeze-check"]
        self.assertIn("bifrost-deliver-platform-prod: rollout is not dominated by the freeze check", fc.violations_for(unguarded))
        for push in ("build-platform-api", "build-platform-console"):
            self.assertFalse(fc._path_misses_freeze(tasks, push, {"freeze-check"}))

    def test_on_error_continue_is_not_protection(self) -> None:
        doc = pipeline("demo", [
            freeze(onError="continue"),
            inline("push", ["freeze-check"]),
        ])
        self.assertEqual(
            fc.violations_for(doc),
            [
                "demo: freeze-check is not a valid freeze check (onError: continue)",
                "demo: push is not dominated by the freeze check",
            ],
        )

    def test_retries_are_not_protection_even_without_a_side_effect(self) -> None:
        # A refusal fails the step. A retry can then succeed against a different
        # object, so the first refusal is not the cut.
        alone = pipeline("demo", [freeze(retries=2), ref("echo", "bifrost-smoke-echo", ["freeze-check"])])
        self.assertEqual(
            fc.violations_for(alone),
            ["demo: freeze-check is not a valid freeze check (retries)"],
        )
        followed = pipeline("demo", [freeze(retries=1), inline("push", ["freeze-check"])])
        self.assertIn("demo: push is not dominated by the freeze check", fc.violations_for(followed))

    def test_when_or_finally_without_side_effects_is_a_violation(self) -> None:
        skipped = pipeline("demo", [
            freeze(when=[{"input": "yes", "operator": "in", "values": ["yes"]}]),
            ref("echo", "bifrost-smoke-echo", ["freeze-check"]),
        ])
        self.assertEqual(
            fc.violations_for(skipped),
            ["demo: freeze-check is not a valid freeze check (when)"],
        )
        parked = pipeline("demo", [ref("echo", "bifrost-smoke-echo")], [freeze()])
        self.assertEqual(
            fc.violations_for(parked),
            ["demo: freeze-check is not a valid freeze check (finally)"],
        )

    def test_a_name_or_inline_spec_is_not_the_freeze_task(self) -> None:
        named = inline("bifrost-release-freeze-check")
        named["taskSpec"]["steps"][0]["script"] = "git push\n"
        misses = fc.violations_for(pipeline("demo", [named]))
        self.assertEqual(misses, ["demo: bifrost-release-freeze-check is not dominated by the freeze check"])
        self.assertFalse(any("valid freeze check" in line for line in misses))

    def test_inline_read_only_name_does_not_hide_a_push(self) -> None:
        task = inline("lint-test")
        task["taskSpec"]["steps"][0]["script"] = "git push origin HEAD:main\n"
        self.assertEqual(
            fc.violations_for(pipeline("demo", [task])),
            ["demo: lint-test is not dominated by the freeze check"],
        )
        effects = fc.load_effects()
        effects["read_only_task_ref"] = list(effects["read_only_task_ref"]) + ["lint-test"]
        self.assertTrue(fc.is_side_effect({"name": "lint-test", "taskRef": {"name": "lint-test"}}, effects, "demo"))

    def test_inline_read_only_is_bound_to_the_taskspec_digest(self) -> None:
        spec = {"steps": [{"name": "look", "image": "alpine:3.20", "script": "true\n"}]}
        digest = fc.taskspec_digest(spec)
        effects = fc.load_effects()
        effects["read_only_inline"] = list(effects["read_only_inline"]) + [
            {"pipeline": "demo", "task": "lint-test", "taskspec_sha256": digest},
        ]
        self.assertFalse(fc.is_side_effect({"name": "lint-test", "taskSpec": spec}, effects, "demo"))
        changed = {"steps": [{"name": "look", "image": "alpine:3.20", "script": "true\n# edited\n"}]}
        self.assertNotEqual(fc.taskspec_digest(changed), digest)
        self.assertTrue(fc.is_side_effect({"name": "lint-test", "taskSpec": changed}, effects, "demo"))
        push = {"steps": [{"name": "look", "image": "alpine:3.20", "script": "git push\n"}]}
        writing = dict(effects)
        writing["read_only_inline"] = [
            {"pipeline": "demo", "task": "lint-test", "taskspec_sha256": fc.taskspec_digest(push)},
        ]
        self.assertTrue(fc.is_side_effect({"name": "lint-test", "taskSpec": push}, writing, "demo"))

    def test_side_effect_list_is_consulted(self) -> None:
        task = ref("smoke-echo", "bifrost-smoke-echo")
        effects = fc.load_effects()
        self.assertFalse(fc.is_side_effect(task, effects, "demo"))
        forced = dict(effects)
        forced["side_effect"] = list(effects["side_effect"]) + ["bifrost-smoke-echo"]
        self.assertTrue(fc.is_side_effect(task, forced, "demo"))

    def test_definition_digest_binds_taskref_params_or_inline_taskspec(self) -> None:
        ref = {"name": "kaniko", "taskRef": {"name": "kaniko"}, "params": [{"name": "IMAGE", "value": "a"}]}
        other = {"name": "kaniko", "taskRef": {"name": "kaniko"}, "params": [{"name": "IMAGE", "value": "b"}]}
        self.assertNotEqual(fc.definition_digest(ref), fc.definition_digest(other))
        inline = {
            "name": "kaniko",
            "params": [{"name": "image", "value": "a"}],
            "taskSpec": {"steps": [{"name": "b", "script": "true\n"}]},
        }
        changed_params = dict(inline)
        changed_params["params"] = [{"name": "image", "value": "b"}]
        self.assertEqual(fc.definition_digest(inline), fc.definition_digest(changed_params))

    def test_old_flex_query_shape_reports_kaniko_not_dominated(self) -> None:
        fixture = FIXTURES.parent / "flex-query" / "k8s" / "cicd" / "pipeline-build.yaml"
        repo = "bifrost-platform-plugin-flex-query"
        records = fc.records_in_file(fixture, repo)
        message = (
            "bifrost-platform-plugin-flex-query/bifrost-build-flex-query: "
            "kaniko is not dominated by the freeze check"
        )
        self.assertEqual([item["message"] for item in records], [message])
        document = fc.load_gap_document()
        self.assertEqual(document["gaps"], [])
        self.assertEqual(document["max_age_days"], 30)
        self.assertIn("max_age_reason", document)
        hard, known = fc.split_known_gaps(records, today=date(2026, 10, 11))
        self.assertEqual(known, [])
        self.assertEqual(hard, [message])
        sibling = ROOT.parent / "bifrost-platform-plugin-flex-query" / "k8s" / "cicd" / "pipeline-build.yaml"
        if sibling.is_file():
            self.assertEqual(fc.violations_in_file(sibling, repo), [])

    def test_a_gap_still_matches_only_that_definition_and_age(self) -> None:
        fixture = FIXTURES.parent / "flex-query" / "k8s" / "cicd" / "pipeline-build.yaml"
        repo = "bifrost-platform-plugin-flex-query"
        message = (
            "bifrost-platform-plugin-flex-query/bifrost-build-flex-query: "
            "kaniko is not dominated by the freeze check"
        )
        records = fc.records_in_file(fixture, repo)
        when = date(2026, 10, 11)
        gap = {
            "name": "flex-query-kaniko-not-dominated",
            "date": "2026-10-11",
            "repo": repo,
            "pipeline": "bifrost-build-flex-query",
            "task": "kaniko",
            "spec_sha256": records[0]["digest"],
            "message": message,
        }
        hard, known = fc.split_known_gaps(records, gaps=[gap], max_age_days=30, today=when)
        self.assertEqual(hard, [])
        self.assertEqual(known[0]["message"], message)
        self.assertEqual(known[0]["age_days"], 0)
        hard, known = fc.split_known_gaps(records, gaps=[gap], max_age_days=30, today=date(2026, 11, 10))
        self.assertEqual(hard, [])
        self.assertEqual(known[0]["age_days"], 30)
        hard, known = fc.split_known_gaps(records, gaps=[gap], max_age_days=30, today=date(2026, 11, 11))
        self.assertEqual(known, [])
        self.assertEqual(hard, [message])
        stale = copy.deepcopy(gap)
        stale["date"] = "not-a-date"
        hard, known = fc.split_known_gaps(records, gaps=[stale], max_age_days=30, today=when)
        self.assertEqual(known, [])
        self.assertEqual(hard, [message])
        other = [dict(records[0]), dict(records[0])]
        other[1]["task"] = "other"
        other[1]["message"] = "bifrost-build-flex-query: other is not dominated by the freeze check"
        hard, known = fc.split_known_gaps(other, gaps=[gap], max_age_days=30, today=when)
        self.assertEqual(hard, ["bifrost-build-flex-query: other is not dominated by the freeze check"])
        self.assertEqual(len(known), 1)
        doc = next(
            item for item in yaml.safe_load_all(fixture.read_text(encoding="utf-8")) if item["kind"] == "Pipeline"
        )
        for task in doc["spec"]["tasks"]:
            if task["name"] == "kaniko":
                task["taskSpec"]["steps"] = [
                    {"name": "push", "image": "alpine:3.20", "script": "git push origin HEAD:main\n"},
                ]
        rewritten = fc.records_for_doc(doc, repo)
        self.assertEqual(rewritten[0]["message"], message)
        self.assertNotEqual(rewritten[0]["digest"], records[0]["digest"])
        hard, known = fc.split_known_gaps(rewritten, gaps=[gap], max_age_days=30, today=when)
        self.assertEqual(known, [])
        self.assertEqual(hard, [message])


class CheckerGapTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["FLEX_QUERY_ROOT"] = str(FIXTURES.parent / "flex-query")
        env.pop("BIFROST_WORKSPACE", None)
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-release-chain.py"), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )

    def test_old_flex_query_shape_fails_the_checker(self) -> None:
        message = (
            "bifrost-platform-plugin-flex-query/bifrost-build-flex-query: "
            "kaniko is not dominated by the freeze check"
        )
        refused = self._run()
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn(message, refused.stdout)
        self.assertNotIn("check-release-chain: ok", refused.stdout)
        self.assertNotIn("known gaps:", refused.stdout)
        allowed = self._run("--allow-known-gaps")
        self.assertEqual(allowed.returncode, 1, allowed.stdout + allowed.stderr)
        self.assertIn(message, allowed.stdout)
        self.assertNotIn("check-release-chain: ok", allowed.stdout)
        self.assertNotIn("known gaps:", allowed.stdout)


if __name__ == "__main__":
    unittest.main()
