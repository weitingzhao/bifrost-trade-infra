"""Owner installer tests with fake executables only: no socket or cluster."""
import os
from pathlib import Path
import sys
import subprocess

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gitea_scripts import GITEA_TOKEN_FIXTURE, run_on_pty
from test_put_reader_token import FAKE_KUBECTL

HERE = Path(__file__).resolve().parent
FAKE_CURL = '''#!/usr/bin/python3
import json, os, re, sys
from urllib.parse import urlsplit, parse_qs
config=sys.stdin.read()
# Check credential plumbing without logging config/header values.
assert "-q" in sys.argv and "-K" in sys.argv and sys.argv[sys.argv.index("-K")+1]=="-"
secret=re.search(r"[0-9a-f]{40}",config).group()
assert not any(secret in arg for arg in sys.argv)
assert not any("Authorization:" in arg or "fixture-token" in arg or "a"*40 in arg for arg in sys.argv)
with open(os.environ["FAKE_STATE"]+"/http-calls", "a") as log:
    log.write("GET " + sys.argv[-1] + "\\n")
args=sys.argv[1:]; url=args[-1]; path=urlsplit(url).path
mode=os.environ['TEST_MODE']; fault=os.environ.get('TEST_FAULT','')
drill=mode=='drill'; lander=mode=='lander'
user={'drill':'agentrt-landing-stg','lander':'agentrt-lander','ci':'bifrost-ci-reader','stg':'bifrost-platform-reader-stg','prod':'bifrost-platform-reader-prod'}[mode]
repos=['bifrost-platform','bifrost-trade-infra']
def writes(repo):
    return drill or (lander and not (repo=="bifrost-trade-infra" and fault=="infra_readonly"))
code=200; body={}
if path=='/api/v1/user':
    body={'login':'wrong' if fault=='user' else user,'is_admin':fault=='admin'}
elif path=='/api/v1/orgs/bifrost/repos': body=[]
elif path=='/api/v1/repos/search':
    page=int(parse_qs(urlsplit(url).query)['page'][0])
    if fault=='endless' and page>1: page=1
    body={'data':[]}
    if page==1:
        body={'data':[{'full_name':'bifrost/'+r,'permissions':{'admin':fault=='search_admin','push':writes(r),'pull':True}} for r in repos]}
    if page==2 and fault=='extra':
        body={'data':[{'full_name':'bifrost/extra','permissions':{'admin':False,'push':True,'pull':True}}]}
    if page==2 and fault=='bad_page': body={}
    if page==2 and fault=='late_error': code=500
elif path.endswith('/branches/main'):
    repo=path.split('/')[5]
    pushable = fault=='main'
    if lander: pushable = fault!='platform_main_closed' and not (repo=='bifrost-trade-infra' and fault=='infra_main_closed')
    body={'protected':True,'user_can_push':pushable,'user_can_merge':False}
    if fault=='missing_branch': body.pop('protected')
    if fault=='merge': body['user_can_merge']=True
    if fault=='unknown_main': code=500
elif path.startswith('/api/v1/repos/bifrost/'):
    repo=path.split('/')[5]
    body={'permissions':{'admin':False,'push':writes(repo) and fault!='readonly','pull':True}}
    if repo=='bifrost-trade-infra' and fault=='infra_hidden': code=404
    if fault=='missing_permission': body['permissions'].pop('push')
    if fault=='numeric_permission': body['permissions']['admin']=0
    if fault=='reader_write': body['permissions']['push']=True
elif path.endswith('/info/refs'):
    repo=path.split('/')[2].removesuffix('.git')
    if 'receive-pack' in url: code=200 if writes(repo) else 403
    if 'receive-pack' in url and fault=='handshake': code=200
    if 'receive-pack' in url and fault=='unauthenticated': code=401
    if 'upload-pack' in url and fault=='fetch': code=500
else: code=404
if fault=='http': code=500; body={'message':secret}
open(args[args.index('-o')+1],'w').write(json.dumps(body))
print(code,end='')
'''


