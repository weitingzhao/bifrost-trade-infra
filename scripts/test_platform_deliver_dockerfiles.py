"""TD-448: platform deliveries must build from the run's cloned Dockerfiles.

Run with `make check-platform-deliver-dockerfiles`. TD448_STG_PIPELINE can
point at a historical manifest to prove the guard rejects the old pipeline.
All checks are offline; shell probes only copy files in temporary directories.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEKTON = ROOT / "k8s/cicd/tekton"
STG = Path(os.environ.get("TD448_STG_PIPELINE", TEKTON / "pipeline-deliver-platform.yaml"))
PROD = TEKTON / "pipeline-deliver-platform-prod.yaml"
KINDS = ("api", "console")


def pipeline_tasks(path):
    doc = yaml.safe_load(path.read_text())
    return {task["name"]: task for task in doc["spec"]["tasks"]}


def configmap_violations(value):
    """Inspect inline specs, projected volumes and referenced Task definitions."""
    violations = []
    if isinstance(value, dict):
        cm = value.get("configMap", {})
        if cm.get("name", "").endswith("-dockerfile"):
            violations.append(cm["name"])
        # Also catch ConfigMaps renamed while still projecting a Dockerfile.
        for item in cm.get("items", []):
            if "Dockerfile" in item.get("key", "") or "Dockerfile" in item.get("path", ""):
                violations.append(str(item))
        for child in value.values():
            violations.extend(configmap_violations(child))
    elif isinstance(value, list):
        for child in value:
            violations.extend(configmap_violations(child))
    elif isinstance(value, str) and re.search(r"\bcp\s+['\"]?/cm/Dockerfile", value):
        violations.append(value)
    return violations


class PlatformDockerfiles(unittest.TestCase):
    def test_no_configmap_dockerfiles_in_either_pipeline_or_referenced_tasks(self):
        task_specs = {}
        for path in TEKTON.glob("*.yaml"):
            for doc in yaml.safe_load_all(path.read_text()):
                if isinstance(doc, dict) and doc.get("kind") == "Task":
                    task_specs[doc["metadata"]["name"]] = doc["spec"]
        for path in (STG, PROD):
            with self.subTest(pipeline=path.name):
                self.assertEqual(configmap_violations(yaml.safe_load(path.read_text())), [])
                for task in pipeline_tasks(path).values():
                    if "taskRef" in task:
                        ref = task["taskRef"]["name"]
                        self.assertIn(ref, task_specs)
                        self.assertEqual(configmap_violations(task_specs[ref]), [], ref)

    def test_infra_clone_uses_its_own_ref_param_and_shared_workspace(self):
        tasks = pipeline_tasks(STG)
        self.assertIn("clone-infra", tasks)
        clone = tasks["clone-infra"]
        self.assertEqual(clone["taskRef"], {"name": "bifrost-git-clone-gitea"})
        self.assertEqual(clone["runAfter"], ["mirror-sync"])
        self.assertEqual({p["name"]: p["value"] for p in clone["params"]}, {
            "url": "$(params.giteaBase)/bifrost-trade-infra.git",
            "revision": "$(params.infraRevision)", "subdir": "bifrost-trade-infra",
        })
        params = {p["name"]: p.get("default") for p in yaml.safe_load(open(STG))["spec"]["params"]}
        self.assertEqual(params.get("infraRevision"), "main")
        self.assertEqual(clone["workspaces"], [{"name": "output", "workspace": "build-context"}])
        mirrors = {p["name"]: p["value"] for p in tasks["mirror-sync"]["params"]}
        self.assertIn("bifrost-trade-infra", mirrors["mirrorRepos"].split())

    def test_stage_sources_are_in_the_clone_and_builds_wait(self):
        tasks = pipeline_tasks(STG)
        for kind in KINDS:
            with self.subTest(kind=kind):
                stage_name = f"stage-{kind}-dockerfile"
                stage = tasks[stage_name]
                self.assertIn("clone-infra", stage["runAfter"])
                self.assertIn("clone-platform", stage["runAfter"])
                if kind == "console":
                    self.assertIn("clone-ui", stage["runAfter"])
                self.assertEqual(stage["workspaces"], [{"name": "source", "workspace": "build-context"}])
                script = stage["taskSpec"]["steps"][0]["script"]
                filename = f"Dockerfile.platform-{kind}-stg"
                self.assertIn(
                    f'cp "$(workspaces.source.path)/bifrost-trade-infra/k8s/cicd/docker/{filename}" '
                    f'"$(workspaces.source.path)/{filename}"', script,
                )
                build = tasks[f"build-platform-{kind}"]
                self.assertIn(stage_name, build["runAfter"])
                self.assertEqual(build["workspaces"], stage["workspaces"])

    def test_stage_copies_and_logs_changed_clone_bytes(self):
        for kind in KINDS:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="td448 workspace ") as tmp:
                root = Path(tmp)
                filename = f"Dockerfile.platform-{kind}-stg"
                source = root / "bifrost-trade-infra/k8s/cicd/docker" / filename
                source.parent.mkdir(parents=True)
                content = f"# TD-448 changed {kind} Dockerfile\nFROM scratch\n"
                source.write_text(content)
                script = pipeline_tasks(STG)[f"stage-{kind}-dockerfile"]["taskSpec"]["steps"][0]["script"]
                script = script.replace("$(workspaces.source.path)", tmp)
                result = subprocess.run(["sh", "-eu"], input=script, text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((root / filename).read_text(), content)
                self.assertIn(content, result.stdout)
                # Missing clone input must fail even if an older staged file exists.
                source.unlink()
                result = subprocess.run(["sh", "-eu"], input=script, text=True, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)

    def test_prod_promotes_stg_digests_without_building(self):
        tasks = pipeline_tasks(PROD)
        self.assertFalse(any(name.startswith(("build-", "stage-")) for name in tasks))
        self.assertFalse(any("kaniko" in task.get("taskRef", {}).get("name", "") for task in tasks.values()))
        promote = tasks["promote-images"]
        self.assertEqual(promote["taskRef"], {"name": "bifrost-promote-platform-images"})
        params = {p["name"]: p["value"] for p in promote["params"]}
        for kind in KINDS:
            self.assertEqual(params[f"{kind}Digest"], f"$(tasks.check-source.results.{kind}-digest)")


if __name__ == "__main__":
    unittest.main()
