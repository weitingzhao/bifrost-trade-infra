"""Real tracked trees and exact clone Task; no stand-in static checkers."""
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

T = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_transport.py')))
ROOT, git, put, commit = T['ROOT'], T['git'], T['put'], T['commit']


@pytest.fixture(scope='module')
def two_repo_clone(tmp_path_factory):
    temp = tmp_path_factory.mktemp('review777-two-repos')
    source = temp / 'sources'
    source.mkdir()
    infra = source / 'bifrost-trade-infra'
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(ROOT), str(infra)], check=True)
    # Include current tracked edits before commit, so this also verifies the
    # proposed fix. Baseline red runs use the unmodified 0e90252 tree.
    changed = subprocess.check_output(['git', '-C', str(ROOT), 'diff', 'HEAD', '--name-only', '-z'])
    for raw in filter(None, changed.split(b'\0')):
        name = os.fsdecode(raw)
        put(infra, name, (ROOT / name).read_bytes())
    if changed:
        commit(infra)
    put(infra, 'review777-baseline.txt', 'fixed source snapshot\n')
    base = commit(infra)
    put(infra, 'review777-candidate.txt', 'single-parent candidate\n')
    revision = commit(infra)
    platform = next(p for p in (ROOT.parent / 'platform', ROOT.parent / 'bifrost-platform') if (p / '.git').exists())
    psha = git(platform, 'rev-parse', 'HEAD')
    subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(platform), str(source / 'bifrost-platform')], check=True)
    git(source / 'bifrost-platform', 'checkout', '--detach', psha)
    env = T['fixture_env'](temp)
    body = T['script']('clone', temp).replace('http://gitea.cicd.svc.cluster.local:3000/bifrost/', source.as_uri() + '/')
    # The source URL ends in .git; aliases stay entirely inside the temp tree.
    for name in ('bifrost-trade-infra', 'bifrost-platform'):
        (source / (name + '.git')).symlink_to(name, target_is_directory=True)
    result = subprocess.run(['bash'], input=body, text=True, capture_output=True, check=False,
                            env=dict(env, REVISION=revision, BASE=base, PLATFORM_REVISION=psha, PURPOSE='landing'))
    assert result.returncode == 0, result.stderr
    return temp / 'ws', revision, base, psha


def test_b04_real_freeze_chain(two_repo_clone):
    ws, *_ = two_repo_clone
    repo = ws / 'cand/bifrost-trade-infra'
    code = "import runpy; m=runpy.run_path('scripts/release/freeze_chain.py'); failures=m['violations_under'](m['TEKTON']); print('\\n'.join(failures)); raise SystemExit(bool(failures))"
    result = subprocess.run([sys.executable, '-I', '-c', code], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_b05_real_statics_in_declared_layout(two_repo_clone):
    ws, revision, base, psha = two_repo_clone
    assert not (ws / 'cand/bifrost-platform-plugin-flex-query').exists()
    env = dict(os.environ, BIFROST_WORKSPACE=str(ws / 'cand'), FLEX_QUERY_ROOT='/absent-review777-flex')
    command = ['bash', str(ws / 'base/bifrost-trade-infra/scripts/landing/ci-infra.sh'),
               '--stage', 'statics', '--cand', str(ws / 'cand'), '--base', str(ws / 'base'),
               '--revision', revision, '--base-sha', base, '--platform-revision', psha]
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    print('COMMAND:', ' '.join(command))
    print(result.stdout, result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'scope=infra' in result.stdout
    # The full, cross-repository entry still refuses a missing required repo.
    full = subprocess.run([sys.executable, '-I', str(ws / 'cand/bifrost-trade-infra/scripts/check-release-chain.py')],
                          env=env, capture_output=True, text=True, check=False)
    assert full.returncode == 1
    assert 'bifrost-build-flex-query: pipeline YAML not found' in full.stdout
