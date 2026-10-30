"""Execute Tekton scripts against local Git and a fake ls-remote, never a cluster."""
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
S = runpy.run_path(str(HERE / 'test_doc_policy.py'))
put, commit, git = S['put'], S['commit_fixture'], S['command']


def script(name, tmp_path):
    task = yaml.safe_load((ROOT / 'k8s/cicd/tekton' / f'task-ci-infra-{name}.yaml').read_text())
    body = task['spec']['steps'][0]['script']
    results = tmp_path / 'results'
    results.mkdir(exist_ok=True)
    for row in task['spec']['results']:
        body = body.replace('$(results.' + row['name'] + '.path)', str(results / row['name']))
    return body.replace('$(workspaces.source.path)', str(tmp_path / 'ws'))


def fixture_env(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    # timeout's bound is asserted separately; replacing it avoids a GNU-only
    # dependency on the macOS host while executing the exact Task body.
    timeout = bindir / 'timeout'
    timeout.write_text('#!/bin/sh\n[ "$1" = 30 ] || exit 91\nshift\nexec "$@"\n')
    timeout.chmod(0o755)
    return dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'],
                GIT_USERNAME='fixture-reader', GIT_PASSWORD='fixture-password')


def test_resolve_pinned_invalid_and_landing_missing(tmp_path):
    env = fixture_env(tmp_path)
    body = script('resolve', tmp_path)
    for value, purpose, ok in [('a' * 40, 'landing', True), ('main', 'push', False),
                               ('0' * 40, 'landing', False), ('', 'landing', False)]:
        result = subprocess.run(['bash'], input=body, text=True, capture_output=True,
                                env=dict(env, PLATFORM_REVISION=value, PURPOSE=purpose), check=False)
        assert (result.returncode == 0) == ok
        assert 'fixture-password' not in result.stdout + result.stderr
    assert (tmp_path / 'results/platform-commit').read_text() == 'a' * 40


def test_resolve_two_retries_then_success_or_failure(tmp_path):
    env = fixture_env(tmp_path)
    counter = tmp_path / 'attempts'
    fake = tmp_path / 'bin/git'
    fake.write_text('''#!/bin/sh
n=0
[ ! -f "$COUNTER" ] || n=$(cat "$COUNTER")
n=$((n+1))
printf '%s' "$n" > "$COUNTER"
[ "$n" -ge 3 ] && [ "$SUCCESS" = yes ] || exit 1
printf '%s\\trefs/heads/main\\n' "$RESOLVED"
''')
    fake.chmod(0o755)
    body = script('resolve', tmp_path)
    for success in ('yes', 'no'):
        counter.unlink(missing_ok=True)
        result = subprocess.run(['bash'], input=body, text=True, capture_output=True, check=False,
                                env=dict(env, COUNTER=str(counter), SUCCESS=success, RESOLVED='b'*40,
                                         PLATFORM_REVISION='', PURPOSE='push'))
        assert counter.read_text() == '3'
        assert (result.returncode == 0) == (success == 'yes')
        assert 'fixture-password' not in result.stdout + result.stderr


@pytest.mark.parametrize('base_kind', ['parent', 'mismatch', 'no_base', 'merge', 'push_two', 'push_one', 'push_missing', 'push_merge'])
def test_clone_depth_identity_and_base_results(tmp_path, base_kind):
    env = fixture_env(tmp_path)
    source = tmp_path / 'sources'
    source.mkdir()
    for name in ('bifrost-trade-infra', 'bifrost-platform'):
        repo = source / name
        repo.mkdir()
        git(repo, 'init', '-q')
        put(repo, 'first', 'one\n')
        head = commit(repo)
        if name == 'bifrost-trade-infra':
            first = head
            put(repo, 'second', 'two\n')
            parent = commit(repo)
            put(repo, 'third', 'three\n')
            revision = commit(repo)
            if base_kind in ('merge', 'push_merge'):
                git(repo, 'checkout', '-b', 'side', parent)
                put(repo, 'side', 'side\n')
                commit(repo)
                git(repo, 'checkout', '--detach', revision)
                git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'merge', '--no-ff', 'side', '-m', 'Merge fixture')
                revision = git(repo, 'rev-parse', 'HEAD')
        else:
            platform_revision = head
    real_git = shutil.which('git')
    fake = tmp_path / 'bin/git'
    fake.write_text('''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
for i, arg in enumerate(args):
    if arg.startswith('http://gitea.cicd.svc.cluster.local:3000/bifrost/'):
        name = arg.rsplit('/', 1)[1].removesuffix('.git')
        args[i] = 'file://' + os.environ['SOURCE'] + '/' + name
os.execv(os.environ['REAL_GIT'], [os.environ['REAL_GIT'], *args])
''')
    fake.chmod(0o755)
    base = first if base_kind in ('mismatch', 'push_two', 'push_merge') else parent
    if base_kind == 'no_base':
        base = '0' * 40
    if base_kind == 'push_missing':
        base = 'f' * 40
    result = subprocess.run(['bash'], input=script('clone', tmp_path), text=True, capture_output=True, check=False,
                            env=dict(env, SOURCE=str(source), REAL_GIT=real_git, REVISION=revision, BASE=base,
                                     PLATFORM_REVISION=platform_revision,
                                     PURPOSE='push' if base_kind == 'no_base' or base_kind.startswith('push_') else 'landing'))
    assert 'fixture-password' not in result.stdout + result.stderr
    if base_kind in ('mismatch', 'merge'):
        assert result.returncode != 0 and 'base_mismatch' in result.stderr
        return
    if base_kind == 'push_missing':
        assert result.returncode != 0 and 'base_fetch_failed' in result.stderr
        return
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'results/commit').read_text() == revision
    assert (tmp_path / 'results/platform-commit').read_text() == platform_revision
    assert (tmp_path / 'results/base-commit').read_text() == ('' if base_kind == 'no_base' else base)
    assert git(tmp_path / 'ws/cand/bifrost-platform', 'rev-list', '--count', 'HEAD') == '1'
    assert git(tmp_path / 'ws/cand/bifrost-trade-infra', 'rev-list', '--count', 'HEAD') == ('3' if base_kind == 'push_merge' else '2')
    if base_kind == 'parent':
        assert git(tmp_path / 'ws/base/bifrost-trade-infra', 'rev-parse', 'HEAD') == parent
