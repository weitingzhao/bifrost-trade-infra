"""W-31 4.6 S7, TD-299: the Tekton janitor's three passes, run offline.

The CronJob's script runs as written with jq; kubectl is a local stand-in that serves
fixtures and records every delete (no cluster, no kubeconfig). Pass 1: terminal
PipelineRuns older than 7 days. Pass 2: pods of finished TaskRuns, Succeeded after 2 days,
Failed after 7. Pass 3: standalone TaskRuns older than 7 days, the newest 5 of each task kept.

    python3 -m unittest scripts/test_pipelinerun_ttl.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "k8s" / "cicd" / "tekton" / "pipelinerun-ttl.yaml"
NOW = 1_800_000_000  # a fixed clock
DAY = 86400
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a = sys.argv[1:]
r = pathlib.Path(os.environ["FIXTURES"])
if a[0] == "get" and a[1] == "pipelinerun":
    print((r / "pr.json").read_text())
elif a[0] == "get" and a[1] == "--raw":
    print((r / "pods.json").read_text())
elif a[0] == "get" and a[1] == "taskrun":
    assert "-l" in a and a[a.index("-l") + 1] == "!tekton.dev/pipelineRun", a
    print((r / "tr.json").read_text())
elif a[0] == "delete":
    names, skip = [], False
    for x in a[2:]:
        if skip:
            skip = False
        elif x == "-n":
            skip = True
        elif not x.startswith("-"):
            names.append(x)
    with (r / "deleted.jsonl").open("a") as f:
        for n in names:
            f.write(json.dumps([a[1], n, "--dry-run=server" in a]) + "\n")
else:
    sys.exit("unexpected kubectl " + " ".join(a))
'''


def iso(epoch: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def script() -> str:
    for doc in yaml.safe_load_all(MANIFEST.read_text()):
        if doc and doc.get("kind") == "CronJob":
            return doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][2]
    raise AssertionError("no CronJob")


def env_defaults() -> dict:
    for doc in yaml.safe_load_all(MANIFEST.read_text()):
        if doc and doc.get("kind") == "CronJob":
            env = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
            return {e["name"]: e["value"] for e in env}
    raise AssertionError("no CronJob")


class Janitor(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="ttl-"))
        (self.dir / "bin").mkdir()
        k = self.dir / "bin" / "kubectl"
        k.write_text(FAKE)
        k.chmod(0o755)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_janitor(self, prs: list, pods: list, trs: list, dry: bool = False) -> list:
        (self.dir / "pr.json").write_text(json.dumps({"items": prs}))
        (self.dir / "pods.json").write_text(json.dumps({"items": pods, "metadata": {}}))
        (self.dir / "tr.json").write_text(json.dumps({"items": trs}))
        env = {**os.environ, **env_defaults(), "PATH": f"{self.dir / 'bin'}:{os.environ['PATH']}",
               "FIXTURES": str(self.dir), "SKIP_APK": "1", "NOW_EPOCH": str(NOW)}
        env.pop("KUBECONFIG", None)
        if dry:
            env["DRY_RUN"] = "1"
        out = subprocess.run(["sh", "-c", script()], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.out = out.stdout
        f = self.dir / "deleted.jsonl"
        return [tuple(json.loads(x)) for x in f.read_text().splitlines()] if f.exists() else []

    @staticmethod
    def pr(name: str, age_days: float | None) -> dict:
        status = {} if age_days is None else {"completionTime": iso(int(NOW - age_days * DAY))}
        return {"metadata": {"name": name}, "status": status}

    @staticmethod
    def pod(name: str, phase: str, age_days: float) -> dict:
        return {"metadata": {"name": name, "ownerReferences": [{"kind": "TaskRun"}]},
                "status": {"phase": phase, "containerStatuses": [
                    {"state": {"terminated": {"finishedAt": iso(int(NOW - age_days * DAY))}}}]}}

    @staticmethod
    def tr(name: str, task: str, age_days: float | None) -> dict:
        status = {} if age_days is None else {"completionTime": iso(int(NOW - age_days * DAY)) .replace("Z", ".123Z")}
        return {"metadata": {"name": name, "labels": {"tekton.dev/task": task}}, "spec": {"taskRef": {"name": task}},
                "status": status}

    def test_pipelineruns(self) -> None:
        deleted = self.run_janitor([self.pr("old", 8), self.pr("young", 6), self.pr("running", None),
                                    self.pr("bad", None) | {"status": {"completionTime": "not-a-time"}}], [], [])
        self.assertEqual(deleted, [("pipelinerun", "old", False)])

    def test_pods_keep_failures_a_week(self) -> None:
        deleted = self.run_janitor([], [self.pod("ok-3d", "Succeeded", 3), self.pod("ok-1d", "Succeeded", 1),
                                        self.pod("bad-3d", "Failed", 3), self.pod("bad-8d", "Failed", 8),
                                        self.pod("running", "Running", 9)], [])
        self.assertEqual(sorted(n for _, n, _ in deleted), ["bad-8d", "ok-3d"])

    def test_standalone_taskruns_keep_the_newest_five_per_task(self) -> None:
        trs = [self.tr(f"sync-{i}", "bifrost-github-sync", 8 + i) for i in range(8)]  # all older than 7 days
        trs += [self.tr("mirror-young", "bifrost-gitea-mirror-sync", 1), self.tr("mirror-old", "bifrost-gitea-mirror-sync", 30),
                self.tr("mirror-running", "bifrost-gitea-mirror-sync", None)]
        deleted = self.run_janitor([], [], trs)
        # github-sync: newest five (8..12 days) kept, the three oldest go; mirror-sync has two finished: both kept
        self.assertEqual(sorted(n for k, n, _ in deleted if k == "taskrun"), ["sync-5", "sync-6", "sync-7"])
        self.assertIn("standalone-taskrun-ttl done deleted=3 of=11 keepPerTask=5", self.out)

    def test_dry_run_sends_every_delete_as_dry_run(self) -> None:
        deleted = self.run_janitor([self.pr("old", 8)], [self.pod("ok-3d", "Succeeded", 3)],
                                   [self.tr(f"s-{i}", "t", 9 + i) for i in range(6)], dry=True)
        self.assertEqual(len(deleted), 3)
        self.assertTrue(all(dry for _, _, dry in deleted))


if __name__ == "__main__":
    unittest.main()
