"""Owner installer tests with fake executables only: no socket or cluster."""
import os
from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gitea_scripts import GITEA_TOKEN_FIXTURE, run_on_pty
from test_put_reader_token import FAKE_KUBECTL

HERE = Path(__file__).resolve().parent
FAKE_CURL = '''#!/usr/bin/python3
import json, os, sys
from urllib.parse import urlsplit, parse_qs
sys.stdin.read()  # credential config never logged
args=sys.argv[1:]; url=args[-1]; path=urlsplit(url).path
mode=os.environ['TEST_MODE']; fault=os.environ.get('TEST_FAULT','')
drill=mode=='drill'; lander=mode=='lander'
user={'drill':'agentrt-landing-stg','lander':'agentrt-lander','ci':'bifrost-ci-reader','stg':'bifrost-platform-reader-stg','prod':'bifrost-platform-reader-prod'}[mode]
repos=['bifrost-platform','bifrost-trade-infra']
def writes(repo):
    # drill writes both; lander writes platform only (infra too under fault infra_write)
    return drill or (lander and (repo=='bifrost-platform' or fault=='infra_write'))
code=200; body={}
if path=='/api/v1/user':
    body={'login':'wrong' if fault=='user' else user,'is_admin':fault=='admin'}
elif path=='/api/v1/orgs/bifrost/repos': body=[]
elif path=='/api/v1/repos/search':
    page=int(parse_qs(urlsplit(url).query)['page'][0])
    body={'data':[]}
    if page==1:
        body={'data':[{'full_name':'bifrost/'+r,'permissions':{'admin':fault=='search_admin','push':writes(r),'pull':True}} for r in repos]}
    if page==2 and fault=='extra':
        body={'data':[{'full_name':'bifrost/extra','permissions':{'admin':False,'push':True,'pull':True}}]}
elif path.endswith('/branches/main'):
    repo=path.split('/')[5]
    pushable = fault=='main'
    if lander and repo=='bifrost-platform': pushable = fault!='platform_main_closed'
    body={'user_can_push': pushable}
    if fault=='unknown_main': code=500
elif path.startswith('/api/v1/repos/bifrost/'):
    repo=path.split('/')[5]
    body={'permissions':{'admin':False,'push':writes(repo) and fault!='readonly','pull':True}}
    # the lander's team holds platform alone: infra is not visible (or, under infra_visible, read-only)
    if lander and repo=='bifrost-trade-infra' and fault not in ('infra_visible','infra_write'): code=404
elif path.endswith('/info/refs'):
    repo=path.split('/')[2].removesuffix('.git')
    if 'receive-pack' in url: code=200 if writes(repo) else 403
else: code=404
if fault=='http': code=500
open(args[args.index('-o')+1],'w').write(json.dumps(body))
print(code,end='')
'''


@pytest.mark.parametrize("mode,fault", [("ci", ""), ("stg", ""), ("prod", ""), ("drill", ""), ("lander", ""), *[("drill", f) for f in
                         ("user", "admin", "main", "unknown_main", "readonly", "extra", "search_admin", "http", "dryrun")],
                         ("lander", "infra_visible"),
                         *[("lander", f) for f in ("user", "admin", "platform_main_closed", "unknown_main", "readonly",
                                                   "infra_write", "extra", "search_admin", "http", "dryrun")]])
def test_installer_rejects_excess_permissions_before_any_write(tmp_path, mode, fault):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    kubectl = FAKE_KUBECTL.replace("cat >/dev/null; echo 'server dry run'",
                                  "cat >/dev/null; [[ $TEST_FAULT != dryrun ]] || exit 1; echo 'server dry run'")
    for name, script in [("curl", FAKE_CURL), ("kubectl", kubectl)]:
        path = bindir / name
        path.write_text(script)
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
    env = {**os.environ, "PATH": str(bindir) + ":/usr/bin:/bin:/opt/homebrew/bin", "FAKE_STATE": str(state),
           "FAKE_NS": ns, "FAKE_NAME": name, "TEST_MODE": mode, "TEST_FAULT": fault,
           "PUT_TOKEN_KUBECONFIG": str(config), "GITEA_PRIMARIES_FILE": str(primaries)}
    result, echoed = run_on_pty(["bash", str(HERE / "put-reader-token.sh"), mode], env, GITEA_TOKEN_FIXTURE)
    calls = (state / "calls").read_text()
    assert GITEA_TOKEN_FIXTURE not in result.stdout + result.stderr + echoed + calls
    if fault and fault != "infra_visible":
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
