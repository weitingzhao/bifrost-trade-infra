"""The Tekton Task bifrost-gitea-mirror-sync, run against a fake Gitea.

Step 0a of agent-config/work/multi-agent/CUT-gitea-primary-2026-10-17.md: each
repository is asked whether it is a pull mirror; a mirror is fetched, a
repository Gitea holds as its primary is not (Gitea answers mirror-sync on it
with 400), and a commit in expectSha is waited for on both. The answer is read
as JSON, its top-level "mirror" (review 243 A1), and the token goes in a
header (review 243 B). The Task's Python step is taken from the YAML and run
against a local HTTP server; no cluster, no network.

    python3 -m unittest scripts/cicd/test_task_gitea_mirror_sync.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_gitea import FakeGitea, repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "k8s" / "cicd" / "tekton" / "task-gitea-mirror-sync.yaml"
SHA = "a" * 40
TOKEN = "fixture-admin-token"


def run(gitea: FakeGitea, repos: str, sha: str = "", only: str = "") -> subprocess.CompletedProcess:
    script = yaml.safe_load(TASK.read_text(encoding="utf-8"))["spec"]["steps"][0]["script"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "step.py"
        path.write_text(script, encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GITEA_TOKEN": TOKEN,
            "GITEA_BASE": f"{gitea.base}/bifrost",
            "MIRROR_REPOS": repos,
            "EXPECT_SHA": sha,
            "EXPECT_REPO": only,
            "MIRROR_SYNC_POLL_SECONDS": "0",
            "MIRROR_SYNC_SETTLE_SECONDS": "0",
        }
        return subprocess.run([sys.executable, str(path)], env=env, capture_output=True, text=True, timeout=60)


class MirrorSyncTask(unittest.TestCase):
    def test_a_mirror_is_fetched_and_a_primary_is_not(self) -> None:
        routes = {
            **repo("mirrored", '{"name":"mirrored","parent":null,"mirror":true}'),
            **repo("primary", '{"name":"primary","parent":null,"mirror":false}'),
            "POST /api/v1/repos/bifrost/mirrored/mirror-sync": (200, ""),
            "POST /api/v1/repos/bifrost/primary/mirror-sync": (400, '{"message":"Repository is not a mirror"}'),
            f"GET /api/v1/repos/bifrost/mirrored/git/commits/{SHA}": (200, "{}"),
            f"GET /api/v1/repos/bifrost/primary/git/commits/{SHA}": (200, "{}"),
        }
        with FakeGitea(routes) as g:
            result = run(g, "mirrored primary", SHA)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("POST /api/v1/repos/bifrost/mirrored/mirror-sync", g.calls("POST"))
        self.assertNotIn("POST /api/v1/repos/bifrost/primary/mirror-sync", g.calls("POST"))
        self.assertIn("bifrost/primary is Gitea's primary: nothing to fetch", result.stdout)
        self.assertIn(f"GET /api/v1/repos/bifrost/primary/git/commits/{SHA}", g.calls())
        # every request carries the token in its header (review 243 B)
        self.assertTrue(all(auth == "token " + TOKEN for _, _, auth in g.requests))

    def test_the_top_level_field_decides_not_a_parents(self) -> None:
        routes = {
            # a fork whose parent is a mirror: the repository itself is a primary
            **repo("fork", '{"name":"fork","parent":{"name":"up","mirror":true},"mirror":false}'),
            # a mirror whose parent is not, with spaces in the JSON
            **repo("mirrored", '{ "name": "mirrored", "parent": { "mirror": false }, "mirror": true }'),
            "POST /api/v1/repos/bifrost/mirrored/mirror-sync": (200, ""),
        }
        with FakeGitea(routes) as g:
            result = run(g, "fork mirrored")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(g.calls("POST"), ["POST /api/v1/repos/bifrost/mirrored/mirror-sync"])

    def test_a_primary_commit_is_still_waited_for(self) -> None:
        with FakeGitea(repo("primary", '{"mirror":false}')) as g:
            result = run(g, "primary", SHA)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("was not on the Gitea mirror", result.stderr)
        self.assertEqual(g.calls("POST"), [])

    def test_only_primaries_do_not_wait_for_a_fetch(self) -> None:
        with FakeGitea(repo("primary", '{"mirror":false}')) as g:
            result = run(g, "primary")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("waiting 8s", result.stdout)

    def test_a_repository_that_cannot_be_read_stops_the_task(self) -> None:
        with FakeGitea({}) as g:
            result = run(g, "gone")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("repository bifrost/gone → HTTP 404", result.stderr)
        self.assertEqual(g.calls("POST"), [])

    def test_an_answer_that_does_not_say_stops_the_task(self) -> None:
        for body in ('{"name":"silent"}', '{"mirror":"true"}', "not json", "[]"):
            with FakeGitea(repo("silent", body)) as g:
                result = run(g, "silent")
            self.assertEqual(result.returncode, 1, body + result.stdout + result.stderr)
            self.assertIn("did not say whether bifrost/silent is a mirror", result.stderr)
            self.assertEqual(g.calls("POST"), [])

    def test_a_refused_fetch_of_a_mirror_still_stops_the_task(self) -> None:
        routes = {**repo("mirrored", '{"mirror":true}'), "POST /api/v1/repos/bifrost/mirrored/mirror-sync": (503, "")}
        with FakeGitea(routes) as g:
            result = run(g, "mirrored")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
