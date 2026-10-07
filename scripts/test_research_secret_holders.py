"""Holder derivation for research Secret rotation. Fixtures are invented."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import research_secret_holders as holders  # noqa: E402


def _deploy(namespace: str, name: str, spec: dict) -> dict:
    return {"metadata": {"namespace": namespace, "name": name}, "spec": {"template": {"spec": spec}}}


class HolderTests(unittest.TestCase):
    def test_lists_every_deployment_that_mounts_the_secret(self) -> None:
        secret = "bifrost-research-secrets"
        items = [
            _deploy("research", "research-api", {"containers": [{"envFrom": [{"secretRef": {"name": secret}}]}]}),
            _deploy("research", "research-mcp", {"containers": [{"envFrom": [{"secretRef": {"name": secret, "optional": True}}]}]}),
            _deploy("research", "dagster-daemon", {"containers": [{"env": [{"valueFrom": {"secretKeyRef": {"name": secret, "key": "OPENAI_API_KEY"}}}]}]}),
            _deploy("research", "unrelated", {"containers": [{"envFrom": [{"secretRef": {"name": "other-secret"}}]}]}),
            _deploy("bifrost-dev", "trade-api", {"containers": [{"envFrom": [{"secretRef": {"name": secret}}]}]}),
        ]
        got = holders.deployments_mounting(items, secret)
        self.assertEqual(
            got,
            [
                ("research", "research-api"),
                ("research", "research-mcp"),
                ("research", "dagster-daemon"),
                ("bifrost-dev", "trade-api"),
            ],
        )

    def test_a_name_prefix_does_not_match(self) -> None:
        items = [
            _deploy("research", "decoy", {"containers": [{"envFrom": [{"secretRef": {"name": "bifrost-research-secrets-extra"}}]}]}),
        ]
        self.assertEqual(holders.deployments_mounting(items, "bifrost-research-secrets"), [])

    def test_checksum_changes_when_data_changes_and_hides_the_value(self) -> None:
        a = holders.secret_checksum({"OPENAI_API_KEY": "c2stZmFrZQ=="})
        b = holders.secret_checksum({"OPENAI_API_KEY": "c2stb3RoZXI="})
        self.assertNotEqual(a, b)
        self.assertNotIn("sk-", a)
        self.assertEqual(len(a), 64)


if __name__ == "__main__":
    unittest.main()
