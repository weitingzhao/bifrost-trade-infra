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


def test_a_repository_named_only_by_digest_is_weighed(monkeypatch, tmp_path, capsys):
    """Review 513 C2: a repository with no tag kept, named only by digest, still counts."""
    import json
    import subprocess

    items = [deploy("192.168.10.73:30500/digest-only@" + D)]
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps({"items": items}), ""))
    asked = []

    def get(path, accept=None):
        asked.append(path)
        if path == "/v2/_catalog":
            return {"repositories": ["digest-only"]}, {}
        if path.endswith("/tags/list"):
            return {"tags": None}, {}
        if path == "/v2/digest-only/manifests/" + D:
            return {"layers": [{"digest": "sha256:" + "e" * 64, "size": 5}], "config": {"digest": "sha256:" + "f" * 64, "size": 1}}, {}
        raise AssertionError(path)

    monkeypatch.setattr(keepset, "get", get)
    monkeypatch.chdir(tmp_path)
    keepset.main()
    assert "/v2/digest-only/manifests/" + D in asked
    assert json.loads((tmp_path / "keepset-digests.json").read_text()) == {"digest-only": [D]}
    assert "唯一 blob: 2 个" in capsys.readouterr().out
