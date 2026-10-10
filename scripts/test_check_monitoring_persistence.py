"""TD-289: Prometheus and Alertmanager data survives an eviction. Fixtures are invented."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_monitoring_persistence as mon  # noqa: E402


def _values() -> dict:
    return yaml.safe_load(mon.VALUES.read_text())


def _pod(volume: dict) -> dict:
    return {"metadata": {"name": "prometheus-x-0"}, "spec": {"volumes": [{"name": "config", "secret": {}}, volume]}}


class StaticTests(unittest.TestCase):
    def test_repo_values_carry_the_claims(self) -> None:
        self.assertEqual(mon.static_problems(_values()), [])

    def test_the_old_values_are_refused(self) -> None:
        # What ran until 2026-10-10: retention only, no storage.
        values = copy.deepcopy(_values())
        values["prometheus"]["prometheusSpec"].pop("storageSpec")
        values["prometheus"]["prometheusSpec"].pop("retentionSize")
        values["alertmanager"]["alertmanagerSpec"].pop("storage")
        problems = mon.static_problems(values)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("prometheusSpec.storageSpec", problems[0])
        self.assertIn("alertmanagerSpec.storage", problems[1])

    def test_a_claim_without_a_retention_cap_is_refused(self) -> None:
        values = copy.deepcopy(_values())
        values["prometheus"]["prometheusSpec"].pop("retentionSize")
        self.assertEqual(len(mon.static_problems(values)), 1)

    def test_a_cap_at_or_above_the_claim_is_refused(self) -> None:
        values = copy.deepcopy(_values())
        values["prometheus"]["prometheusSpec"]["retentionSize"] = "40GB"
        problems = mon.static_problems(values)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("not below the claim size", problems[0])

    def test_sizes(self) -> None:
        self.assertEqual(mon.size_bytes("30Gi"), 30 * 2**30)
        self.assertEqual(mon.size_bytes("25GB"), 25e9)
        self.assertIsNone(mon.size_bytes("plenty"))


class LiveTests(unittest.TestCase):
    def test_an_emptydir_data_volume_is_a_problem(self) -> None:
        problems = mon.live_pod_problems(_pod({"name": "db", "emptyDir": {}}), "db", {})
        self.assertEqual(len(problems), 1)
        self.assertIn("is emptyDir", problems[0])

    def test_a_bound_claim_passes(self) -> None:
        pod = _pod({"name": "db", "persistentVolumeClaim": {"claimName": "db-claim"}})
        self.assertEqual(mon.live_pod_problems(pod, "db", {"db-claim": "Bound"}), [])

    def test_a_pending_claim_is_a_problem(self) -> None:
        pod = _pod({"name": "db", "persistentVolumeClaim": {"claimName": "db-claim"}})
        problems = mon.live_pod_problems(pod, "db", {"db-claim": "Pending"})
        self.assertEqual(len(problems), 1)
        self.assertIn("Pending", problems[0])

    def test_a_missing_data_volume_is_a_problem(self) -> None:
        self.assertEqual(len(mon.live_pod_problems(_pod({"name": "other", "emptyDir": {}}), "db", {})), 1)


if __name__ == "__main__":
    unittest.main()
