"""policy_check.py decision table (LANE-RP). No cluster.

Signatures use a throwaway ed25519 key made in a temp dir per test class and deleted
with it; nothing here touches the Owner's key.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ci_gate  # noqa: E402
import policy_check as pc  # noqa: E402

INFRA = Path(__file__).resolve().parents[2]
DRAFT = INFRA / "agent-config/work/release-approval/release-policy.draft.yaml"
PATHS = INFRA / "agent-config/release-policy/paths.json"
NOW = pc.parse_iso("2026-10-08T12:00:00Z")
HAVE_SSH_KEYGEN = shutil.which("ssh-keygen") is not None


def sign(key: Path, text: str, namespace: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "data"
        f.write_text(text, encoding="utf-8")
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", namespace, str(f)],
                       check=True, capture_output=True)
        return (Path(tmp) / "data.sig").read_text(encoding="utf-8")


class TemplateAndGlobTests(unittest.TestCase):
    def test_draft_renders(self):
        template = pc.parse_template(DRAFT.read_text(encoding="utf-8"))
        paths = json.loads(PATHS.read_text(encoding="utf-8"))
        policy = pc.render_policy(template, paths, NOW)
        self.assertEqual(policy["policy_id"], "rp-20261008-1200")
        self.assertEqual(policy["expires_at"], "2026-10-15T12:00:00Z")
        self.assertIn("merge-to-main", policy["allow"])
        self.assertIn("bifrost-deliver-platform-prod", policy["allow"])
        self.assertEqual(policy["reminders"]["before_expiry_hours"], [48, 24, 2])
        self.assertEqual(policy["limits"]["rolling_24h"], "none")
        for rule in pc.PATH_RULES:
            self.assertIs(policy["conditions"][rule], True)
            self.assertTrue(policy["paths"][rule])
        self.assertEqual(json.loads(pc.dump_policy(policy)), policy)

    def test_days_override(self):
        template = pc.parse_template(DRAFT.read_text(encoding="utf-8"))
        policy = pc.render_policy(template, json.loads(PATHS.read_text()), NOW, days=2)
        self.assertEqual(policy["expires_at"], "2026-10-10T12:00:00Z")

    def test_template_refuses_deep_nesting(self):
        with self.assertRaises(ValueError):
            pc.parse_template("a:\n  b:\n    c: 1\n")

    def test_globs(self):
        self.assertTrue(pc.path_matches("src/x/persistence/postgres/ddl.py", "**/ddl*.py"))
        self.assertTrue(pc.path_matches("ddl.py", "**/ddl*.py"))
        self.assertTrue(pc.path_matches("scripts/db/a.sql", "**/*.sql"))
        self.assertFalse(pc.path_matches("src/model.py", "**/*.sql"))
        self.assertTrue(pc.path_matches("api/internal/approvals/service.go", "api/internal/approvals/**"))
        self.assertFalse(pc.path_matches("api/internal/approvalsx/a.go", "api/internal/approvals/**"))
        self.assertFalse(pc.path_matches("k8s/overlays/stg/x/kustomization.yaml", "k8s/overlays/*/kustomization.yaml"))

    def test_every_path_rule_has_a_hit_in_the_real_table(self):
        table = json.loads(PATHS.read_text())["rules"]
        cases = {
            "no_ddl": ("bifrost-trade-core", "src/bifrost_core/persistence/postgres/ddl.py"),
            "no_d10_paths": ("bifrost-trade-infra", "k8s/overlays/prod/daemon-observe-safe.patch.yaml"),
            "no_trust_anchor_change": ("bifrost-platform", "api/internal/releasepolicy/engine.go"),
        }
        for rule, (repo, path) in cases.items():
            self.assertEqual(pc.rule_hits(table, rule, repo, [path, "README.md"]), [path], rule)
        self.assertEqual(pc.rule_hits(table, "no_d10_paths", "bifrost-trade-api",
                                      ["src/bifrost_api/monitor/routers/daemon.py"]),
                         ["src/bifrost_api/monitor/routers/daemon.py"])
        self.assertEqual(pc.rule_hits(table, "no_trust_anchor_change", "bifrost-trade-infra",
                                      ["scripts/release/release.sh", "docs/RELEASE.md"]),
                         ["scripts/release/release.sh"])


@unittest.skipUnless(HAVE_SSH_KEYGEN, "ssh-keygen not installed")
class SignedPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="rp-test-"))
        cls.key = cls.tmp / "throwaway"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(cls.key)], check=True)
        pub = (cls.tmp / "throwaway.pub").read_text().strip()
        cls.allowed = cls.tmp / "allowed_signers"
        cls.allowed.write_text(
            f'# test anchor\nowner namespaces="{pc.NS_POLICY},{pc.NS_UNFREEZE}" {pub}\n', encoding="utf-8")
        other = cls.tmp / "other"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "other", "-f", str(other)], check=True)
        cls.other_key = other
        template = pc.parse_template(DRAFT.read_text(encoding="utf-8"))
        cls.paths = json.loads(PATHS.read_text())
        cls.policy_text = pc.dump_policy(pc.render_policy(template, cls.paths, NOW - timedelta(days=1)))
        cls.policy_sig = sign(cls.key, cls.policy_text, pc.NS_POLICY)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def state(self, text=None, sig=None, now=NOW):
        return pc.policy_state(self.policy_text if text is None else text,
                               self.policy_sig if sig is None else sig, self.allowed, now)

    def clean(self, repo="bifrost-trade-api", files=("src/bifrost_api/app.py",)):
        return [{"repo": repo, "old": "a" * 40, "new": "b" * 40, "files": list(files)}]

    UNFROZEN = {"frozen": False, "reason": "never frozen"}

    def test_valid_policy_clean_diff_auto_approves(self):
        code, reasons = pc.decide(self.state(), self.UNFROZEN, "bifrost-deliver-stg", self.clean())
        self.assertEqual((code, reasons), (pc.EXIT_OK, []))

    def test_each_path_rule_hit_needs_the_owner(self):
        for repo, path, rule in (
            ("bifrost-trade-core", "src/bifrost_core/persistence/postgres/ddl.py", "no_ddl"),
            ("bifrost-research", "k8s/jobs/ddl-apply.yaml", "no_ddl"),
            ("bifrost-trade-worker", "src/bifrost_worker/daemon/execution/order_manager.py", "no_d10_paths"),
            ("bifrost-trade-infra", "k8s/overlays/stg/daemon-scale-zero.patch.yaml", "no_d10_paths"),
            ("bifrost-platform", "api/internal/approvals/service.go", "no_trust_anchor_change"),
            ("bifrost-trade-infra", "agent-config/release-policy/allowed_signers", "no_trust_anchor_change"),
        ):
            code, reasons = pc.decide(self.state(), self.UNFROZEN, "bifrost-deliver-stg",
                                      self.clean(repo, ["README.md", path]))
            self.assertEqual(code, pc.EXIT_OWNER, path)
            self.assertIn(rule, reasons[0], path)

    def test_action_outside_allow_needs_the_owner(self):
        code, reasons = pc.decide(self.state(), self.UNFROZEN, "bifrost-deliver-prod", self.clean())
        self.assertEqual(code, pc.EXIT_OWNER)
        self.assertIn("not in the policy's allow list", reasons[0])

    def test_tampered_policy_needs_the_owner(self):
        tampered = self.policy_text.replace('"merge-to-main"', '"anything"')
        st = self.state(text=tampered)
        self.assertFalse(st["valid"])
        code, reasons = pc.decide(st, self.UNFROZEN, "bifrost-deliver-stg", self.clean())
        self.assertEqual(code, pc.EXIT_OWNER)
        self.assertIn("signature does not verify", reasons[0])

    def test_signature_by_another_key_needs_the_owner(self):
        st = self.state(sig=sign(self.other_key, self.policy_text, pc.NS_POLICY))
        self.assertFalse(st["valid"])

    def test_signature_in_the_unfreeze_namespace_is_not_a_policy(self):
        st = self.state(sig=sign(self.key, self.policy_text, pc.NS_UNFREEZE))
        self.assertFalse(st["valid"])

    def test_expired_policy_needs_the_owner(self):
        st = self.state(now=NOW + timedelta(days=7))
        self.assertFalse(st["valid"])
        self.assertIn("expired", st["reasons"][0])

    def test_missing_policy_or_sig_needs_the_owner(self):
        self.assertFalse(pc.policy_state("", "", self.allowed, NOW)["valid"])
        self.assertFalse(pc.policy_state(self.policy_text, "", self.allowed, NOW)["valid"])

    def test_no_trust_anchor_needs_the_owner(self):
        empty = self.tmp / "empty_signers"
        empty.write_text("# nothing yet\n")
        st = pc.policy_state(self.policy_text, self.policy_sig, empty, NOW)
        self.assertFalse(st["valid"])
        self.assertIn("trust anchor", st["reasons"][0])

    def test_unreadable_diff_and_blocks_need_the_owner(self):
        code, reasons = pc.decide(self.state(), self.UNFROZEN, "bifrost-deliver-stg",
                                  [{"repo": "bifrost-trade-api", "error": "no checkout"}])
        self.assertEqual(code, pc.EXIT_OWNER)
        code, reasons = pc.decide(self.state(), self.UNFROZEN, "bifrost-deliver-stg", self.clean(),
                                  ["--allow-red was used"])
        self.assertEqual((code, reasons), (pc.EXIT_OWNER, ["--allow-red was used"]))

    # ── freeze ──

    def test_freeze_states(self):
        frozen = pc.freeze_state({"frozen": "true", "frozen_at": "2026-10-08T10:00:00Z", "who": "x", "reason": "r"},
                                 self.allowed)
        self.assertTrue(frozen["frozen"])
        self.assertTrue(pc.freeze_state(None, self.allowed)["frozen"])
        self.assertTrue(pc.freeze_state({"frozen": "maybe"}, self.allowed)["frozen"])
        self.assertFalse(pc.freeze_state({"frozen": "false"}, self.allowed)["frozen"])
        code, reasons = pc.decide(self.state(), frozen, "bifrost-deliver-stg", self.clean())
        self.assertEqual(code, pc.EXIT_FROZEN)
        self.assertIn("frozen", reasons[0])

    def test_unfreeze_needs_a_signed_text_for_that_freeze(self):
        at = "2026-10-08T10:00:00Z"
        text = f"unfreeze frozen_at={at} at=2026-10-08T11:00:00Z by=owner\n"
        data = {"frozen": "false", "frozen_at": at, "unfreeze.txt": text,
                "unfreeze.sig": sign(self.key, text, pc.NS_UNFREEZE)}
        self.assertFalse(pc.freeze_state(data, self.allowed, seen_frozen_at=at)["frozen"])
        unsigned = dict(data, **{"unfreeze.sig": sign(self.other_key, text, pc.NS_UNFREEZE)})
        self.assertTrue(pc.freeze_state(unsigned, self.allowed)["frozen"])
        policy_ns = dict(data, **{"unfreeze.sig": sign(self.key, text, pc.NS_POLICY)})
        self.assertTrue(pc.freeze_state(policy_ns, self.allowed)["frozen"])
        no_text = {"frozen": "false", "frozen_at": at}
        self.assertTrue(pc.freeze_state(no_text, self.allowed)["frozen"])

    def test_old_unfreeze_cannot_lift_a_newer_freeze(self):
        at = "2026-10-08T10:00:00Z"
        text = f"unfreeze frozen_at={at} at=2026-10-08T11:00:00Z by=owner\n"
        replay = {"frozen": "false", "frozen_at": at, "unfreeze.txt": text,
                  "unfreeze.sig": sign(self.key, text, pc.NS_UNFREEZE)}
        self.assertTrue(pc.freeze_state(replay, self.allowed, seen_frozen_at="2026-10-08T11:30:00Z")["frozen"])
        erased = {"frozen": "false"}
        self.assertTrue(pc.freeze_state(erased, self.allowed, seen_frozen_at="2026-10-08T11:30:00Z")["frozen"])

    def test_seen_file_keeps_the_newest_freeze(self):
        seen = self.tmp / "seen"
        pc.update_seen(seen, {"frozen": "true", "frozen_at": "2026-10-08T10:00:00Z"})
        pc.update_seen(seen, {"frozen": "true", "frozen_at": "2026-10-07T10:00:00Z"})
        self.assertEqual(pc.update_seen(seen, {"frozen": "false"}), "2026-10-08T10:00:00Z")

    # ── the CLI against a real git diff ──

    def _cm(self, name, data):
        path = self.tmp / f"{name}.json"
        path.write_text(json.dumps({"data": data}) if data is not None else "", encoding="utf-8")
        return str(path)

    def _repo(self):
        root = Path(tempfile.mkdtemp(prefix="rp-root-", dir=self.tmp))
        repo = root / "bifrost-trade-core"
        repo.mkdir()
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        (repo / "README.md").write_text("a\n")
        subprocess.run(git + ["add", "README.md"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "one"], check=True)
        old = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        (repo / "README.md").write_text("b\n")
        subprocess.run(git + ["commit", "-q", "-am", "two"], check=True)
        clean = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        ddl = repo / "src/bifrost_core/persistence/postgres"
        ddl.mkdir(parents=True)
        (ddl / "ddl.py").write_text("x = 1\n")
        subprocess.run(git + ["add", "src"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "three"], check=True)
        dirty = subprocess.run(git[:3] + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        return root, old, clean, dirty

    def _check(self, root, pair, policy=True, freeze=None, action="bifrost-deliver-stg"):
        policy_cm = self._cm("policy", {"policy.yaml": self.policy_text, "policy.sig": self.policy_sig,
                                        "allowed_signers": self.allowed.read_text()} if policy else None)
        freeze_cm = self._cm("freeze", freeze if freeze is not None else {"frozen": "false"})
        return pc.main(["check", "--policy-cm", policy_cm, "--freeze-cm", freeze_cm,
                        "--allowed-signers", str(self.allowed), "--now", "2026-10-08T12:00:00Z",
                        "--action", action, "--root", str(root), "--pair", pair])

    def test_cli_check(self):
        root, old, clean, dirty = self._repo()
        self.assertEqual(self._check(root, f"bifrost-trade-core={old}..{clean}"), pc.EXIT_OK)
        self.assertEqual(self._check(root, f"bifrost-trade-core={old}..{dirty}"), pc.EXIT_OWNER)
        self.assertEqual(self._check(root, f"bifrost-trade-core=missing..{clean}"), pc.EXIT_OWNER)
        self.assertEqual(self._check(root, f"bifrost-trade-core={old}..{clean}", policy=False), pc.EXIT_OWNER)
        self.assertEqual(self._check(root, f"bifrost-trade-core={old}..{clean}", freeze={"frozen": "true"}),
                         pc.EXIT_FROZEN)
        self.assertEqual(self._check(root, f"bifrost-trade-core={old}..{clean}", freeze={}), pc.EXIT_FROZEN)

    def test_cli_check_refuses_a_shipped_anchor_that_differs(self):
        root, old, clean, _ = self._repo()
        policy_cm = self._cm("policy", {"policy.yaml": self.policy_text, "policy.sig": self.policy_sig,
                                        "allowed_signers": "owner ssh-ed25519 AAAAdifferent\n"})
        rc = pc.main(["check", "--policy-cm", policy_cm, "--freeze-cm", self._cm("freeze", {"frozen": "false"}),
                      "--allowed-signers", str(self.allowed), "--now", "2026-10-08T12:00:00Z",
                      "--action", "bifrost-deliver-stg", "--root", str(root),
                      "--pair", f"bifrost-trade-core={old}..{clean}"])
        self.assertEqual(rc, pc.EXIT_OWNER)


class RecordAndCiTests(unittest.TestCase):
    def test_pick_record(self):
        def rec(run, lane, env, at, sha):
            return {"data": {"record.json": json.dumps({
                "run": run, "lane": lane, "env": env, "completed_at": at,
                "repos": {"bifrost-trade-core": {"sha": sha}}})}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.json"
            path.write_text(json.dumps({"items": [
                rec("stg-1", "trade", "stg", "2026-10-07T00:00:00Z", "a" * 40),
                rec("stg-2", "trade", "stg", "2026-10-08T00:00:00Z", "b" * 40),
                rec("prod-1", "trade", "prod", "2026-10-08T01:00:00Z", "c" * 40),
            ]}))
            records = pc.load_records(path)
            self.assertEqual(pc.pick_record(records, "trade", "stg")["run"], "stg-2")
            self.assertEqual(pc.pick_record(records, run="stg-1")["repos"]["bifrost-trade-core"]["sha"], "a" * 40)
            self.assertIsNone(pc.pick_record(records, "platform", "prod"))

    def test_ci_gate_counts_the_platform_pipeline(self):
        run = {"metadata": {"labels": {"tekton.dev/pipeline": "bifrost-ci-platform", "bifrost.io/repo": "bifrost-platform"}},
               "spec": {"params": [{"name": "revision", "value": "d" * 40}]},
               "status": {"conditions": [{"type": "Succeeded", "status": "True"}]}}
        self.assertEqual(ci_gate.classify([run], "bifrost-platform", "d" * 40), "succeeded")


if __name__ == "__main__":
    unittest.main()
