"""Exercise the exact Owner runbook with fake kubectl/curl, no cluster access."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/gitea/s7-owner-apply.sh'
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ['OWNER_FIXTURE'])
call = {'tool': pathlib.Path(sys.argv[0]).name, 'args': args}
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
    print(json.dumps({'full_name': 'bifrost/' + name, 'mirror': bool(os.environ.get('PULL_MIRROR'))}))
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
    mutations = assert_dry_run_pairs(calls)
    role = yaml.safe_load(mutations[0]['role'])
    assert role['rules'][0]['resourceNames'] == ['gitea-ci-reader', 'gitea-git-credentials']
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
