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
    # CEL has checks field presence without reading a possibly missing field.
    py = re.sub(r"has\(([\w.]+)\.([\w]+)\)", r"_has(\1, '\2')", py)
    # X.matches('re') -> _m(X, 're'): CEL's matches is an RE2 search; the filters anchor theirs (TD-435)
    py = re.sub(r"([\w.]+)\.matches\(('[^']*')\)", r"_m(\1, \2)", py)
    py = py.replace("&&", " and ").replace("||", " or ").replace(".startsWith(", ".startswith(")
    py = re.sub(r"!(?!=)", " not ", py)
    scope = {"body": Obj(body), "_m": lambda value, pattern: re.search(pattern, value) is not None,
             "_has": lambda obj, key: key in obj}
    return bool(eval(py, {"__builtins__": {}}, scope))  # noqa: S307 - our own file's filters


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
        assert expr.startswith("body.ref.startsWith('refs/heads/') && body.after.matches('^[0-9a-f]{40}$') && "
                               "body.after != '" + ZERO + "' && "), name
    # infra-ci (W-31 S6) has its own rule (repository first, no land/ or agent/
    # refs), pinned by scripts/landing/test_ci_infra_pins.py.
    assert set(filters()) == set(CI) | {"github-sync", "infra-ci"}


def test_a_posted_body_runs_nothing_unless_after_is_a_commit():
    # TD-435: the listener does not check the sender; `after` becomes `revision` in Task scripts
    for after in ("main;true", "$(id)", "A" * 40, "a" * 39, "a" * 41, ""):
        assert fired(push("bifrost-platform", "refs/heads/main", after=after)) == [], after
    # CI does not take the branch name, so any branch name still runs CI (review 546)
    assert "platform-ci" in fired(push("bifrost-platform", "refs/heads/feature/fix=1"))
    assert "platform-ci" in fired(push("bifrost-platform", "refs/heads/feature/修复"))
    # github-sync passes the ref on, so it takes main and plain tags only
    assert "github-sync" not in fired(push("bifrost-platform", "refs/tags/v1;true"))


def test_a_platform_attempt_or_land_branch_runs_no_ci():
    # R5:5.7-1: an attempt (agent/<task>/a<n>, pushed by agentd or handin) reaches main only
    # through a landing. R5:5.7-5: its branch land/<env>/<task>/<k> runs no webhook CI either;
    # the landing drill makes its own landing-ci-* there.
    attempt = "refs/heads/agent/t_01M6B2RDYZ5X554GXPGQDQGY3K/a1"
    assert [n for n in fired(push("bifrost-platform", attempt)) if n in CI] == []
    for env in ("prod", "stg"):
        land = f"refs/heads/land/{env}/t_01M6B2RDYZ5X554GXPGQDQGY3K/1"
        assert [n for n in fired(push("bifrost-platform", land)) if n in CI] == [], land
    # Only the prefixes: a branch whose name merely contains agent or land still runs.
    for ref in ("refs/heads/w31/agent/x", "refs/heads/agentic", "refs/heads/main",
                "refs/heads/landscape", "refs/heads/w31/land/x"):
        assert "platform-ci" in fired(push("bifrost-platform", ref)), ref
    # The other repositories keep their rule (bifrost-ui's attempt still runs both gates).
    assert [n for n in fired(push("bifrost-ui", attempt)) if n in CI] == ["frontend-ci-ui", "platform-ci-ui"]
    assert [n for n in fired(push("bifrost-trade-core", attempt)) if n in CI] == ["python-ci"]


@pytest.mark.parametrize("pusher", [
    {"login": "agentrt-lander"},
    {"username": "agentrt-lander"},
    {"login": "agentrt-lander", "username": "Owner"},
    {"login": "Owner", "username": "agentrt-lander"},
    {"login": "agentrt-lander", "username": "agentrt-lander"},
])
def test_lander_main_push_runs_no_second_platform_ci(pusher):
    body = push("bifrost-platform", "refs/heads/main")
    body["pusher"] = pusher
    assert "platform-ci" not in fired(body)


@pytest.mark.parametrize("pusher", [
    None, {}, {"login": "Owner"}, {"username": "another-user"},
    {"login": "Owner", "username": "Owner"},
    {"login": "agentrt-lander-extra", "username": "Agentrt-lander"},
])
def test_other_or_missing_pusher_runs_platform_ci(pusher):
    body = push("bifrost-platform", "refs/heads/main")
    if pusher is not None:
        body["pusher"] = pusher
    assert "platform-ci" in fired(body)


@pytest.mark.parametrize("repo, ci", [
    ("bifrost-trade-frontend", ["frontend-ci"]),
    ("bifrost-trade-core", ["python-ci"]),
    ("bifrost-research", ["python-ci"]),
    ("bifrost-ui", ["frontend-ci-ui", "platform-ci-ui"]),
    ("bifrost-trade-infra", ["infra-ci"]),
])
def test_lander_push_keeps_other_repositories_ci(repo, ci):
    body = push(repo, "refs/heads/main")
    body["repository"]["full_name"] = f"bifrost/{repo}"
    body["pusher"] = {"login": "agentrt-lander", "username": "agentrt-lander"}
    assert [n for n in fired(body) if n in CI + ["infra-ci"]] == ci
