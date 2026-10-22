"""W-31 3.4 ② (Owner 2026-10-21 「D3 A」): CI runs on every branch push, so a lane's commit is
green before push-main.sh lets it reach main. The EventListener's CEL filters are evaluated
here on Gitea push bodies (a small translation of the operators these filters use)."""

from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TRIGGER = ROOT / "k8s/cicd/tekton/trigger-trade-ci.yaml"
ZERO = "0" * 40
SHA = "a" * 40
CI = ["python-ci", "frontend-ci", "frontend-ci-ui", "platform-ci", "platform-ci-ui"]


class Obj(dict):
    def __getattr__(self, name):
        value = self.get(name)
        return Obj(value) if isinstance(value, dict) else value


def filters():
    docs = [d for d in yaml.safe_load_all(TRIGGER.read_text()) if d]
    (el,) = [d for d in docs if d["kind"] == "EventListener" and d["metadata"]["name"] == "bifrost-ci"]
    out = {}
    for trigger in el["spec"]["triggers"]:
        (cel,) = [i for i in trigger["interceptors"] if i["ref"]["name"] == "cel"]
        (expr,) = [p["value"] for p in cel["params"] if p["name"] == "filter"]
        out[trigger["name"]] = expr
    return out


def evaluate(expr, body):
    py = " ".join(expr.split())
    py = py.replace("&&", " and ").replace("||", " or ").replace(".startsWith(", ".startswith(")
    py = re.sub(r"!(?!=)", " not ", py)
    return bool(eval(py, {"__builtins__": {}}, {"body": Obj(body)}))  # noqa: S307 - our own file's filters


def fired(body):
    return sorted(name for name, expr in filters().items() if evaluate(expr, body))


def push(repo, ref, after=SHA, mirror=False):
    return {"ref": ref, "after": after, "repository": {"name": repo, "mirror": mirror}}


@pytest.mark.parametrize(
    "repo, ci",
    [
        ("bifrost-platform", ["platform-ci"]),
        ("bifrost-trade-frontend", ["frontend-ci"]),
        ("bifrost-trade-core", ["python-ci"]),
        ("bifrost-research", ["python-ci"]),
        ("bifrost-ui", ["frontend-ci-ui", "platform-ci-ui"]),
        ("bifrost-trade-infra", []),
    ],
)
def test_a_branch_push_runs_the_repos_ci(repo, ci):
    # the branch a lane pushes before push-main (W-31 3.4 ②)
    assert [n for n in fired(push(repo, "refs/heads/w31/some-lane")) if n in CI] == ci
    # main as before
    assert [n for n in fired(push(repo, "refs/heads/main")) if n in CI] == ci


@pytest.mark.parametrize("repo", ["bifrost-platform", "bifrost-trade-core", "bifrost-ui"])
def test_tags_and_branch_deletions_run_no_ci(repo):
    assert not [n for n in fired(push(repo, "refs/tags/v1.2.3")) if n in CI]
    assert not [n for n in fired(push(repo, "refs/heads/w31/gone", after=ZERO)) if n in CI]


def test_github_sync_still_follows_main_and_tags_only():
    assert "github-sync" in fired(push("bifrost-platform", "refs/heads/main"))
    assert "github-sync" in fired(push("bifrost-platform", "refs/tags/v1"))
    assert "github-sync" not in fired(push("bifrost-platform", "refs/heads/w31/some-lane"))
    assert "github-sync" not in fired(push("bifrost-platform", "refs/heads/main", mirror=True))


def test_every_ci_filter_has_the_same_ref_rule():
    for name in CI:
        expr = " ".join(filters()[name].split())
        assert expr.startswith("body.ref.startsWith('refs/heads/') && body.after != '" + ZERO + "' && "), name
    assert set(filters()) == set(CI) | {"github-sync"}
