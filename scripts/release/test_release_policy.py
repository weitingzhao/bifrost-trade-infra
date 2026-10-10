"""release_policy.py render and the policy files it reads (W-42). No cluster."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import release_policy as rp  # noqa: E402

TEMPLATE = ROOT / "agent-config/release-policy/template.json"
PATHS = ROOT / "agent-config/release-policy/paths.json"
NOW = datetime(2026, 10, 10, 9, 30, 15, tzinfo=timezone.utc)


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


class RenderTests(unittest.TestCase):
    def test_render_fills_ids_and_merges_paths(self) -> None:
        doc = rp.render(load(TEMPLATE), load(PATHS), None, NOW)
        self.assertEqual(doc["policy_id"], "rp-20261010-0930")
        self.assertEqual(doc["signed_at"], "2026-10-10T09:30:15Z")
        self.assertEqual(doc["expires_at"], "2027-01-08T09:30:15Z")
        self.assertEqual(doc["valid_days"], 90)
        self.assertEqual(doc["version"], 1)
        self.assertNotIn("about", doc)
        for key in ("allow", "conditions", "reminders", "ci_repos", "db_steps", "pinned", "paths"):
            self.assertIn(key, doc)

    def test_days_override_and_bounds(self) -> None:
        doc = rp.render(load(TEMPLATE), load(PATHS), 7, NOW)
        self.assertEqual(doc["expires_at"], "2026-10-17T09:30:15Z")
        for bad in (0, -1, rp.MAX_DAYS + 1):
            with self.assertRaises(ValueError):
                rp.render(load(TEMPLATE), load(PATHS), bad, NOW)

    def test_canonical_text_is_stable(self) -> None:
        a = rp.canonical(rp.render(load(TEMPLATE), load(PATHS), None, NOW))
        b = rp.canonical(json.loads(a))
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("}\n"))

    def test_cli_writes_the_file_and_prints_the_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "policy.yaml"
            res = subprocess.run(
                [sys.executable, str(HERE / "release_policy.py"), "render", "--template", str(TEMPLATE),
                 "--paths", str(PATHS), "--now", "2026-10-10T09:30:15Z", "--out", str(out)],
                capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("policy_id rp-20261010-0930", res.stdout)
            self.assertEqual(json.loads(out.read_text())["policy_id"], "rp-20261010-0930")


class PolicyFileTests(unittest.TestCase):
    """What platform-api reads out of the signed policy (releasepolicy.Policy)."""

    def test_allow_names_real_pipelines(self) -> None:
        tekton = ROOT / "k8s/cicd/tekton"
        names = set()
        for f in tekton.glob("pipeline-*.yaml"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("  name: bifrost-"):
                    names.add(line.split(":", 1)[1].strip())
        plugin_builds = {"bifrost-build-flex-query", "bifrost-build-market-data", "bifrost-build-ib-gateway"}
        for name in load(TEMPLATE)["allow"]:
            if name in plugin_builds:
                continue
            self.assertIn(name, names, f"allow names {name}, which no Tekton pipeline in k8s/cicd/tekton defines")

    def test_conditions_are_all_on(self) -> None:
        cond = load(TEMPLATE)["conditions"]
        for key in ("ci_succeeded", "window_held_by_requester", "no_pending_before_db_steps", "no_ddl",
                    "additive_ddl", "no_d10_paths", "no_trust_anchor_change"):
            self.assertIs(cond[key], True, key)
        self.assertEqual(cond["revision"], "main-or-tag")

    def test_reminders_are_14d_3d_1d(self) -> None:
        self.assertEqual(load(TEMPLATE)["reminders"]["before_expiry_hours"], [336, 72, 24])

    def test_db_steps_dir_exists_and_envs_are_known(self) -> None:
        db = load(PATHS)["db_steps"]
        self.assertEqual(db["repo"], "bifrost-trade-infra")
        self.assertTrue((ROOT / db["dir"]).is_dir())
        self.assertLessEqual(set(db["pipelines"].values()), {"dev", "stg", "prod"})

    def test_pinned_params_match_the_pinned_scripts(self) -> None:
        pinned = load(PATHS)["pinned"]
        prod = pinned["bifrost-deliver-prod"]
        self.assertEqual(prod["from"], "bifrost-deliver-stg")
        script = (HERE / "prod-pinned-from-stg.sh").read_text(encoding="utf-8")
        for param in prod["params"]:
            self.assertIn(f'"{param}"', script)
        plat = pinned["bifrost-deliver-platform-prod"]
        self.assertEqual(plat["from"], "bifrost-deliver-platform")
        self.assertIn("revision", plat["params"])

    def test_trust_anchor_covers_the_policy_and_this_script(self) -> None:
        rules = load(PATHS)["paths"]["no_trust_anchor_change"]
        infra = next(r["paths"] for r in rules if r["repo"] == "bifrost-trade-infra")
        for p in ("agent-config/release-policy/**", "scripts/release/release.sh", "scripts/release/release_policy.py",
                  "k8s/cicd/release-policy/**", "k8s/cicd/tekton/task-release-window.yaml"):
            self.assertIn(p, infra)
        platform = next(r["paths"] for r in rules if r["repo"] == "bifrost-platform")
        self.assertIn("api/internal/releasepolicy/**", platform)


if __name__ == "__main__":
    unittest.main()
