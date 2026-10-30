"""Review 777: exercise real Git hunks and the baseline-exported CLI."""
import json
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


def reset_document(args, infra, old, new):
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, DOC, old)
    args.base_sha = commit(infra)
    git(args.base / 'bifrost-trade-infra', 'checkout', '--detach', args.base_sha)
    put(infra, DOC, new)
    args.revision = commit(infra)


@pytest.mark.parametrize('separator', ['\u2028', '\u0085', '\v', '\f', '\r'])
@pytest.mark.parametrize('removal', [False, True])
def test_b01_git_line_separators(ci_workspace, separator, removal):
    args, infra, _ = ci_workspace
    claim = 'prefix' + separator + 'Owner 决定 A\n'
    reset_document(args, infra, claim if removal else 'Before\n', 'After\n' if removal else claim)
    for stage in ('scope', 'consumers'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stderr
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert ('owner_claim_removed' if removal else 'owner_claim_unlinked') in result.stderr
    assert 'Owner 决定 A' in result.stdout
    # Evidence on the added Git line is the same-entry positive control.
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, DOC, ('After' if removal else claim.rstrip('\n')) + ' approval #2\n')
    args.revision = commit(infra)
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('heading', [
    ' ## Owner 决定 approval #1', '  ## Owner 决定 approval #1',
    '   ## Owner 决定 approval #1', 'Owner 决定 approval #1\n====================',
    'Owner 决定 approval #1\n--------------------',
    'Owner 决定 approval #1\r\n====================\r',
    'Owner 决定 approval #1\ncontinued title\n====================',
    '## Owner 决定 approval #1\n\n```md\n## Ordinary example\n```',
])
def test_b02_markdown_decision_sections(ci_workspace, heading):
    args, infra, _ = ci_workspace
    prefix = heading + '\n\n### Detail\n\n'
    reset_document(args, infra, prefix + '选 A\n', prefix + '选 B\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'owner_claim_removed' in result.stderr and 'owner_claim_unlinked' in result.stderr
    assert '选 A' in result.stdout and '选 B' in result.stdout
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, DOC, prefix + '选 B approval #2\n')
    args.revision = commit(infra)
    assert invoke_stage(args, 'doc-policy').returncode == 0


@pytest.mark.parametrize('heading,next_heading', [
    ('  ## Owner 决定 approval #1', '  ## Ordinary'),
    ('Owner 决定 approval #1\n====', 'Ordinary\n===='),
    ('Owner 决定 approval #1\n----', 'Ordinary\n----'),
])
def test_b02_section_ends_at_peer(ci_workspace, heading, next_heading):
    args, infra, _ = ci_workspace
    prefix = heading + '\n\n选 A approval #1\n\n' + next_heading + '\n\n'
    reset_document(args, infra, prefix + 'ordinary A\n', prefix + 'ordinary B\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('leaf', ['中文', '"big"', 'big doc', 'tab\tname', 'new\nline', 'ascii'])
def test_b03_real_filename_growth(ci_workspace, leaf):
    args, infra, _ = ci_workspace
    git(infra, 'checkout', '--detach', args.base_sha)
    git(infra, 'config', 'core.quotePath', 'true')
    name = 'agent-config/work/multi-agent/REPORT-' + leaf + '.md'
    put(infra, name, 'line\n' * 500)
    args.revision = commit(infra)
    assert invoke_stage(args, 'code-health').returncode == 0
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, name, 'line\n' * 501)
    args.revision = commit(infra)
    for stage in ('scope', 'consumers', 'doc-policy'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stderr
    result = invoke_stage(args, 'code-health')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'code_health_regressed code.oversized.rocket.infra' in result.stderr


def test_b03_missing_tracked_file_is_scan_failure(ci_workspace, tmp_path):
    args, infra, _ = ci_workspace
    (infra / DOC).unlink()
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


@pytest.mark.parametrize('attestation', [False, True])
def test_b03_legacy_numeric_report_is_not_complete(ci_workspace, attestation):
    args, infra, _ = ci_workspace
    git(infra, 'checkout', '--detach', args.base_sha)
    data = {'metrics': [{'id': key, 'repo': 'bifrost-trade-infra', 'value': 0} for key in sorted(C.METRICS)]}
    if attestation:
        data['scan_complete'] = {'bifrost-trade-infra': {'files_read': 0, 'paths_sha256': '0' * 64}}
    report = json.dumps(data)
    put(infra, 'agent-config/scripts/code-health/scan.sh',
        '#!/bin/bash\nwhile [[ "$1" != --json ]]; do shift; done\nprintf \'%s\\n\' \'' + report + '\' > "$2"\n')
    args.base_sha = commit(infra)
    git(args.base / 'bifrost-trade-infra', 'checkout', '--detach', args.base_sha)
    put(infra, DOC, 'Updated\n')
    args.revision = commit(infra)
    result = invoke_stage(args, 'code-health')
    assert result.returncode == 1 and 'code_health_scan_incomplete' in result.stderr


def test_r01_multicommit_push_all_policy_stages(ci_workspace):
    args, infra, _ = ci_workspace
    put(infra, DOC, 'Two commits pushed together\n')
    args.revision = commit(infra)
    args.purpose = 'push'
    for stage in ('scope', 'consumers', 'doc-policy', 'code-health'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stderr
    args.purpose = 'landing'
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1 and 'base_mismatch' in result.stderr
