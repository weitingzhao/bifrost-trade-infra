"""Run protect-repo's shell/JSON/comparison against a file-backed API, no sockets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parent


@pytest.mark.parametrize("repo,teams", [
    ("bifrost-platform", []), ("bifrost-trade-infra", []), ("bifrost-ui", ["maintainers"]),
])
def test_main_baseline_and_existing_rule_drift(tmp_path, repo, teams):
    # Copy the script verbatim; replace only its sourced transport library.
    shutil.copyfile(HERE / "protect-repo.sh", tmp_path / "protect-repo.sh")
    (tmp_path / "lib.sh").write_text('''set -euo pipefail
GITEA_ORG=bifrost
gitea_die() { echo "$*" >&2; exit 1; }
gitea_connect() { :; }
gitea_api() { "$TEST_PYTHON" "$TEST_API" "$@"; }
''')
    api = tmp_path / "api.py"
    api.write_text('''import json, os, sys
from pathlib import Path
state = Path(os.environ["TEST_STATE"])
rules = json.loads(state.read_text())
method, path, *body = sys.argv[1:]
with open(os.environ["TEST_CALLS"], "a") as log:
    log.write(method + " " + path + "\\n")
if method == "GET":
    print(json.dumps(rules["main"] if path.endswith("/main") else list(rules.values())))
elif method == "POST" and path.endswith("/branch_protections"):
    assert "main" not in rules
    rules["main"] = json.loads(body[0])
    state.write_text(json.dumps(rules))
    print(json.dumps(rules["main"]))
else:
    raise AssertionError("unexpected mutation: " + method + " " + path)
''')
    state, calls = tmp_path / "state.json", tmp_path / "calls"
    state.write_text("{}")
    env = {**os.environ, "TEST_PYTHON": sys.executable, "TEST_API": str(api),
           "TEST_STATE": str(state), "TEST_CALLS": str(calls)}

    def run():
        return subprocess.run(["bash", str(tmp_path / "protect-repo.sh"), "--owner", "vision", repo],
                              env=env, capture_output=True, text=True)

    first = run()
    assert first.returncode == 0, first.stdout + first.stderr
    rule = json.loads(state.read_text())["main"]
    for operation in ("push", "merge"):
        assert rule[f"enable_{operation}_whitelist"] is True
        assert rule[f"{operation}_whitelist_usernames"] == ["vision"]
        assert rule[f"{operation}_whitelist_teams"] == teams
    assert rule["push_whitelist_deploy_keys"] is False
    assert "allowed: " + ("team maintainers and " if teams else "") + "vision" in first.stdout
    calls.write_text("")
    second = run()
    assert second.returncode == 0, second.stdout + second.stderr
    assert "there as the baseline" in second.stdout
    assert all(line.startswith("GET ") for line in calls.read_text().splitlines())

    # A stale wider whitelist on either operation must be reported, never repaired implicitly.
    if not teams:
        for operation in ("push", "merge"):
            wider = {**rule, f"{operation}_whitelist_teams": ["maintainers"]}
            state.write_text(json.dumps({"main": wider}))
            calls.write_text("")
            result = run()
            assert result.returncode == 1
            assert f"{operation}_whitelist_teams" in result.stdout
            assert json.loads(state.read_text())["main"] == wider
            assert all(line.startswith("GET ") for line in calls.read_text().splitlines())
