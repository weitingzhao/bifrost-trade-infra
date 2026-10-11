"""Domination ratchet for the freeze check. Fixtures only; no cluster."""

from __future__ import annotations

import sys
import unittest
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
            inline("preflight-stg"),
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
        quiet = pipeline("demo", [freeze()], [inline("pin-check")])
        self.assertEqual(fc.violations_for(quiet), [])

    def test_a_freeze_check_with_when_dominates_nothing(self) -> None:
        doc = pipeline("demo", [
            freeze(when=[{"input": "yes", "operator": "in", "values": ["yes"]}]),
            inline("push", ["freeze-check"]),
        ])
        self.assertEqual(fc.violations_for(doc), ["demo: push is not dominated by the freeze check"])

    def test_an_unknown_task_name_counts_as_side_effecting(self) -> None:
        effects = fc.load_effects()
        self.assertNotIn("custom-step", effects["read_only"])
        self.assertNotIn("custom-step", effects["side_effect"])
        doc = pipeline("demo", [freeze(), inline("custom-step")])
        self.assertEqual(fc.violations_for(doc), ["demo: custom-step is not dominated by the freeze check"])
        self.assertEqual(fc.violations_for(pipeline("demo", [inline("pin-check")])), [])

    def test_inline_taskspec_uses_the_pipeline_task_name(self) -> None:
        doc = pipeline("demo", [freeze(), inline("kaniko", ["freeze-check"])])
        self.assertEqual(fc.violations_for(doc), [])
        self.assertEqual(fc.effect_identity(inline("kaniko")), "kaniko")

    def test_effects_lists_are_disjoint_and_apply_is_the_only_exception(self) -> None:
        effects = fc.load_effects()
        self.assertEqual(set(effects["read_only"]) & set(effects["side_effect"]), set())
        self.assertEqual(list(effects["not_this_slice"]), ["bifrost-apply-manifest"])
        apply = next(doc for _path, doc in fc.iter_pipelines(TEKTON)
                     if doc["metadata"]["name"] == "bifrost-apply-manifest")
        self.assertTrue(any(fc.is_side_effect(task, effects) for task in apply["spec"]["tasks"]))
        self.assertEqual(fc.violations_for(apply), [])
        bare = dict(effects)
        bare["not_this_slice"] = {}
        self.assertIn(
            "bifrost-apply-manifest: run is not dominated by the freeze check",
            fc.violations_for(apply, bare),
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
        self.assertEqual(fc.violations_for(doc), [])
        for push in ("build-platform-api", "build-platform-console"):
            self.assertFalse(fc._path_misses_freeze(tasks, push, {"freeze-check"}))


if __name__ == "__main__":
    unittest.main()
