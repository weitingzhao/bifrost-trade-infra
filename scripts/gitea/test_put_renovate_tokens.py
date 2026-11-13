"""scripts/gitea/put-renovate-tokens.sh with stub curl and kubectl, on a pty.

No Gitea, no GitHub, no cluster. The tokens typed here are made up.
"""

from __future__ import annotations

import json
import os
import select
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gitea" / "put-renovate-tokens.sh"
GITEA_TOKEN = "0123456789abcdef0123456789abcdef01234567"
GITHUB_TOKEN = "github_pat_MADEUP_0000"

CURL = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
url = args[-1]
out = args[args.index("-o") + 1]
cfg = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a") as log:
    log.write("curl argv: " + " ".join(args) + "\n")
state = json.load(open(os.environ["STUB_STATE"]))
body, code = {}, "200"
if url.endswith("/api/v1/user"):
    body = {"login": state["login"], "is_admin": state["is_admin"]}
elif "/pulls" in url:
    body = []
elif url.endswith("/api/v1/user/repos?limit=50"):
    body = [{"full_name": n, "permissions": {"push": True}} for n in state["repos"]]
elif "/api/v1/repos/" in url:
    body = {"permissions": {"push": state["push"], "admin": state["repo_admin"], "pull": True}}
elif "api.github.com" in url:
    code = state["github_code"]
json.dump(body, open(out, "w"))
sys.stdout.write(code)
'''

KUBECTL = r'''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write("kubectl argv: " + " ".join(args) + "\n")
if args[-3:] == ["secret", "renovate", "-o"] or (len(args) > 3 and args[2:5] == ["get", "secret", "renovate"] and "name" in args):
    sys.exit(0 if os.path.exists(os.environ["STUB_SECRET"]) else 1)
if "create" in args:
    open(os.environ["STUB_SECRET"], "w").write(sys.stdin.read())
    sys.exit(0)
if args[2:5] == ["get", "secret", "renovate"]:
    print('{"data": {"gitea-token": "x", "github-com-token": "y"}}')
sys.exit(0)
'''


def run(tmp_path, *flags, typed=(GITEA_TOKEN, GITHUB_TOKEN), **state):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, text in (("curl", CURL), ("kubectl", KUBECTL)):
        p = bindir / name
        p.write_text(text)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    full = {"login": "renovate-bot", "is_admin": False, "push": True, "repo_admin": False,
            "repos": ["bifrost/bifrost-trade-infra"], "github_code": "200"}
    full.update(state)
    (tmp_path / "state.json").write_text(json.dumps(full))
    kubeconfig = tmp_path / "admin.yaml"
    kubeconfig.write_text("stub\n")
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", STUB_LOG=str(tmp_path / "log"),
               STUB_STATE=str(tmp_path / "state.json"), STUB_SECRET=str(tmp_path / "secret.json"),
               PUT_TOKEN_KUBECONFIG=str(kubeconfig))
    # Same way as run_on_pty in test_gitea_scripts.py, for two prompts: bash's
    # read -s flushes pending input when it turns echo off, so each token is
    # typed only after its prompt is out.
    master, slave = os.openpty()
    proc = subprocess.Popen(["bash", str(SCRIPT), *flags], stdin=slave, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, cwd=tmp_path)
    os.close(slave)
    err, answered, deadline = b"", 0, time.monotonic() + 30
    try:
        while time.monotonic() < deadline and answered < len(typed):
            ready, _, _ = select.select([proc.stderr], [], [], 0.5)
            if ready:
                chunk = os.read(proc.stderr.fileno(), 4096)
                if not chunk:
                    break
                err += chunk
            elif proc.poll() is not None:
                break
            if err.count(b"(input hidden): ") > answered:
                time.sleep(0.3)
                os.write(master, (typed[answered] + "\n").encode())
                answered += 1
        stdout, rest = proc.communicate(timeout=30)
    finally:
        os.close(master)
    out = stdout.decode() + (err + rest).decode()
    log = (tmp_path / "log").read_text() if (tmp_path / "log").exists() else ""
    return proc.returncode, out, log, tmp_path / "secret.json"


def test_check_passes_and_writes_nothing(tmp_path):
    code, out, log, secret = run(tmp_path, "--check")
    assert code == 0, out
    assert "both tokens pass. Nothing was written." in out
    assert not secret.exists() and "kubectl" not in log


def test_create_sends_both_tokens_on_stdin_and_never_on_a_command_line(tmp_path):
    code, out, log, secret = run(tmp_path)
    assert code == 0, out
    made = json.loads(secret.read_text())
    assert made["metadata"] == {"name": "renovate", "namespace": "cicd"}
    assert made["stringData"] == {"gitea-token": GITEA_TOKEN, "github-com-token": GITHUB_TOKEN}
    assert GITEA_TOKEN not in log and GITHUB_TOKEN not in log, "a token reached an argv"
    assert GITEA_TOKEN not in out and GITHUB_TOKEN not in out, "a token was printed"
    assert "keys: gitea-token github-com-token" in out


def test_an_existing_secret_is_not_replaced(tmp_path):
    (tmp_path / "secret.json").write_text("{}")
    code, out, _, secret = run(tmp_path)
    assert code == 1 and "already exists" in out and "Nothing was written." in out
    assert secret.read_text() == "{}"


def refused(tmp_path, needle, **state):
    code, out, _, secret = run(tmp_path, **state)
    assert code == 1 and needle in out and "Nothing was written." in out, out
    assert not secret.exists()


def test_a_token_of_another_account_is_refused(tmp_path):
    refused(tmp_path, "belongs to 'bifrost-mbp'", login="bifrost-mbp")


def test_an_admin_bot_is_refused(tmp_path):
    refused(tmp_path, "is a Gitea admin", is_admin=True)


def test_a_bot_that_cannot_push_is_refused(tmp_path):
    refused(tmp_path, "cannot push branches", push=False)


def test_a_bot_that_administers_the_repository_is_refused(tmp_path):
    refused(tmp_path, "administers", repo_admin=True)


def test_a_bot_with_write_on_a_second_repository_is_refused(tmp_path):
    refused(tmp_path, "can also push to: bifrost/bifrost-platform",
            repos=["bifrost/bifrost-trade-infra", "bifrost/bifrost-platform"])


def test_a_github_token_that_is_not_accepted_is_refused(tmp_path):
    refused(tmp_path, "GitHub GET a public release -> HTTP 401", github_code="401")


def test_a_malformed_gitea_token_is_refused_before_any_request(tmp_path):
    code, out, log, secret = run(tmp_path, typed=("not-a-token", GITHUB_TOKEN))
    assert code == 1 and "not a Gitea token" in out and "curl" not in log and not secret.exists()


def test_without_a_terminal_it_refuses():
    proc = subprocess.run(["bash", str(SCRIPT), "--check"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert proc.returncode == 1 and "not a terminal" in proc.stderr