def setup_fake(tmp_path, mode, fault):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    kubectl = FAKE_KUBECTL.replace("cat >/dev/null; echo 'server dry run'",
                                  "cat >/dev/null; [[ $TEST_FAULT != dryrun ]] || exit 1; echo 'server dry run'")
    for name, script in [("curl", FAKE_CURL), ("kubectl", kubectl)]:
        path = bindir / name
        path.write_text(script.replace("#!/usr/bin/python3", "#!" + sys.executable))
        path.chmod(0o755)
    config = tmp_path / "kubeconfig"
    config.write_text("fixture only")
    primaries = tmp_path / "primaries"
    primaries.write_text("bifrost-platform\nbifrost-trade-infra\n")
    ns, name = {"drill": ("bifrost-platform-stg", "agentrt-landing-drill"),
                "lander": ("bifrost-platform-prod", "agentrt-lander"),
                "ci": ("cicd", "gitea-ci-reader"),
                "stg": ("bifrost-platform-stg", "bifrost-gitea-reader"),
                "prod": ("bifrost-platform-prod", "bifrost-gitea-reader")}[mode]
    env = {**os.environ, "PATH": str(bindir) + ":" + str(Path(sys.executable).parent) + ":" + os.environ["PATH"], "FAKE_STATE": str(state),
           "FAKE_NS": ns, "FAKE_NAME": name, "TEST_MODE": mode, "TEST_FAULT": fault,
           "PUT_TOKEN_KUBECONFIG": str(config), "GITEA_PRIMARIES_FILE": str(primaries),
           "GITEA_PUBLIC_BASE": "http://fixture.invalid/bifrost"}
    return state, env, ns, name


@pytest.mark.parametrize("mode,fault", [("ci", ""), ("stg", ""), ("prod", ""), ("drill", ""), ("lander", ""), *[("drill", f) for f in
                         ("user", "admin", "main", "unknown_main", "readonly", "extra", "search_admin", "http", "dryrun")],
                         *[("lander", f) for f in ("user", "admin", "platform_main_closed", "unknown_main", "readonly",
                                                   "infra_readonly", "infra_hidden", "infra_main_closed", "extra", "search_admin", "http", "dryrun")]])
def test_installer_rejects_excess_permissions_before_any_write(tmp_path, mode, fault):
    state, env, ns, name = setup_fake(tmp_path, mode, fault)
    result, echoed = run_on_pty(["bash", str(HERE / "put-reader-token.sh"), mode], env, GITEA_TOKEN_FIXTURE)
    calls = (state / "calls").read_text()
    assert GITEA_TOKEN_FIXTURE not in result.stdout + result.stderr + echoed + calls
    if fault:
        assert result.returncode != 0
        assert not (state / "secret.yaml").exists()
        assert "create -f -" not in calls and "replace -f -" not in calls
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        doc = yaml.safe_load((state / "secret.yaml").read_text())
        assert doc["metadata"]["namespace"] == ns and doc["metadata"]["name"] == name
        assert doc["stringData"]["password"] == GITEA_TOKEN_FIXTURE
        assert doc["metadata"]["labels"]["bifrost.io/component"] == {"drill": "gitea-landing-drill", "lander": "gitea-lander"}.get(mode, "gitea-reader")
        assert calls.index("--dry-run=server") < calls.index("create -f -")


@pytest.mark.parametrize("mode", ["stg", "prod", "ci", "lander"])
@pytest.mark.parametrize("fault", ["", "infra_hidden", "bad_page", "extra", "search_admin", "http",
                                  "missing_permission", "numeric_permission", "missing_branch", "merge",
                                  "fetch", "late_error", "endless"])
def test_check_only_never_invokes_kubectl(tmp_path, mode, fault):
    state, env, _, _ = setup_fake(tmp_path, mode, fault)
    # Read-only verification does not need a kubeconfig or a Secret.
    Path(env["PUT_TOKEN_KUBECONFIG"]).unlink()
    result, echoed = run_on_pty(["bash", str(HERE / "put-reader-token.sh"), mode, "--check"], env, GITEA_TOKEN_FIXTURE)
    assert not (state / "calls").exists()
    assert not (state / "secret.yaml").exists()
    assert GITEA_TOKEN_FIXTURE not in result.stdout + result.stderr + echoed + (state / "http-calls").read_text()
    assert result.returncode == (1 if fault else 0), result.stdout + result.stderr
    assert ("FAIL" if fault else "PASS identity") in result.stdout + result.stderr


@pytest.mark.parametrize("fault", ["reader_write", "handshake", "unauthenticated"])
def test_reader_refusals(tmp_path, fault):
    state, env, _, _ = setup_fake(tmp_path, "prod", fault)
    result, _ = run_on_pty(["bash", str(HERE / "put-reader-token.sh"), "prod", "--check"], env, GITEA_TOKEN_FIXTURE)
    assert result.returncode == 1
    assert not (state / "calls").exists()


def test_put_refuses_xtrace_and_extra_arguments_before_input(tmp_path):
    state, env, _, _ = setup_fake(tmp_path, "prod", "")
    for args in (["-x", str(HERE / "put-reader-token.sh"), "prod", "--check"],
                 [str(HERE / "put-reader-token.sh"), "prod", "--check", "ignored"]):
        result = subprocess.run(["bash", *args], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        assert not (state / "calls").exists()
        assert not (state / "http-calls").exists()
