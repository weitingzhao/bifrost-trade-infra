"""The Tekton Task bifrost-gitea-mirror-sync, run with a fake Gitea.

Step 0a of agent-config/work/multi-agent/CUT-gitea-primary-2026-10-17.md: each
repository is asked whether it is a pull mirror; a mirror is fetched, a
repository Gitea holds as its primary is not (Gitea answers mirror-sync on it
with 400), and a commit in expectSha is waited for on both. The Task's script
is taken from the YAML and run by sh with a fake curl; no cluster, no network.

    python3 -m unittest scripts/cicd/test_task_gitea_mirror_sync.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "k8s" / "cicd" / "tekton" / "task-gitea-mirror-sync.yaml"
SHA = "a" * 40

# The fake curl: answers from FAKE_GITEA ({"METHOD /path": [code, body]}),
# logs "METHOD /path" to FAKE_LOG, and prints what -w and -o ask for.
FAKE_CURL = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    from urllib.parse import urlparse
    args, method, fmt, out, url = sys.argv[1:], "GET", "", None, ""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-X":
            method = args[i + 1]; i += 2; continue
        if a == "-w":
            fmt = args[i + 1]; i += 2; continue
        if a == "-o":
            out = args[i + 1]; i += 2; continue
        if a in ("-H", "-d"):
            i += 2; continue
        if a.startswith("http"):
            url = a
        i += 1
    key = method + " " + urlparse(url).path
    with open(os.environ["FAKE_LOG"], "a") as fh:
        fh.write(key + "\\n")
    code, body = json.loads(os.environ["FAKE_GITEA"]).get(key, [404, "{}"])
    if out is None:
        sys.stdout.write(body)
    sys.stdout.write(fmt.replace("\\\\n", "\\n").replace("%{http_code}", str(code)))
    """
)


def task_script(repos: str, expect_sha: str = "", expect_repo: str = "") -> str:
    doc = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    script = doc["spec"]["steps"][0]["script"]
    for name, value in {
        "giteaBase": "http://gitea.test/bifrost",
        "mirrorRepos": repos,
        "expectSha": expect_sha,
        "expectRepo": expect_repo,
    }.items():
        script = script.replace(f"$(params.{name})", value)
    return script


def run(script: str, gitea: dict) -> tuple[subprocess.CompletedProcess, list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        bindir = Path(tmp) / "bin"
        bindir.mkdir()
        for name, body in {"curl": FAKE_CURL, "sleep": "#!/bin/sh\nexit 0\n"}.items():
            path = bindir / name
            path.write_text(body, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        log = Path(tmp) / "log"
        log.write_text("", encoding="utf-8")
        script_path = Path(tmp) / "task.sh"
        script_path.write_text(script, encoding="utf-8")
        env = {
            "PATH": f"{bindir}:/usr/bin:/bin",
            "GITEA_TOKEN": "fixture",
            "FAKE_GITEA": json.dumps(gitea),
            "FAKE_LOG": str(log),
        }
        result = subprocess.run(["sh", str(script_path)], env=env, capture_output=True, text=True, timeout=60)
        return result, log.read_text(encoding="utf-8").splitlines()


def repo(name: str, mirror) -> dict:
    body = {"name": name, "parent": None, "mirror_interval": "8h0m0s"}
    if mirror is not None:
        body["mirror"] = mirror
    return {f"GET /api/v1/repos/bifrost/{name}": [200, json.dumps(body, separators=(",", ":"))]}


class MirrorSyncTask(unittest.TestCase):
    def test_a_mirror_is_fetched_and_a_primary_is_not(self) -> None:
        gitea = {
            **repo("mirrored", True),
            **repo("primary", False),
            "POST /api/v1/repos/bifrost/mirrored/mirror-sync": [200, ""],
            "POST /api/v1/repos/bifrost/primary/mirror-sync": [400, '{"message":"Repository is not a mirror"}'],
            f"GET /api/v1/repos/bifrost/mirrored/git/commits/{SHA}": [200, "{}"],
            f"GET /api/v1/repos/bifrost/primary/git/commits/{SHA}": [200, "{}"],
        }
        result, calls = run(task_script("mirrored primary", SHA), gitea)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("POST /api/v1/repos/bifrost/mirrored/mirror-sync", calls)
        self.assertNotIn("POST /api/v1/repos/bifrost/primary/mirror-sync", calls)
        self.assertIn("bifrost/primary is Gitea's primary: nothing to fetch", result.stdout)
        self.assertIn(f"GET /api/v1/repos/bifrost/primary/git/commits/{SHA}", calls)

    def test_a_primary_commit_is_still_waited_for(self) -> None:
        gitea = {**repo("primary", False)}
        result, calls = run(task_script("primary", SHA), gitea)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("was not on the Gitea mirror", result.stderr)
        self.assertNotIn("POST /api/v1/repos/bifrost/primary/mirror-sync", calls)

    def test_only_primaries_do_not_wait_for_a_fetch(self) -> None:
        result, _ = run(task_script("primary"), {**repo("primary", False)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("waiting 8s", result.stdout)

    def test_a_repository_that_cannot_be_read_stops_the_task(self) -> None:
        result, calls = run(task_script("gone"), {})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("repository bifrost/gone → HTTP 404", result.stderr)
        self.assertFalse([c for c in calls if c.startswith("POST")])

    def test_an_answer_without_the_mirror_field_stops_the_task(self) -> None:
        result, calls = run(task_script("silent"), {**repo("silent", None)})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("did not say whether bifrost/silent is a mirror", result.stderr)
        self.assertFalse([c for c in calls if c.startswith("POST")])

    def test_a_refused_fetch_of_a_mirror_still_stops_the_task(self) -> None:
        gitea = {**repo("mirrored", True), "POST /api/v1/repos/bifrost/mirrored/mirror-sync": [503, ""]}
        result, _ = run(task_script("mirrored"), gitea)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
