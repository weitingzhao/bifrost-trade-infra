"""W-31 4.6 S7, TD-299: the Tekton janitor's three passes, run offline.

The CronJob's script runs as written with jq; kubectl is a local stand-in that serves
fixtures and records every delete (no cluster, no kubeconfig). Pass 1: terminal
PipelineRuns older than 2 days (7 until 2026-11-17). Pass 2: pods of finished TaskRuns, Succeeded after 1 hour,
Failed after 1 day. Pass 3: standalone TaskRuns older than 2 days, the newest 5 of each task kept.
Pass 4 (TD-492): workspace PVCs of PipelineRuns finished more than 1 day ago; the runs stay.

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
# The CronJob lives in its own file since 2026-11-19 (it goes by apply_manifest; its
# identity does not). The checks read both as one manifest.
CRONJOB = ROOT / "k8s" / "cicd" / "tekton" / "cronjob-pipelinerun-ttl.yaml"


def manifest_text() -> str:
    return MANIFEST.read_text() + "\n---\n" + CRONJOB.read_text()


NOW = 1_800_000_000  # a fixed clock
DAY = 86400
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a = sys.argv[1:]
r = pathlib.Path(os.environ["FIXTURES"])
if a[0] == "get" and a[1] == "pipelinerun":
    # 2026-11-15: this one call, every run decoded at once, is what was OOMKilled.
    sys.exit("pass 1 must page through the API, not `kubectl get pipelinerun`")
elif a[0] == "get" and a[1] == "pvc":
    print((r / "pvc.json").read_text())
elif a[0] == "get" and a[1] == "taskrun":
    sys.exit("pass 3 must page through the API, not `kubectl get taskrun`")
elif a[0] == "get":
    # 2026-11-17: an Owner's execution card cannot carry kubectl's raw-path flag; the lists go through curl.
    sys.exit("the paged lists go through api_get (curl), not kubectl get: " + " ".join(a))
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
# The API server's stand-in: curl as api_get calls it (the URL is the last argument).
FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a = sys.argv[1:]
r = pathlib.Path(os.environ["FIXTURES"])
url = a[-1]
assert url.startswith("https://api.test:6443/"), a
assert "--cacert" in a and any(x == "Authorization: Bearer fixture-token" for x in a), a
if "/pipelineruns?" in url:
    from urllib.parse import urlparse, parse_qs, unquote
    q = parse_qs(urlparse(url).query)
    items = json.loads((r / "pr.json").read_text())["items"]
    limit, start = int(q["limit"][0]), int(unquote(q.get("continue", ["0"])[0]).split("/")[-1])
    page = items[start:start + limit]
    more = start + limit < len(items)
    with (r / "pr.pages").open("a") as f:
        f.write("%d\n" % len(page))
    # A continue token that needs escaping, as the API server's does.
    print(json.dumps({"items": page, "metadata": {"continue": "tok+en/%d" % (start + limit)} if more else {}}))
elif "/taskruns?" in url:
    assert "labelSelector=%21tekton.dev%2FpipelineRun" in url, a
    print((r / "tr.json").read_text())
elif "/pods?" in url:
    print((r / "pods.json").read_text())
else:
    sys.exit("unexpected GET " + url)
'''


def iso(epoch: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def script() -> str:
    for doc in yaml.safe_load_all(manifest_text()):
        if doc and doc.get("kind") == "CronJob":
            return doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"][2]
    raise AssertionError("no CronJob")


def env_defaults() -> dict:
    for doc in yaml.safe_load_all(manifest_text()):
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
        c = self.dir / "bin" / "curl"
        c.write_text(FAKE_CURL)
        c.chmod(0o755)
        (self.dir / "sa").mkdir()
        (self.dir / "sa" / "token").write_text("fixture-token")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_janitor(self, prs: list, pods: list, trs: list, dry: bool = False, pvcs: list | None = None) -> list:
        (self.dir / "pr.json").write_text(json.dumps({"items": prs}))
        (self.dir / "pvc.json").write_text(json.dumps({"items": pvcs or []}))
        (self.dir / "pods.json").write_text(json.dumps({"items": pods, "metadata": {}}))
        (self.dir / "tr.json").write_text(json.dumps({"items": trs, "metadata": {}}))
        env = {**os.environ, **env_defaults(), "PATH": f"{self.dir / 'bin'}:{os.environ['PATH']}",
               "FIXTURES": str(self.dir), "SKIP_APK": "1", "NOW_EPOCH": str(NOW),
               "SA_DIR": str(self.dir / "sa"), "KUBERNETES_SERVICE_HOST": "api.test", "KUBERNETES_SERVICE_PORT": "6443"}
        env.pop("KUBECONFIG", None)
        if dry:
            env["DRY_RUN"] = "1"
        out = subprocess.run(["sh", "-c", script()], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.out = out.stdout
        f = self.dir / "deleted.jsonl"
        return [tuple(json.loads(x)) for x in f.read_text().splitlines()] if f.exists() else []

    @staticmethod
    def pr(name: str, age_days: float | None, ok: bool = False) -> dict:
        status = {} if age_days is None else {"completionTime": iso(int(NOW - age_days * DAY)),
                                              "conditions": [{"type": "Succeeded", "status": "True" if ok else "False"}]}
        return {"metadata": {"name": name, "uid": "uid-" + name}, "status": status}

    @staticmethod
    def pvc(name: str, owner: str | None, kind: str = "PipelineRun") -> dict:
        refs = [] if owner is None else [{"kind": kind, "name": owner, "uid": "uid-" + owner}]
        return {"metadata": {"name": name, "ownerReferences": refs}}

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
        # three-days: 2026-11-17, retention went from 7 days to 2 (a run of three days was kept
        # until then; 15,000 TaskRuns without a pod stalled Tekton's controller that night).
        deleted = self.run_janitor([self.pr("old", 8), self.pr("three-days", 3), self.pr("young", 0.5), self.pr("running", None),
                                    self.pr("bad", None) | {"status": {"completionTime": "not-a-time"}}], [], [])
        self.assertEqual(deleted, [("pipelinerun", "old", False), ("pipelinerun", "three-days", False)])

    def test_pods_keep_failures_a_day(self) -> None:
        deleted = self.run_janitor([], [self.pod("ok-2h", "Succeeded", 2 / 24), self.pod("ok-30m", "Succeeded", 0.5 / 24),
                                        self.pod("bad-12h", "Failed", 0.5), self.pod("bad-2d", "Failed", 2),
                                        self.pod("running", "Running", 9)], [])
        self.assertEqual(sorted(n for _, n, _ in deleted), ["bad-2d", "ok-2h"])

    def test_a_pod_whose_steps_passed_is_not_kept_as_a_failure(self) -> None:
        # 2026-11-19: a sidecar stopped at the end of the steps leaves the pod Failed, and
        # 1,460 such pods of passing runs were kept a day. Positive control: a failed step
        # keeps its pod the day, and so does a Failed pod that lists no steps.
        def pod(name, codes):
            return {"metadata": {"name": name, "ownerReferences": [{"kind": "TaskRun"}]},
                    "status": {"phase": "Failed", "containerStatuses": [
                        {"name": n, "state": {"terminated": {"finishedAt": iso(int(NOW - 2 / 24 * DAY)), "exitCode": c}}}
                        for n, c in codes]}}
        deleted = self.run_janitor([], [pod("sidecar-only", [("step-go-test", 0), ("sidecar-postgres", 137)]),
                                        pod("step-failed", [("step-go-test", 1), ("sidecar-postgres", 137)]),
                                        self.pod("no-steps", "Failed", 2 / 24)], [])
        self.assertEqual(sorted(n for _, n, _ in deleted), ["sidecar-only"])

    def test_standalone_taskruns_keep_the_newest_five_per_task(self) -> None:
        trs = [self.tr(f"sync-{i}", "bifrost-github-sync", 8 + i) for i in range(8)]  # all older than 2 days
        trs += [self.tr("mirror-young", "bifrost-gitea-mirror-sync", 1), self.tr("mirror-old", "bifrost-gitea-mirror-sync", 30),
                self.tr("mirror-running", "bifrost-gitea-mirror-sync", None)]
        deleted = self.run_janitor([], [], trs)
        # github-sync: newest five (8..12 days) kept, the three oldest go; mirror-sync has two finished: both kept
        self.assertEqual(sorted(n for k, n, _ in deleted if k == "taskrun"), ["sync-5", "sync-6", "sync-7"])
        self.assertIn("standalone-taskrun-ttl done deleted=3 of=11 keepPerTask=5", self.out)

    def test_workspaces_go_after_a_day_and_the_runs_stay(self) -> None:
        prs = [self.pr("done-36h", 1.5), self.pr("done-6h", 0.25), self.pr("running", None), self.pr("old", 8)]
        pvcs = [self.pvc("ws-done-36h", "done-36h"), self.pvc("ws-done-6h", "done-6h"), self.pvc("ws-running", "running"),
                self.pvc("ws-old", "old"), self.pvc("gitea-data", None), self.pvc("ws-taskrun", "done-36h", kind="TaskRun"),
                self.pvc("ws-stranger", "gone")]
        deleted = self.run_janitor(prs, [], [], pvcs=pvcs)
        self.assertEqual(sorted(deleted), [("pipelinerun", "done-36h", False), ("pipelinerun", "old", False),
                                           ("pvc", "ws-done-36h", False), ("pvc", "ws-old", False)])
        self.assertIn("workspace-pvc-ttl done deleted=2 of=7 maxAge=86400s succeededMaxAge=10800s", self.out)

    def test_a_succeeded_run_gives_up_its_workspace_after_three_hours(self) -> None:
        # 2026-11-19: 653 workspaces, 632 of them new in a day, and the root disks of four
        # nodes growing 32-47 GB a day. A failed run keeps its workspace a day, to be looked
        # at. Positive control: the same age failed, and a success younger than the limit.
        prs = [self.pr("ok-4h", 4 / 24, ok=True), self.pr("ok-2h", 2 / 24, ok=True), self.pr("bad-4h", 4 / 24)]
        pvcs = [self.pvc("ws-ok-4h", "ok-4h"), self.pvc("ws-ok-2h", "ok-2h"), self.pvc("ws-bad-4h", "bad-4h")]
        self.assertEqual(self.run_janitor(prs, [], [], pvcs=pvcs), [("pvc", "ws-ok-4h", False)])

    def test_retention_is_the_registered_one(self) -> None:
        # 2026-11-19: run records 1 day (2 until then, 7 until 11-17). The pods go after an hour, and the
        # 15,000 TaskRuns left without one stalled Tekton's controller for 23 minutes that night.
        # TD-492: their local-path workspaces 1 day (ubt-k3s-07's disk),
        # finished pods 1 hour, failed pods 1 day (cards #331/#334, 2026-11-07).
        env = env_defaults()
        self.assertEqual({k: env[k] for k in ("MAX_AGE_SECONDS", "WORKSPACE_MAX_AGE_SECONDS",
                                              "WORKSPACE_SUCCEEDED_MAX_AGE_SECONDS", "POD_MAX_AGE_SECONDS",
                                              "FAILED_POD_MAX_AGE_SECONDS", "KEEP_PER_TASK")},
                         {"MAX_AGE_SECONDS": str(DAY), "WORKSPACE_MAX_AGE_SECONDS": str(DAY),
                          "WORKSPACE_SUCCEEDED_MAX_AGE_SECONDS": str(3 * 3600),
                          "POD_MAX_AGE_SECONDS": "3600", "FAILED_POD_MAX_AGE_SECONDS": str(DAY), "KEEP_PER_TASK": "5"})
        self.assertLessEqual(int(env["WORKSPACE_MAX_AGE_SECONDS"]), int(env["MAX_AGE_SECONDS"]))
        self.assertGreaterEqual(int(env["WORKSPACE_MAX_AGE_SECONDS"]), int(env["FAILED_POD_MAX_AGE_SECONDS"]))
        role = next(d for d in yaml.safe_load_all(manifest_text()) if d and d.get("kind") == "Role")
        self.assertIn({"apiGroups": [""], "resources": ["persistentvolumeclaims"], "verbs": ["list", "delete"]},
                      role["rules"])

    def test_dry_run_sends_every_delete_as_dry_run(self) -> None:
        deleted = self.run_janitor([self.pr("old", 8), self.pr("done-36h", 1.5)], [self.pod("ok-3d", "Succeeded", 3)],
                                   [self.tr(f"s-{i}", "t", 9 + i) for i in range(6)], dry=True,
                                   pvcs=[self.pvc("ws", "done-36h")])
        # old and done-36h (one day of run records since 2026-11-19), ok-3d, s-0, ws
        self.assertEqual(len(deleted), 5)
        self.assertTrue(all(dry for _, _, dry in deleted))


    def test_pipelineruns_are_read_a_page_at_a_time(self) -> None:
        """Origin: 2026-11-15 04:21Z. Pass 1 read every PipelineRun in one `kubectl get -o json`
        (53 MB; kubectl peaked near 563 MB under a 256Mi limit) and the job was OOMKilled every
        hour for 43 hours. No pass ran: finished pods reached 5,900, workspaces 717, and their
        series took PROD's Prometheus down on 2026-11-16. With 250 runs the script asks for
        pages of PR_PAGE and never for the whole list (the stand-in exits on that call), and
        passes 1 and 4 see every run, the ones on the last page too."""
        prs = [self.pr("old-%03d" % i, 9) for i in range(120)] + [self.pr("fresh-%03d" % i, 0.1) for i in range(129)]
        prs.append(self.pr("day-old-last", 0.5, ok=True))  # on the last page: its workspace goes, the run stays
        pvcs = [self.pvc("pvc-day-old-last", "day-old-last"), self.pvc("pvc-fresh", "fresh-000")]
        deleted = self.run_janitor(prs, [], [], pvcs=pvcs)
        pages = [int(x) for x in (self.dir / "pr.pages").read_text().split()]
        self.assertEqual(pages, [100, 100, 50])
        self.assertEqual(sorted(n for k, n, _ in deleted if k == "pipelinerun"), sorted("old-%03d" % i for i in range(120)))
        self.assertEqual([n for k, n, _ in deleted if k == "pvc"], ["pvc-day-old-last"])
        self.assertIn("pipelinerun-ttl done deleted=120 kept=130", self.out)

    def test_the_whole_list_in_one_call_is_refused_by_the_stand_in(self) -> None:
        """The control of the test above: the old first line of pass 1 fails here."""
        (self.dir / "pr.json").write_text(json.dumps({"items": []}))
        env = {**os.environ, "PATH": f"{self.dir / 'bin'}:{os.environ['PATH']}", "FIXTURES": str(self.dir)}
        out = subprocess.run(["sh", "-c", 'kubectl get pipelinerun -n cicd -o json'], env=env, capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("must page", out.stderr)


class CardCommand(unittest.TestCase):
    def test_the_cronjob_can_be_carried_by_an_owner_execution_card(self) -> None:
        """Origin: 2026-11-17 09:15 CST. The card that applies this CronJob was refused when it
        was made (HTTP 400): the platform's check of an execution card's command
        (bifrost-platform api/internal/approvals/createcheck.go) refuses kubectl's raw-path flag
        and any dry-run flag whose value is not exactly `server`, wherever they stand in the
        text, and the janitor's own script had both (`kubectl get` with the flag for its pages,
        and the dry-run flag inside a ${VAR:+...} expansion). Loosening that check is the
        Owner's to decide and he declined (#587), so the manifest stays free of both. The three
        patterns are that file's, copied; positive controls below."""
        import re
        raw = re.compile(r"--raw(\s|=|$)", re.M)
        dry = re.compile(r"""--dry-run(=[^\s'"]*)?""")
        conn = re.compile(r"--(kubeconfig|server|token|certificate-authority|client-key|client-certificate)(\s|=|$)", re.M)

        def problems(text: str) -> list:
            out = ["raw"] if raw.search(text) else []
            out += ["dry-run " + m.group(0) for m in dry.finditer(text) if m.group(0) != "--dry-run=server"]
            out += ["connection"] if conn.search(text) else []
            out += [w for w in ("DROP", "TRUNCATE", "DELETE FROM") if w in text.upper()]
            return out

        doc = next(d for d in manifest_text().split("\n---\n") if "\nkind: CronJob\n" in d)
        self.assertEqual(problems(doc), [])
        self.assertEqual(problems('kubectl get --raw "${url}"'), ["raw"])
        self.assertEqual(problems('DRY="${DRY_RUN:+--dry-run=server}"'), ["dry-run --dry-run=server}"])
        self.assertEqual(problems("deletes sent with --dry-run=server."), ["dry-run --dry-run=server."])


if __name__ == "__main__":
    unittest.main()
