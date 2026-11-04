"""S1-5 review round 2 (R2-M1): what a launched executor's environment keeps and loses.

python3 -m pytest -q scripts/agent-host/tests/test_collector_env.py
Every value is synthetic; no credential or kubeconfig is read.
"""

import importlib.util
import json
import os
import subprocess

from collector_fakes import AGENT_HOST, HEARTBEAT

# Named in the review, found in this repository (.env.example, manifests, scripts), and their usual kin.
CREDENTIALS = [
    "POLYGON_API_KEY", "MASSIVE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "CURSOR_API_KEY", "ANTHROPIC_API_KEY",
    "REDISCLI_AUTH", "PROMETHEUS_AUTH", "DOCKER_AUTH_CONFIG", "SSH_AUTH_SOCK", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "KUBECONFIG", "PGPASSFILE", "PGPASSWORD", "POSTGRES_PASSWORD", "REDIS_IB_PASSWORD", "GOLDEN_SOURCE_PASSWORD",
    "MINIO_CREDENTIALS", "IB_FLEX_HOST_TOKEN", "OPS_ADMIN_TOKEN", "PLATFORM_PROD_OPERATOR_TOKEN", "PLATFORM_REPORTER_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN", "AGENTRT_COORDINATOR_AGENTD_TOKEN", "AGENTRT_COORDINATOR_PROPOSER_TOKEN",
    "HANDIN_AGENTD_TOKEN_FILE", "HANDIN_HOST", "BIFROST_DISPATCH_TOKEN", "SESSION_COOKIE", "SOME_SECRET",
]
CONFIG = [
    "PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL", "USER", "CODEX_HOME", "XAUTHORITY",
    "PLATFORM_HEARTBEAT_URL", "PLATFORM_LINEAGE_URL", "PLATFORM_AGENTRT_URL", "BIFROST_HOME_OVERRIDE", "BIFROST_HOST_ID",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "NODE_OPTIONS", "GIT_AUTHOR_NAME", "KEYCHAIN_PROFILE", "MONKEY",
]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, AGENT_HOST / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic():
    return {name: f"synthetic-{i}" for i, name in enumerate(CREDENTIALS + CONFIG)}


def test_codex_loses_every_credential_and_keeps_every_setting_with_its_value():
    env = synthetic()
    out = load("dispatch_codex_env", "dispatch-codex.py").child_env(env)
    assert [n for n in CREDENTIALS if n in out] == []
    assert {n: out.get(n) for n in CONFIG} == {n: env[n] for n in CONFIG}
    assert set(out) == set(CONFIG), "nothing else is added or lost"


def test_claude_loses_the_coordinator_credentials_and_keeps_what_its_hooks_read():
    env = synthetic()
    env["PLATFORM_COLLECTOR_TOKEN"] = "synthetic-collector"
    out = load("dispatch_claude_env", "dispatch-claude.py").child_env(env)
    kept = {"PLATFORM_COLLECTOR_TOKEN", "PLATFORM_REPORTER_TOKEN"}
    assert [n for n in CREDENTIALS if n in out and n not in kept] == []
    assert {n: out[n] for n in kept} == {n: env[n] for n in kept}
    assert {n: out.get(n) for n in CONFIG} == {n: env[n] for n in CONFIG}


def test_the_heartbeat_still_aims_where_it_was_told_after_the_filter(tmp_path):
    """The review's probe: PLATFORM_HEARTBEAT_URL must survive, or beats go to the default platform."""
    code = "console.log(JSON.stringify(require(" + json.dumps(str(HEARTBEAT)) + ").baseURL()))"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "BIFROST_HOME_OVERRIDE": str(tmp_path), "PLATFORM_HEARTBEAT_URL": "http://stg.invalid"}

    def aim(e):
        p = subprocess.run(["node", "-e", code], env=e, capture_output=True, text=True, timeout=10, check=True)
        return json.loads(p.stdout)

    for module in (load("dc", "dispatch-codex.py"), load("dcl", "dispatch-claude.py")):
        assert aim(module.child_env(env)) == aim(env) == "http://stg.invalid"
