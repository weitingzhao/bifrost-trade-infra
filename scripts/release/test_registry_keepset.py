"""TD-335 (W-31 3.4 ①): the registry keep set keeps what the workloads name by digest."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/registry"))

import keepset  # noqa: E402  (main() runs only as a script)

D = "sha256:" + "d" * 64


def deploy(*images):
    return {"spec": {"template": {"spec": {"containers": [{"image": i} for i in images]}}}}


def test_digest_and_tag_references():
    tags, digests = keepset.references([
        deploy("192.168.10.73:30500/bifrost-platform-api@" + D),
        deploy("192.168.10.73:30500/bifrost-platform-console:prod@" + D),
        deploy("192.168.10.73:30500/bifrost-research:0.113.0"),
        {"spec": {"jobTemplate": {"spec": {"template": {"spec": {"initContainers": [
            {"image": "192.168.10.73:30500/bifrost-platform-api:stg"}]}}}}}},
        deploy("redis:7-alpine", "ghcr.io/cloudnative-pg/postgresql:17.9"),
    ])
    assert digests == {("bifrost-platform-api", D), ("bifrost-platform-console", D)}
    assert tags == {("bifrost-platform-console", "prod"), ("bifrost-research", "0.113.0"), ("bifrost-platform-api", "stg")}


def test_moving_tags_still_kept():
    assert {"prod", "stg", "stg-candidate", "prod-candidate"} <= keepset.MOVING
