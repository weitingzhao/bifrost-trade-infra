"""Protect/probe shell flows against a file-backed API; no sockets or credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent

# Independent expectations: do not ask production code to generate its oracle.
def expected(repo):
    landing = repo in ("bifrost-platform", "bifrost-trade-infra")
    teams = [] if landing else ["maintainers"]
    main = {"rule_name": "main", "enable_push": True, "enable_push_whitelist": True,
            "push_whitelist_usernames": ["vision", "agentrt-lander"] if landing else ["vision"],
            "push_whitelist_teams": teams, "push_whitelist_deploy_keys": False, "unprotected_file_patterns": "",
            "enable_merge_whitelist": True, "merge_whitelist_usernames": ["vision"],
            "merge_whitelist_teams": teams}
    return {"main": main, **({"land/prod/**": {**main, "rule_name": "land/prod/**",
            "push_whitelist_usernames": ["agentrt-lander"], "merge_whitelist_usernames": []}} if landing else {})}


@pytest.fixture
def fake(tmp_path):
    for name in ("protect-repo.sh", "protection_policy.py", "probe-infra-access.sh", "put-reader-token.sh"):
        shutil.copyfile(HERE / name, tmp_path / name)
    (tmp_path / "lib.sh").write_text('''set -euo pipefail
GITEA_ORG=bifrost
gitea_die() { echo "$*" >&2; exit 1; }
gitea_connect() { :; }
gitea_api() { "$TEST_PYTHON" "$TEST_API" "$@"; }
''')
    api = tmp_path / "api.py"
    api.write_text('''import json, os, sys
from pathlib import Path
from urllib.parse import unquote
state = Path(os.environ["TEST_STATE"])
rules = json.loads(state.read_text())
method, path, *body = sys.argv[1:]
fault = os.environ.get("TEST_API_FAULT", "")
with open(os.environ["TEST_CALLS"], "a") as log:
    log.write(method + " " + path + " " + " ".join(body) + "\\n")
if fault == "unreadable":
    sys.stderr.write("fixture-secret-must-not-leak")
    sys.exit(1)
if path == "/user":
    print(json.dumps({"login": "wrong" if fault == "identity" else "vision", "is_admin": fault != "nonadmin"}))
elif method == "GET":
    if fault == "malformed": print("not json")
    elif fault == "null": print("null")
    else: print(json.dumps(list(rules.values())))
elif fault == "refuse":
    sys.stderr.write("fixture-secret-must-not-leak")
    sys.exit(1)
else:
    if method == "POST" and path.endswith("/branch_protections"):
        data = json.loads(body[0]); rules[data["rule_name"]] = data
    elif method == "PATCH":
        rules[unquote(path.rsplit("/", 1)[1])].update(json.loads(body[0]))
    elif method == "DELETE":
        if fault != "keep_agent": rules.pop("agent/**")
    else: raise AssertionError("unexpected mutation")
    if fault == "readback": rules["main"]["enable_merge_whitelist"] = False
    state.write_text(json.dumps(rules))
    print("{}")
''')
    state, calls = tmp_path / "state.json", tmp_path / "calls"
    state.write_text("{}")
    env = {**os.environ, "TEST_PYTHON": sys.executable, "TEST_API": str(api),
           "TEST_STATE": str(state), "TEST_CALLS": str(calls)}

    def run(*options, repo="bifrost-trade-infra", fault="", xtrace=False):
        calls.write_text("")
        result = subprocess.run(["bash", *(["-x"] if xtrace else []), str(tmp_path / "protect-repo.sh"),
                                 *options, "--owner", "vision", repo],
                                env={**env, "TEST_API_FAULT": fault}, capture_output=True, text=True)
        assert "fixture-secret-must-not-leak" not in result.stdout + result.stderr + calls.read_text()
        return result
    return state, calls, run, env


@pytest.mark.parametrize("repo", ["bifrost-platform", "bifrost-trade-infra", "bifrost-ui"])
def test_dry_run_then_apply_and_idempotent_check(fake, repo):
    state, calls, run, _ = fake
    first = run(repo=repo)
    assert first.returncode == 0, first.stderr
    assert "dry-run" in first.stdout
    assert json.loads(state.read_text()) == {}
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    check = run("--check", repo=repo)
    assert check.returncode == 1 and "missing protection" in check.stderr
    result = run("--apply", repo=repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(state.read_text()) == expected(repo)
    for options in (("--apply",), ("--check",), ("--dry-run",)):
        result = run(*options, repo=repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


def test_s0_infra_upgrade_only_patches_push_users_and_preserves_hardening(fake):
    state, calls, run, _ = fake
    main = expected("bifrost-trade-infra")["main"]
    main.update(push_whitelist_usernames=["vision"], required_approvals=2, enable_status_check=True)
    initial = {"main": main, "agent/**": {"rule_name": "agent/**"}}
    state.write_text(json.dumps(initial))
    result = run()
    assert result.returncode == 0 and '"method":"PATCH"' in result.stdout
    assert json.loads(state.read_text()) == initial
    result = run("--apply")
    assert result.returncode == 0, result.stderr
    got = json.loads(state.read_text())
    assert got["main"] == {**main, "push_whitelist_usernames": ["vision", "agentrt-lander"]}
    assert set(got) == {"main", "land/prod/**"}
    patch = next(line for line in calls.read_text().splitlines() if line.startswith("PATCH "))
    assert json.loads(patch.split(" ", 2)[2]) == {"push_whitelist_usernames": ["vision", "agentrt-lander"]}


@pytest.mark.parametrize("rule,field,value", [
    ("main", "enable_push", False), ("main", "enable_push_whitelist", False),
    ("main", "push_whitelist_teams", ["maintainers"]),
    ("main", "push_whitelist_deploy_keys", True),
    ("main", "merge_whitelist_usernames", ["vision", "agentrt-lander"]),
    ("land/prod/**", "push_whitelist_usernames", ["vision", "agentrt-lander"]),
    ("land/prod/**", "enable_merge_whitelist", False),
    ("land/prod/**", "merge_whitelist_teams", ["maintainers"]),
    ("land/prod/**", "push_whitelist_teams", None),
    ("main", "enable_push", 1), ("main", "unprotected_file_patterns", "**"),
])
def test_existing_drift_blocks_every_mutation(fake, rule, field, value):
    state, calls, run, _ = fake
    rules = expected("bifrost-trade-infra")
    rules[rule][field] = value
    rules["agent/**"] = {"rule_name": "agent/**"}
    before = json.dumps(rules)
    state.write_text(before)
    for option in ("--check", "--apply", "--dry-run"):
        result = run(option)
        assert result.returncode == 1
        assert field in result.stderr
        assert state.read_text() == before
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


@pytest.mark.parametrize("name", ["**", "main*", "agent/*", "agent/{one,two}/**",
                                  "land/**", "land/prod/*", "land/prod/job/a1", "land/{stg,prod}/**",
                                  "land/prod/中文", "land/prod/[é-ê]/**", "agent/中文"])
def test_conflicting_rules_fail_before_writes(fake, name):
    state, calls, run, _ = fake
    state.write_text(json.dumps({name: {"rule_name": name}}))
    result = run("--apply")
    assert result.returncode == 1 and "STOPPED" in result.stderr
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


@pytest.mark.parametrize("name", ["release/**", "land/stg/**", "main?", "ma[st]er", "agent/."])
def test_unrelated_rule_is_preserved(fake, name):
    state, _, run, _ = fake
    state.write_text(json.dumps({name: {"rule_name": name}}))
    result = run("--apply")
    assert result.returncode == 0, result.stderr
    assert name in json.loads(state.read_text())


@pytest.mark.parametrize("fault", ["unreadable", "malformed", "null", "identity", "nonadmin", "refuse", "readback", "keep_agent"])
def test_unknown_and_failed_write_never_pass(fake, fault):
    state, _, run, _ = fake
    state.write_text(json.dumps({"agent/**": {"rule_name": "agent/**"}}))
    result = run("--apply", fault=fault)
    assert result.returncode != 0
    assert "FAIL" in result.stdout + result.stderr


def test_xtrace_and_bad_cli_stop_before_credentials(fake):
    _, calls, run, _ = fake
    for opts in (("--apply", "--check"), ("--unknown",)):
        assert run(*opts).returncode != 0
        assert calls.read_text() == ""
    result = run(xtrace=True)
    assert result.returncode != 0 and "xtrace" in result.stderr
    assert calls.read_text() == ""


@pytest.mark.parametrize("fault,policy_ok", [("", True), ("", False), ("reader_write", True), ("http", True)])
def test_combined_probe_is_get_only_and_aggregates_failure(fake, tmp_path, fault, policy_ok):
    sys.path.insert(0, str(HERE))
    from test_landing_drill_token import setup_fake
    from test_gitea_scripts import GITEA_TOKEN_FIXTURE, run_on_pty
    policy, calls, _, api_env = fake
    policy.write_text(json.dumps(expected("bifrost-trade-infra") if policy_ok else {}))
    state, env, _, _ = setup_fake(tmp_path, "prod", fault)
    result, echoed = run_on_pty(["bash", str(tmp_path / "probe-infra-access.sh"), "--owner", "vision", "prod"],
                               {**api_env, **env}, GITEA_TOKEN_FIXTURE)
    assert result.returncode == (0 if policy_ok and not fault else 1), result.stdout + result.stderr
    assert ("VERDICT PASS" if result.returncode == 0 else "VERDICT FAIL") in result.stdout
    assert not (state / "calls").exists()
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert all(line.startswith("GET ") for line in (state / "http-calls").read_text().splitlines())
    assert GITEA_TOKEN_FIXTURE not in result.stdout + result.stderr + echoed
