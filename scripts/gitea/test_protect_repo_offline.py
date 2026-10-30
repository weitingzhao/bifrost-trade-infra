"""Protect/probe shell flows against a file-backed API; no sockets or credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from protection_fixture import PROTECTION_DEFAULTS, protection_rule

HERE = Path(__file__).resolve().parent

# Independent expectations: do not ask production code to generate its oracle.
def expected(repo):
    landing = repo in ("bifrost-platform", "bifrost-trade-infra")
    teams = [] if landing else ["maintainers"]
    main = {**protection_rule("main"), "enable_push": True, "enable_push_whitelist": True,
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
    if (HERE / "protection_state.py").exists():
        shutil.copyfile(HERE / "protection_state.py", tmp_path / "protection_state.py")
    (tmp_path / "lib.sh").write_text('''set -euo pipefail
GITEA_ORG=bifrost
gitea_die() { echo "$*" >&2; exit 1; }
gitea_connect() { :; }
gitea_api() { "$TEST_PYTHON" "$TEST_API" "$@"; }
''')
    api = tmp_path / "api.py"
    api.write_text('PROTECTION_DEFAULTS = ' + repr(PROTECTION_DEFAULTS) + '\n' + '''import json, os, sys
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
    else:
        if fault.startswith("omit:"): rules["main"].pop(fault.split(":", 1)[1])
        if fault.startswith("invalid:"): rules["main"][fault.split(":", 1)[1]] = {"fixture-secret-must-not-leak": True}
        print(json.dumps(list(rules.values())))
elif fault == "refuse":
    sys.stderr.write("fixture-secret-must-not-leak")
    sys.exit(1)
else:
    if method == "POST" and path.endswith("/branch_protections"):
        data = json.loads(body[0]); rules[data["rule_name"]] = {**PROTECTION_DEFAULTS, **data}
    elif method == "PATCH":
        rules[unquote(path.rsplit("/", 1)[1])].update(json.loads(body[0]))
    elif method == "DELETE":
        if fault != "keep_agent": rules.pop(unquote(path.rsplit("/", 1)[1]))
    else: raise AssertionError("unexpected mutation")
    if fault == "readback" and "main" in rules: rules["main"]["enable_merge_whitelist"] = False
    if fault == "landing_extra" and method == "POST": rules["land/prod/**"]["push_whitelist_usernames"].append("vision")
    if fault == "hardening" and method == "PATCH": rules["main"]["required_approvals"] = 0
    if fault == "other_rule": rules["release/**"]["enable_push"] = True
    if fault == "missing_post" and method == "POST": rules.pop(json.loads(body[0])["rule_name"])
    if fault == "extra_rule": rules["release/unexpected"] = {**PROTECTION_DEFAULTS, "rule_name": "release/unexpected"}
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
    initial = {"main": main, "agent/**": protection_rule("agent/**")}
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
    rules["agent/**"] = protection_rule("agent/**")
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
    state.write_text(json.dumps({name: protection_rule(name)}))
    result = run("--apply")
    assert result.returncode == 1 and "STOPPED" in result.stderr
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


@pytest.mark.parametrize("name", ["release/**", "land/stg/**", "main?", "ma[st]er", "agent/."])
def test_unrelated_rule_is_preserved(fake, name):
    state, _, run, _ = fake
    state.write_text(json.dumps({name: protection_rule(name)}))
    result = run("--apply")
    assert result.returncode == 0, result.stderr
    assert name in json.loads(state.read_text())


@pytest.mark.parametrize("fault", ["unreadable", "malformed", "null", "identity", "nonadmin", "refuse", "readback", "keep_agent"])
def test_unknown_and_failed_write_never_pass(fake, fault):
    state, _, run, _ = fake
    state.write_text(json.dumps({"agent/**": protection_rule("agent/**")}))
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


# REVIEW-771: same entry points, independent counterexamples and controls.
@pytest.mark.parametrize("pattern,blocked", [
    ("LAND/PROD/job/a1", True), ("MAIN", True), ("AGENT/job", True),
    ("{land/prod/[x,y],release/**}", True),
    (r"{land/prod/[x\,y],release/**}", True),
    (r"{release/\{x\,y\},land/prod/[x,y]}", True),
    ("LAND/STG/job/a1", False), ("LAND/PROD/*", False),
    ("{land/stg/[x,y],release/**}", False),
    (r"{land/stg/[x\]y],release/**}", False),
    (r"{land/stg/\{x\,y\},release/**}", False),
])
@pytest.mark.parametrize("mode", ["--check", "--apply"])
def test_review771_matching_entry_points(fake, pattern, blocked, mode):
    state, calls, run, _ = fake
    rules = {pattern: protection_rule(pattern, enable_push=True), **expected("bifrost-trade-infra")}
    state.write_text(json.dumps(rules))
    result = run(mode)
    assert result.returncode == (1 if blocked else 0), result.stdout + result.stderr
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


@pytest.mark.parametrize("pattern,blocked", [
    ("LAND/PROD/job/a1", True), ("{land/prod/[x,y],release/**}", True),
    ("LAND/STG/job/a1", False), ("{land/stg/[x,y],release/**}", False),
])
def test_review771_combined_matching(fake, tmp_path, pattern, blocked):
    sys.path.insert(0, str(HERE))
    from test_landing_drill_token import setup_fake
    from test_gitea_scripts import GITEA_TOKEN_FIXTURE, run_on_pty
    policy, calls, _, api_env = fake
    policy.write_text(json.dumps({pattern: protection_rule(pattern), **expected("bifrost-trade-infra")}))
    state, env, _, _ = setup_fake(tmp_path, "prod", "")
    result, echoed = run_on_pty(["bash", str(tmp_path / "probe-infra-access.sh"), "--owner", "vision", "prod"],
                               {**api_env, **env}, GITEA_TOKEN_FIXTURE)
    assert result.returncode == (1 if blocked else 0), result.stdout + result.stderr
    assert ("VERDICT FAIL" if blocked else "VERDICT PASS") in result.stdout
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert not (state / "calls").exists()
    assert GITEA_TOKEN_FIXTURE not in result.stdout + result.stderr + echoed


def migration_rules():
    main = expected("bifrost-trade-infra")["main"]
    main.update(push_whitelist_usernames=["vision"], required_approvals=2, enable_status_check=True)
    return {"main": main, "agent/**": protection_rule("agent/**", enable_push=False),
            "release/**": protection_rule("release/**", enable_push=False)}


@pytest.mark.parametrize("fault,methods", [
    ("landing_extra", ["POST"]), ("readback", ["POST"]), ("refuse", ["POST"]),
    ("other_rule", ["POST"]), ("missing_post", ["POST"]), ("extra_rule", ["POST"]),
    ("hardening", ["POST", "PATCH"]), ("keep_agent", ["POST", "PATCH", "DELETE"]),
])
def test_review771_first_bad_readback_stops_all_writes(fake, fault, methods):
    state, calls, run, _ = fake
    state.write_text(json.dumps(migration_rules()))
    result = run("--apply", fault=fault)
    assert result.returncode != 0
    writes = [line.split()[0] for line in calls.read_text().splitlines() if not line.startswith("GET ")]
    assert writes == methods, calls.read_text()
    if methods == ["POST"]:
        assert json.loads(state.read_text())["main"]["push_whitelist_usernames"] == ["vision"]
        assert "agent/**" in json.loads(state.read_text())
    assert "verified actions:" in result.stderr
    assert "current state:" in result.stderr and "--restore" in result.stderr


@pytest.mark.parametrize("initial", [migration_rules(), expected("bifrost-trade-infra")], ids=["migration", "idempotent"])
def test_review771_snapshot_restores_prior_rules(fake, tmp_path, initial):
    state, calls, run, _ = fake
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "before.json"
    result = run("--snapshot", str(snapshot))
    assert result.returncode == 0, result.stderr
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert snapshot.stat().st_mode & 0o777 == 0o600
    saved = snapshot.read_text()
    assert run("--snapshot", str(snapshot)).returncode != 0  # never overwrite the pre-change evidence
    assert snapshot.read_text() == saved
    assert run("--apply").returncode == 0
    assert run("--verify-snapshot", str(snapshot)).returncode == (0 if "agent/**" not in initial else 1)
    assert run("--restore", str(snapshot)).returncode == 0  # dry-run
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    result = run("--restore", str(snapshot), "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    restored = json.loads(state.read_text())
    assert set(restored) == set(initial)
    for name, row in initial.items():
        assert {key: restored[name][key] for key in row} == row
        # Recreating a rule returns the server's explicit optional defaults.
        assert all(value in (False, 0, "", []) for key, value in restored[name].items() if key not in row)
    result = run("--verify-snapshot", str(snapshot))
    assert result.returncode == 0 and "PASS snapshot" in result.stdout
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


def test_review771_runbook_restores_team_tags_and_migration():
    runbook = (HERE.parent.parent / "docs/runbooks/owner-steps-s6-7.md").read_text()
    for required in ("--snapshot", "--restore", "--verify-snapshot", "team-and-tags-before.md",
                     "迁移初态", "幂等重跑初态", "紧急撤权", "创建时间"):
        assert required in runbook
    assert "`agent/**` 继续采用" not in runbook


def test_review771_no_blank_line_at_eof():
    data = (HERE / "protection_policy.py").read_bytes()
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")


@pytest.mark.parametrize("with_agent", [False, True])
def test_platform_existing_protection_requests_unchanged(fake, tmp_path, with_agent):
    state, calls, run, _ = fake
    initial = expected("bifrost-platform")
    initial["main"].update(required_approvals=2, enable_status_check=True)
    if with_agent:
        initial["agent/**"] = protection_rule("agent/**", enable_push=False)
    state.write_text(json.dumps(initial))
    result = run("--apply", repo="bifrost-platform")
    assert result.returncode == 0, result.stderr
    actual_calls, actual_state = calls.read_text(), json.loads(state.read_text())
    # Execute the reviewed commit with the very same transport and input.
    for name in ("protect-repo.sh", "protection_policy.py"):
        old = subprocess.run(["git", "-C", str(HERE), "show", "9e079f2:scripts/gitea/" + name],
                             check=True, capture_output=True, text=True).stdout
        (tmp_path / name).write_text(old)
    state.write_text(json.dumps(initial))
    result = run("--apply", repo="bifrost-platform")
    assert result.returncode == 0, result.stderr
    assert calls.read_text() == actual_calls
    assert json.loads(state.read_text()) == actual_state


@pytest.mark.parametrize("pattern", ["release/[", "{release/*", "release/[a-bc]", "release/[]", "release/\\"])
def test_ambiguous_glob_is_rejected_before_writes(fake, pattern):
    state, calls, run, _ = fake
    state.write_text(json.dumps({pattern: protection_rule(pattern), **expected("bifrost-trade-infra")}))
    for mode in ("--check", "--apply"):
        result = run(mode)
        assert result.returncode == 1 and "STOPPED" in result.stderr
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


def test_snapshot_identity_and_external_changes_refuse_restore(fake, tmp_path):
    state, calls, run, _ = fake
    state.write_text(json.dumps(migration_rules()))
    snapshot = tmp_path / "before.json"
    assert run("--snapshot", str(snapshot)).returncode == 0
    assert run("--apply").returncode == 0
    for target in ("foreign-repo", "bifrost-platform"):
        assert run("--restore", str(snapshot), "--apply", repo=target).returncode != 0
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    rules = json.loads(state.read_text())
    rules["release/**"]["enable_push"] = True
    state.write_text(json.dumps(rules))
    assert run("--restore", str(snapshot), "--apply").returncode != 0
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


def test_snapshot_keeps_effective_priority_and_refuses_reorder(fake, tmp_path):
    state, calls, run, _ = fake
    initial = migration_rules()
    initial["release/private/**"] = protection_rule("release/private/**", enable_push=False)
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "before.json"
    assert run("--snapshot", str(snapshot)).returncode == 0
    assert run("--apply").returncode == 0
    assert run("--restore", str(snapshot), "--apply").returncode == 0
    assert run("--verify-snapshot", str(snapshot)).returncode == 0
    rules = json.loads(state.read_text())
    rules["release/**"] = rules.pop("release/**")
    state.write_text(json.dumps(rules))
    for mode in ("--verify-snapshot", "--restore"):
        assert run(mode, str(snapshot)).returncode != 0
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


def test_auto_snapshot_precedes_first_write_and_failed_readback_can_restore(fake):
    state, calls, run, _ = fake
    initial = migration_rules()
    state.write_text(json.dumps(initial))
    result = run("--apply", fault="landing_extra")
    assert result.returncode != 0
    snapshot = Path(next(line.split(": ", 1)[1] for line in result.stdout.splitlines()
                         if line.startswith("Execution snapshot: ")))
    assert {row["rule_name"]: row for row in json.loads(snapshot.read_text())["rules"]} == initial
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert (snapshot.parent / "current.json").stat().st_mode & 0o777 == 0o600
    assert run("--restore", str(snapshot), "--apply").returncode == 0
    assert run("--verify-snapshot", str(snapshot)).returncode == 0


def test_bad_readback_stops_before_next_repository(fake, tmp_path):
    state, calls, _, env = fake
    state.write_text(json.dumps(migration_rules()))
    result = subprocess.run(["bash", str(tmp_path / "protect-repo.sh"), "--apply", "--owner", "vision",
                             "bifrost-trade-infra", "bifrost-platform"],
                            env={**env, "TEST_API_FAULT": "landing_extra"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "bifrost-platform" not in calls.read_text()
    assert sum(not line.startswith("GET ") for line in calls.read_text().splitlines()) == 1


def test_multiline_api_json_is_verified(fake):
    state, _, run, env = fake
    api = Path(env["TEST_API"])
    api.write_text(api.read_text().replace('json.dumps(list(rules.values()))', 'json.dumps(list(rules.values()), indent=2)'))
    state.write_text(json.dumps(migration_rules()))
    result = run("--apply")
    assert result.returncode == 0, result.stdout + result.stderr


def test_post_defaults_and_patch_timestamp_are_allowed_but_hardening_is_preserved(fake):
    state, _, run, env = fake
    api = Path(env["TEST_API"])
    api.write_text(api.read_text().replace('state.write_text(json.dumps(rules))', '''
    if method == "POST":
        rules[json.loads(body[0])["rule_name"]].update(required_approvals=0, status_check_contexts=None,
                                                      created_at="2026-10-30T00:00:00Z", updated_at="2026-10-30T00:00:00Z")
    if method == "PATCH": rules["main"]["updated_at"] = "2026-10-30T00:00:01Z"
    state.write_text(json.dumps(rules))'''))
    rules = migration_rules()
    rules["main"].update(created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z")
    state.write_text(json.dumps(rules))
    result = run("--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(state.read_text())["main"]["required_approvals"] == 2


# REVIEW-773 A-1: unknown settings must never become permissive restore values.
def hardened_migration_rules():
    rules = migration_rules()
    rules["main"].update(require_signed_commits=True, protected_file_patterns="sensitive/**",
                         status_check_contexts=["ci"])
    return rules


@pytest.mark.parametrize("field", PROTECTION_DEFAULTS)
@pytest.mark.parametrize("fault", ["omit", "invalid"])
@pytest.mark.parametrize("entry", ["explicit", "auto"])
def test_review773_invalid_snapshot_read_stops_before_first_write(fake, tmp_path, field, fault, entry):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "invalid.json"
    options = ("--snapshot", str(snapshot)) if entry == "explicit" else ("--apply",)
    result = run(*options, fault=f"{fault}:{field}")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL" in result.stderr
    assert "Execution snapshot:" not in result.stdout
    assert not snapshot.exists()
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert json.loads(state.read_text()) == initial


@pytest.mark.parametrize("field", PROTECTION_DEFAULTS)
@pytest.mark.parametrize("fault", ["omit", "invalid"])
def test_review773_corrupt_snapshot_refuses_restore_and_verify(fake, tmp_path, field, fault):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    rows = list(hardened_migration_rules().values())
    # Corrupt the removed agent rule too: validation must cover every rule.
    if fault == "omit":
        del rows[1][field]
    else:
        rows[1][field] = {"fixture-secret-must-not-leak": True}
    snapshot = tmp_path / "corrupt.json"
    snapshot.write_text(json.dumps({"version": 1, "org": "bifrost", "repo": "bifrost-trade-infra",
                                    "owner": "vision", "rules": rows}))
    for options in (("--restore", str(snapshot)), ("--restore", str(snapshot), "--apply"),
                    ("--verify-snapshot", str(snapshot))):
        result = run(*options)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "FAIL protection state" in result.stderr and "PASS snapshot" not in result.stdout
        assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
        assert json.loads(state.read_text()) == initial


def test_review773_complete_snapshot_restores_every_protection_field(fake, tmp_path):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    # Non-default values on the deleted/recreated rule exercise every field.
    initial["agent/**"].update({key: True if type(value) is bool else 3 if type(value) is int
                                else ["reviewers"] if isinstance(value, list) else "sensitive/**"
                                for key, value in PROTECTION_DEFAULTS.items()})
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "complete.json"
    saved = run("--snapshot", str(snapshot))
    assert saved.returncode == 0, saved.stderr
    assert run("--apply").returncode == 0
    restored = run("--restore", str(snapshot), "--apply")
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert "PASS snapshot" in restored.stdout
    assert json.loads(state.read_text()) == initial
    post = next(line for line in calls.read_text().splitlines() if line.startswith("POST "))
    assert json.loads(post.split(" ", 2)[2]) == initial["agent/**"]
    checked = run("--verify-snapshot", str(snapshot))
    assert checked.returncode == 0 and "PASS snapshot" in checked.stdout


@pytest.mark.parametrize("field", PROTECTION_DEFAULTS)
def test_review773_restore_readback_checks_every_field(fake, tmp_path, field):
    state, calls, run, env = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "complete.json"
    assert run("--snapshot", str(snapshot)).returncode == 0
    assert run("--apply").returncode == 0
    api = Path(env["TEST_API"])
    default = PROTECTION_DEFAULTS[field]
    wrong = not default if type(default) is bool else 5 if type(default) is int else ["extra"] if isinstance(default, list) else "wrong/**"
    api.write_text(api.read_text().replace('state.write_text(json.dumps(rules))',
        f'if method == "POST": rules["agent/**"][{field!r}] = {wrong!r}\n    state.write_text(json.dumps(rules))'))
    result = run("--restore", str(snapshot), "--apply")
    assert result.returncode != 0 and "FAIL" in result.stderr
    assert "PASS snapshot" not in result.stdout
    assert [line.split()[0] for line in calls.read_text().splitlines() if not line.startswith("GET ")] == ["PATCH", "POST"]
    # Stop at the bad readback, before removing the new landing protection.
    assert "land/prod/**" in json.loads(state.read_text())
    checked = run("--verify-snapshot", str(snapshot))
    assert checked.returncode != 0 and "PASS snapshot" not in checked.stdout


def test_review773_explicit_null_lists_restore_as_empty_lists(fake, tmp_path):
    state, _, run, _ = fake
    initial = hardened_migration_rules()
    initial["agent/**"].update({key: None for key, value in PROTECTION_DEFAULTS.items() if isinstance(value, list)})
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "null-lists.json"
    assert run("--snapshot", str(snapshot)).returncode == 0
    assert run("--apply").returncode == 0
    result = run("--restore", str(snapshot), "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(state.read_text())["agent/**"] == protection_rule("agent/**")
    assert run("--verify-snapshot", str(snapshot)).returncode == 0


@pytest.mark.parametrize("field", PROTECTION_DEFAULTS)
@pytest.mark.parametrize("fault", ["omit", "changed"])
def test_review773_snapshot_verification_requires_every_current_field(fake, tmp_path, field, fault):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "complete.json"
    assert run("--snapshot", str(snapshot)).returncode == 0
    if fault == "omit":
        del initial["agent/**"][field]
    else:
        value = initial["agent/**"][field]
        initial["agent/**"][field] = (not value if type(value) is bool else 5 if type(value) is int
                                      else ["extra"] if isinstance(value, list) else "wrong/**")
    state.write_text(json.dumps(initial))
    result = run("--verify-snapshot", str(snapshot))
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAIL protection state" in result.stderr and "PASS snapshot" not in result.stdout
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())


@pytest.mark.parametrize("kind", ["absent", "directory", "malformed", "null", "unknown_field"])
def test_review773_unreadable_snapshot_refuses_writes(fake, tmp_path, kind):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    snapshot = tmp_path / "unreadable.json"
    if kind == "directory":
        snapshot.mkdir()
    elif kind == "malformed":
        snapshot.write_text('{"fixture-secret-must-not-leak":')
    elif kind == "null":
        snapshot.write_text("null")
    elif kind == "unknown_field":
        assert run("--snapshot", str(snapshot)).returncode == 0
        data = json.loads(snapshot.read_text())
        data["rules"][0]["fixture-secret-must-not-leak"] = True
        snapshot.write_text(json.dumps(data))
    result = run("--restore", str(snapshot), "--apply")
    assert result.returncode != 0
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert json.loads(state.read_text()) == initial


def test_review773_snapshot_save_io_failure_refuses_writes(fake, tmp_path):
    state, calls, run, _ = fake
    initial = hardened_migration_rules()
    state.write_text(json.dumps(initial))
    helper = tmp_path / "protection_state.py"
    helper.write_text(helper.read_text().replace(
        'fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)',
        'raise OSError("fixture-secret-must-not-leak")'))
    result = run("--apply")
    assert result.returncode != 0
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
    assert json.loads(state.read_text()) == initial
