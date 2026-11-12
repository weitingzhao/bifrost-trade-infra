"""Review 777: exercise real Git hunks and the baseline-exported CLI."""
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

T = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_stages.py')))
ci_workspace = T['ci_workspace']
C, git, put, commit = T['C'], T['git'], T['put'], T['commit']
DOC = T['S']['DOC']


def invoke_stage(args, stage):
    return subprocess.run([
        'bash', str(args.base / 'bifrost-trade-infra/scripts/landing/ci-infra.sh'),
        '--stage', stage, '--cand', str(args.cand), '--base', str(args.base),
        '--revision', args.revision, '--base-sha', args.base_sha,
        '--platform-revision', args.platform_revision, '--purpose', args.purpose,
    ], capture_output=True, text=True, check=False)


@pytest.mark.parametrize('leaf', ['中文', '"big"', 'big doc', 'tab\tname', 'new\nline', 'ascii'])
def test_b03_real_filename_growth(ci_workspace, leaf):
    args, infra, _ = ci_workspace
    git(infra, 'checkout', '--detach', args.base_sha)
    git(infra, 'config', 'core.quotePath', 'true')
    name = 'agent-config/work/multi-agent/REPORT-' + leaf + '.md'
    put(infra, name, 'line\n' * 500)
    args.revision = commit(infra)
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, name, 'line\n' * 501)
    args.revision = commit(infra)
    for stage in ('scope', 'consumers', 'doc-policy'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stderr


def test_b03_missing_tracked_file_is_scan_failure(ci_workspace, tmp_path):
    args, infra, _ = ci_workspace
    (infra / 'scripts/landing/doc_policy.py').unlink()
    output = tmp_path / 'scan.json'
    result = subprocess.run(['bash', str(args.base / 'bifrost-trade-infra/agent-config/scripts/code-health/scan.sh'),
                             '--root', str(args.cand), '--repo', 'bifrost-trade-infra', '--json', str(output)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not output.exists()


def test_b03_file_enumeration_failure_is_fatal(ci_workspace, tmp_path):
    args, _infra, _ = ci_workspace
    bindir = tmp_path / 'failing-git'
    bindir.mkdir()
    fake = bindir / 'git'
    fake.write_text('#!/bin/sh\nfor arg in "$@"; do\n  [ "$arg" != ls-files ] || exit 2\ndone\nexec "$REAL_GIT" "$@"\n')
    fake.chmod(0o755)
    output = tmp_path / 'enumeration.json'
    result = subprocess.run(['bash', str(args.base / 'bifrost-trade-infra/agent-config/scripts/code-health/scan.sh'),
                             '--root', str(args.cand), '--repo', 'bifrost-trade-infra', '--json', str(output)],
                            env=dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'], REAL_GIT=shutil.which('git')),
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2 and not output.exists(), result.stdout + result.stderr


def test_r01_multicommit_push_all_policy_stages(ci_workspace):
    args, infra, _ = ci_workspace
    put(infra, DOC, 'Two commits pushed together\n')
    args.revision = commit(infra)
    args.purpose = 'push'
    for stage in ('scope', 'consumers', 'doc-policy'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stderr
    args.purpose = 'landing'
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1 and 'base_mismatch' in result.stderr
