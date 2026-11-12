"""Review 779: real Git decisions, M0-exported CLI, and push endpoint limits."""
import runpy
import subprocess
from pathlib import Path

import pytest

T = runpy.run_path(str(Path(__file__).with_name('test_review777_policy.py')))
X = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_transport.py')))
ci_workspace = T['ci_workspace']
git, put, commit = T['git'], T['put'], T['commit']
DOC, invoke_stage = T['DOC'], T['invoke_stage']


@pytest.mark.parametrize('name,violation,stage,error', [
    (DOC, b'not text \0\n', 'doc-policy', 'doc_content'),
])
def test_b01_push_checks_endpoints_not_restored_intermediate_commit(ci_workspace, tmp_path, name, violation, stage, error):
    args, infra, platform = ci_workspace
    args.purpose = 'push'
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, name, violation)
    bad = args.revision = commit(infra)
    result = invoke_stage(args, stage)
    assert result.returncode == 1 and error in result.stderr, result.stdout + result.stderr
    put(infra, name, 'Restored\n')
    commit(infra)
    put(infra, DOC, 'Final ordinary text\n')
    args.revision = commit(infra)
    # Execute the real shallow clone Task. Only redirect the remote to local
    # Git and replace the host's missing timeout binary, as in transport tests.
    source = tmp_path / 'sources'
    source.mkdir()
    for name, repo in (('bifrost-trade-infra', infra), ('bifrost-platform', platform)):
        (source / (name + '.git')).symlink_to(repo, target_is_directory=True)
    body = X['script']('clone', tmp_path).replace(
        'http://gitea.cicd.svc.cluster.local:3000/bifrost/', source.as_uri() + '/')
    result = subprocess.run(['bash'], input=body, text=True, capture_output=True, check=False,
                            env=dict(X['fixture_env'](tmp_path), REVISION=args.revision, BASE=args.base_sha,
                                     PLATFORM_REVISION=args.platform_revision, PURPOSE='push'))
    assert result.returncode == 0, result.stdout + result.stderr
    args.cand, args.base = tmp_path / 'ws/cand', tmp_path / 'ws/base'
    clone = args.cand / 'bifrost-trade-infra'
    assert git(clone, 'rev-list', '--count', 'HEAD') == '2'
    missing = subprocess.run(['git', '-C', str(clone), 'cat-file', '-e', bad + '^{commit}'],
                             capture_output=True, check=False)
    assert missing.returncode != 0
    for check in ('scope', 'consumers', 'doc-policy'):
        result = invoke_stage(args, check)
        assert result.returncode == 0, result.stdout + result.stderr
    args.purpose = 'landing'
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1 and 'base_mismatch' in result.stderr


def test_b01_help_discloses_endpoint_semantics():
    result = subprocess.run(['bash', str(Path(__file__).with_name('ci-infra.sh')), '--help'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    for phrase in ('before/after', 'intermediate commits are not checked', 'never landing evidence',
                   'DESIGN-S6-v3-2026-10-29.md', '--base-sha', '--platform-revision'):
        assert phrase in result.stdout
