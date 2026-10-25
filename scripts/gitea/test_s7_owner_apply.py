"""Exercise the exact Owner runbook with fake kubectl/curl, no cluster access."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/gitea/s7-owner-apply.sh'
USER = 'fixture-ci-reader'
TOKEN = 'fixture-secret-never-in-curl-argv-or-env'
AUTH = base64.b64encode(f'{USER}:{TOKEN}'.encode()).decode()
FAKE = r'''#!/usr/bin/env python3
import base64, json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ['OWNER_FIXTURE'])
call = {'tool': pathlib.Path(sys.argv[0]).name, 'args': args}
if call['tool'] == 'curl':
    call['stdin'] = sys.stdin.read()
    token = 'fixture-secret-never-in-curl-argv-or-env'
    auth = base64.b64encode(('fixture-ci-reader:' + token).encode()).decode()
    call['credential_in_env'] = any(value in json.dumps(dict(os.environ)) for value in
                                    (token, auth, base64.b64encode(token.encode()).decode()))
    work = pathlib.Path(args[args.index('--output') + 1]).parent
    call['work_mode'] = work.stat().st_mode & 0o777
    call['config_mode'] = (work / 'reader.curl').stat().st_mode & 0o777
if '--patch-file' in args:
    call['patch'] = json.loads(pathlib.Path(args[args.index('--patch-file') + 1]).read_text())
if '-f' in args and args[args.index('-f') + 1].endswith('applier-read.yaml'):
    call['role'] = pathlib.Path(args[args.index('-f') + 1]).read_text()
with (root / 'calls').open('a') as stream:
    stream.write(json.dumps(call) + '\n')
if os.environ.get('FAIL_MATCH') and os.environ['FAIL_MATCH'] in str(args):
    sys.exit(1)
if call['tool'] == 'curl':
    name = args[-1].rsplit('/', 1)[1]
    code = os.environ.get('HTTP_STATUS', '200') if name == os.environ.get('FAIL_REPO', 'bifrost-platform') else '200'
    body = json.dumps({'full_name': 'bifrost/' + name, 'mirror': bool(os.environ.get('PULL_MIRROR'))})
    pathlib.Path(args[args.index('--output') + 1]).write_text(os.environ.get('BAD_BODY', body))
    print(code, end='')
    sys.exit(int(os.environ.get('CURL_EXIT', '0')))
elif args[2:5] == ['get', 'secret', 'gitea-ci-reader']:
    data = {key: base64.b64encode(value.encode()).decode() for key, value in
            [('username', 'fixture-ci-reader'), ('password', 'fixture-secret-never-in-curl-argv-or-env')]}
    print(json.dumps({'data': data}))
elif args[2:4] == ['get', 'secrets']:
    assert args[4] == '-o' and args[5].startswith('go-template=')
    assert '.data' not in args[5]
    print('unknown-git-secret\ttekton.dev/git-17=http://gitea\t')
    print('unlinked-git-secret\ttekton.dev/git-3=http://other\t')
    print('unrelated-registry\tregistry.example/host=registry\t')
elif args[2:4] == ['get', 'serviceaccounts']:
    print(json.dumps({'items': [
        {'metadata': {'name': 'build'}, 'secrets': [{'name': 'unrelated-registry'},
            {'name': 'unknown-git-secret'}, {'name': 'gitea-git-credentials'}, {'name': 'gitea-ci-reader'}],
         'imagePullSecrets': [{'name': 'unknown-git-secret'}, {'name': 'unrelated-registry'}]},
        {'metadata': {'name': 'second'}, 'secrets': [{'name': 'unknown-git-secret'}]},
        {'metadata': {'name': 'no-links'}}]}))
'''


@pytest.fixture
def owner_fixture(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name in ('kubectl', 'curl'):
        path = bindir / name
        path.write_text(FAKE)
        path.chmod(0o755)
    tmp = tmp_path / 'tmp'
    tmp.mkdir()
    env = {**os.environ, 'PATH': str(bindir) + ':' + str(Path(sys.executable).parent) + ':' + os.environ['PATH'],
           'TMPDIR': str(tmp), 'OWNER_FIXTURE': str(tmp_path)}
    return tmp_path, env


def run(fixture, **extra):
    root, env = fixture
    # Models pasting a bash invocation into a shell: child failure cannot exit it.
    result = subprocess.run(['bash', '-c', 'bash "$1"; code=$?; echo SHELL_ALIVE; exit "$code"', '_', str(SCRIPT)],
                            env={**env, **extra}, capture_output=True, text=True)
    calls = [json.loads(line) for line in (root / 'calls').read_text().splitlines()]
    assert 'SHELL_ALIVE' in result.stdout
    assert list((root / 'tmp').iterdir()) == []  # EXIT trap also on failure.
    for secret in (TOKEN, AUTH, base64.b64encode(TOKEN.encode()).decode()):
        assert secret not in result.stdout + result.stderr
        for call in calls:
            assert secret not in json.dumps(call['args'])
            assert not call.get('credential_in_env', False)
    for call in calls:
        if call['tool'] == 'curl':
            assert call['stdin'] == f'header = "Authorization: Basic {AUTH}"\n'
            assert call['args'][0] == '-q'  # Ignore ~/.curlrc (verbose/redirect settings).
            assert call['args'][call['args'].index('--config') + 1] == '-'
            assert call['args'][call['args'].index('--max-redirs') + 1] == '0'
            assert call['args'][call['args'].index('--noproxy') + 1] == '*'
            assert '--location' not in call['args'] and '-L' not in call['args']
            assert call['args'][-1].startswith('http://192.168.10.73:30300/api/v1/repos/bifrost/')
            assert call['work_mode'] == 0o700
            assert call['config_mode'] == 0o600
    return result, calls


def assert_dry_run_pairs(calls):
    mutations = [c for c in calls if c['tool'] == 'kubectl' and c['args'][2] in ('apply', 'patch')]
    assert len(mutations) % 2 == 0
    for dry, real in zip(mutations[::2], mutations[1::2]):
        assert '--dry-run=server' in dry['args']
        assert [a for a in dry['args'] if a != '--dry-run=server'] == real['args']
    return mutations


def test_inventory_order_transition_and_all_links(owner_fixture):
    result, calls = run(owner_fixture)
    assert result.returncode == 0, result.stderr
    assert calls[0]['args'][2:4] == ['get', 'secrets']
    assert calls[1]['args'][2:4] == ['get', 'serviceaccounts']
    assert 'unlinked-git-secret' in result.stdout and 'tekton.dev/git-3' in result.stdout
    assert 'SA link: second secrets unknown-git-secret' in result.stdout
    reads = [c for c in calls if c['tool'] == 'curl']
    assert len(reads) == 11
    primaries = [line for line in (ROOT / 'agent-config/gitea-primary.txt').read_text().splitlines()
                 if line and not line.startswith('#')]
    assert [c['args'][-1].rsplit('/', 1)[1] for c in reads] == primaries
    assert result.stdout.count(': mirror:false') == 11
    reader_calls = [c for c in calls if c['args'][2:5] == ['get', 'secret', 'gitea-ci-reader']]
    assert len(reader_calls) == 1
    mutations = assert_dry_run_pairs(calls)
    assert calls.index(reads[-1]) < calls.index(mutations[0])
    role = yaml.safe_load(mutations[0]['role'])
    assert role['rules'][0]['resourceNames'] == ['gitea-ci-reader', 'gitea-git-credentials']
    files = [c['args'][c['args'].index('-f') + 1] for c in mutations[::2] if '-f' in c['args']]
    expected = [
        'task-code-health', 'task-deliver-platform', 'task-deliver-research', 'task-deliver-stg',
        'task-git-clone-gitea', 'task-gitea-mirror-sync', 'task-refresh-dockerfile-cms',
        'task-research-lint-test', 'task-verify-prod-deliver', 'task-verify-stg-deliver',
        'apply-manifest/pipeline', 'pipeline-ci-python', 'pipeline-deliver-platform-prod',
        'pipeline-deliver-prod', 'pipeline-deliver-research',
    ]
    assert Path(files[0]).name == 'applier-read.yaml'
    assert files[1:] == [f'k8s/cicd/tekton/{name}.yaml' for name in expected]
    kinds = [doc['kind'] for path in files[1:] for doc in yaml.safe_load_all((ROOT / path).read_text())
             if doc and doc['kind'] in ('Task', 'Pipeline')]
    assert kinds == ['Task'] * 13 + ['Pipeline'] * 5  # All Tasks before any Pipeline.
    bundles = [c['args'][c['args'].index('-k') + 1] for c in mutations[::2] if '-k' in c['args']]
    assert bundles == ['k8s/cicd/github-sync']
    assert mutations[-6]['args'][-1] == 'k8s/cicd/github-sync'
    assert all(c['args'][2] == 'patch' for c in mutations[-4:])
    patches = [c['patch'] for c in mutations if c['args'][2:5] == ['patch', 'serviceaccount', 'build']]
    assert len(patches) == 2
    assert [op['value'] for op in patches[0] if op['op'] == 'test'] == [
        'gitea-ci-reader', 'gitea-git-credentials', 'unknown-git-secret', 'unknown-git-secret']
    assert [op['path'] for op in patches[0] if op['op'] == 'remove'] == [
        '/secrets/3', '/secrets/2', '/secrets/1', '/imagePullSecrets/0']
    first_temp = mutations[0]['args'][-1]
    root, _ = owner_fixture
    (root / 'calls').unlink()
    _, again = run(owner_fixture)
    assert assert_dry_run_pairs(again)[0]['args'][-1] != first_temp


@pytest.mark.parametrize('fail', ['get\', \'secrets', 'applier-read.yaml', 'task-git-clone-gitea.yaml',
                                 'apply-manifest/pipeline.yaml', 'github-sync', 'patch'])
def test_failed_step_stops_without_next_mutation(owner_fixture, fail):
    result, calls = run(owner_fixture, FAIL_MATCH=fail)
    assert result.returncode != 0
    assert fail in str(calls[-1]['args'])
    if calls[-1]['args'][2] in ('apply', 'patch'):
        assert '--dry-run=server' in calls[-1]['args']


def test_pull_mirror_stops_before_apply(owner_fixture):
    result, calls = run(owner_fixture, PULL_MIRROR='1')
    assert result.returncode != 0
    assert not any(c['tool'] == 'kubectl' and c['args'][2] in ('apply', 'patch') for c in calls)


@pytest.mark.parametrize('status', ['404', '401', '302', '500'])
def test_unreadable_repo_stops_cleanly_before_any_change(owner_fixture, status):
    result, calls = run(owner_fixture, HTTP_STATUS=status, FAIL_REPO='bifrost-research')
    assert result.returncode != 0
    assert f'STOP: cannot read repository bifrost-research (HTTP {status})' in result.stderr
    assert 'Traceback' not in result.stderr
    assert len([c for c in calls if c['tool'] == 'curl']) == 11
    assert not any(c['tool'] == 'kubectl' and c['args'][2] in ('apply', 'patch') for c in calls)


@pytest.mark.parametrize('extra, message', [
    ({'CURL_EXIT': '7', 'HTTP_STATUS': '000'}, 'HTTP 000; transport failure'),
    ({'BAD_BODY': '<html>sign in</html>'}, 'HTTP 200'),
    ({'BAD_BODY': '[]'}, 'HTTP 200'),
])
def test_transport_or_invalid_metadata_stops_cleanly(owner_fixture, extra, message):
    result, calls = run(owner_fixture, **extra)
    assert result.returncode != 0
    assert 'bifrost-platform' in result.stderr and message in result.stderr
    assert 'Traceback' not in result.stderr
    assert not any(c['tool'] == 'kubectl' and c['args'][2] in ('apply', 'patch') for c in calls)
