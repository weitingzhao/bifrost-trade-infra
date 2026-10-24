"""Review 545 F1, 546, 548 R1: the apply-manifest pipeline's own guards, run offline.

The check step's shell runs as written, with the real checker and jq; git, curl, apk and
kubectl are local stand-ins (no cluster, no network, no kubeconfig). A tier C or D apply
needs requireOnMain=true and must render what main's head renders at the same path; the
repository, path, organisation and Gitea address come from the mounted policy. Adapted
from Codex review 548's offline probe.

    python3 -m unittest scripts/test_apply_manifest_pipeline.py
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPLY = ROOT / "k8s" / "cicd" / "tekton" / "apply-manifest"
OLD, HEAD = "1" * 40, "2" * 40
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
name = pathlib.Path(sys.argv[0]).name
a = sys.argv[1:]
r = pathlib.Path(os.environ["PROBE_DIR"])
with (r / "calls.jsonl").open("a") as f:
    f.write(json.dumps([name, *a]) + "\n")
if name != "git":
    assert "GIT_PASSWORD" not in os.environ and "GIT_USERNAME" not in os.environ
    assert not any(k.startswith("GIT_CONFIG_VALUE_") for k in os.environ)
if name == "apk":
    sys.exit(0)
if name == "git":
    if a[0] == "clone":
        assert os.environ["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
        assert "fixture" not in a[-2] and "@" not in a[-2]
        pathlib.Path(a[-1]).mkdir()
    elif a[2] == "rev-parse":
        print(os.environ["PROBE_HEAD"])
    elif a[2] == "merge-base":
        sys.exit(0)
    else:
        sys.exit("unexpected git " + " ".join(a))
elif name == "curl":
    assert sys.stdin.read().startswith('header = "Authorization: Basic ')
    assert "fixture" not in " ".join(a)
    sha = a[-1].rsplit("/", 1)[1].split(".")[0]
    shutil.copyfile(r / (sha + ".tar.gz"), a[a.index("--output") + 1])
elif name == "kubectl":
    if a[0] == "kustomize":
        print((pathlib.Path(a[1]) / "objects.json").read_text())
    elif a[0] == "create":
        print(pathlib.Path(a[a.index("-f") + 1]).read_text())
    elif a[:2] == ["get", "namespace"]:
        print("{}")
    elif a[0] == "get":
        print("")
    elif a[0] == "apply":
        shutil.copyfile(a[a.index("-f") + 1], r / "applied.json")
    elif a[0] == "diff":
        sys.exit(0)
    else:
        sys.exit("unexpected kubectl " + " ".join(a))
else:
    sys.exit("unexpected " + name)
'''


def step_script() -> str:
    pipeline = yaml.safe_load((APPLY / "pipeline.yaml").read_text())
    for task in pipeline["spec"]["tasks"]:
        for step in task.get("taskSpec", {}).get("steps", []):
            if "apply-manifest-check.sh" in step.get("script", ""):
                return step["script"]
    raise AssertionError("no step runs apply-manifest-check.sh")


class ApplyPipelineGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="td432-apply-"))
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        for name in ("apk", "git", "curl", "kubectl"):
            (self.bin / name).write_text(FAKE)
            (self.bin / name).chmod(0o755)
        self.script = step_script()

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_case(self, name: str, *, commit: str = OLD, namespace: bool = False, changed: bool = False,
                 mode: str = "apply", require: str = "true", repo: str = "bifrost-platform-plugin-market-data",
                 path: str = "k8s/base", org: str = "bifrost",
                 base: str = "http://gitea.cicd.svc.cluster.local:3000/bifrost", ns: str = "plugin-market-data",
                 tier_d: bool = False) -> tuple[int, bool, str]:
        r = self.dir / name
        (r / "tmp").mkdir(parents=True)
        docs = [{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"namespace": ns, "name": "probe"},
                 "data": {"value": "same"}}]
        if namespace:
            docs.insert(0, {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns}})
        for sha in (OLD, HEAD):
            items = json.loads(json.dumps(docs))
            if sha == HEAD and changed:
                items[-1]["data"]["value"] = "changed"
            payload = json.dumps({"apiVersion": "v1", "kind": "List", "items": items}).encode()
            with tarfile.open(r / (sha + ".tar.gz"), "w:gz") as t:
                member = tarfile.TarInfo("repo/k8s/base/objects.json")
                member.size = len(payload)
                t.addfile(member, io.BytesIO(payload))
        policy = (APPLY / "actuation-policy.yaml").read_text()
        if tier_d:
            policy = policy.replace("plugin-market-data: C", "plugin-market-data: D")
        (r / "policy.yaml").write_text(policy)
        s = self.script.replace("/tmp/", str(r / "tmp") + "/")
        s = s.replace("/policy/actuation-policy.yaml", str(r / "policy.yaml"))
        s = s.replace("/checks/apply-manifest-check.sh", str(APPLY / "apply-manifest-check.sh"))
        for key in ("objects", "policy", "highest_tier"):
            s = s.replace("$(results." + key + ".path)", str(r / (key + ".result")))
        (r / "run.sh").write_text(s)
        env = {k: v for k, v in os.environ.items() if k != "KUBECONFIG"}
        env.update({"PATH": str(self.bin) + ":" + os.environ["PATH"], "TMPDIR": str(r / "tmp"),
                    "MODE": mode, "REPO": repo, "PATH_IN_REPO": path, "COMMIT": commit, "GITEA_BASE": base,
                    "GITEA_ORG": org, "REQUIRE_ON_MAIN": require, "GIT_USERNAME": "fixture",
                    "GIT_PASSWORD": "fixture", "PROBE_DIR": str(r), "PROBE_HEAD": HEAD})
        out = subprocess.run(["sh", str(r / "run.sh")], env=env, capture_output=True, text=True)
        return out.returncode, (r / "applied.json").exists(), out.stderr

    def test_allowed(self) -> None:
        for name, kw in (("b-branch", {"ns": "bifrost-dev", "require": "false"}),
                         ("c-head", {"commit": HEAD}),
                         ("c-old-unchanged", {}),
                         ("c-old-with-namespace", {"namespace": True}),  # review 548 R1
                         ("d-old-unchanged", {"tier_d": True})):
            with self.subTest(name):
                code, applied, err = self.run_case(name, **kw)
                self.assertEqual((code, applied), (0, True), err)

    def test_refused(self) -> None:
        for name, kw, why in (
                ("c-old-changed", {"changed": True}, "renders differently at main's head"),
                ("d-old-changed", {"changed": True, "tier_d": True}, "renders differently at main's head"),
                ("c-not-on-main", {"require": "false"}, "requireOnMain must be true"),
                ("wrong-repo", {"repo": "bifrost-platform"}, "not in the policy's apply list"),
                ("wrong-path", {"path": "k8sx/base"}, "not in the policy's apply list"),
                ("wrong-org", {"org": "other"}, "giteaOrg is not the policy's gitea_org"),
                ("wrong-base", {"base": "http://example.invalid/bifrost"}, "giteaBase is not the policy's gitea_base")):
            with self.subTest(name):
                code, applied, err = self.run_case(name, **kw)
                self.assertEqual((code, applied), (1, False), err)
                self.assertIn(why, err)

    def test_plan_is_not_compared(self) -> None:
        code, applied, err = self.run_case("c-plan", mode="plan", require="false", changed=True, namespace=True)
        self.assertEqual((code, applied), (0, False), err)


if __name__ == "__main__":
    unittest.main()
