"""Review 779: real Git decisions, M0-exported CLI, and push endpoint limits."""
import runpy
import subprocess
from pathlib import Path

import pytest

T = runpy.run_path(str(Path(__file__).with_name('test_review777_policy.py')))
X = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_transport.py')))
ci_workspace = T['ci_workspace']
git, put, commit = T['git'], T['put'], T['commit']
DOC, invoke_stage, reset_document = T['DOC'], T['invoke_stage'], T['reset_document']


@pytest.mark.parametrize('prefix', [
    '```inline```\n\n## Owner 决定 approval #1\n\n',
    '   ````inline````\n\n## Owner 决定 approval #1\n\n',
    '```language `invalid info`\n\n## Owner 决定 approval #1\n\n',
    '```inline```\r\n\r\n## Owner 决定 approval #1\r\n\r\n',
    # The exact original 777 B-02 examples, without the later nested heading.
    '  ## Owner 决定 approval #1\n\n',
    'Owner 决定 approval #1\n====================\n\n',
], ids=['inline', 'indented_inline', 'backtick_info', 'crlf_inline', 'original_atx', 'original_setext'])
@pytest.mark.parametrize('removal', [False, True])
def test_a01_decision_edit_after_inline_or_original_heading(ci_workspace, prefix, removal):
    args, infra, _ = ci_workspace
    replacement = '' if removal else '选 B\n'
    reset_document(args, infra, prefix + '选 A\n', prefix + replacement)
    for stage in ('scope', 'consumers', 'code-health'):
        result = invoke_stage(args, stage)
        assert result.returncode == 0, result.stdout + result.stderr
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'owner_claim_removed' in result.stderr and '选 A' in result.stdout
    if not removal:
        assert 'owner_claim_unlinked' in result.stderr and '选 B' in result.stdout
    # An unchanged approval in the heading cannot support this edit; an added
    # evidence line in the same hunk can support both a rewrite and a removal.
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, DOC, prefix + ('Removed' if removal else '选 B') + ' approval #2\n')
    args.revision = commit(infra)
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('opening,closing', [
    ('```md', '```'), (' ```md', '  ````'),
    ('  ````md', '   ````\t'), ('   ~~~md `info`', '~~~~'),
    ('~~~~', '  ~~~~ \t'), ('```md\r', '```\r'),
])
def test_a01_real_fence_preserves_section_and_then_closes(ci_workspace, opening, closing):
    args, infra, _ = ci_workspace
    prefix = '## Owner 决定 approval #1\n\n' + opening + '\n## Ordinary example\n' + closing + '\n\n'
    reset_document(args, infra, prefix + '选 A\n', prefix + '选 B\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'owner_claim_removed' in result.stderr and 'owner_claim_unlinked' in result.stderr
    # A real peer heading after the closing fence ends the decision section.
    prefix += '选 A approval #1\n\n## Ordinary\n\n'
    reset_document(args, infra, prefix + 'Before\n', prefix + 'After\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('false_close', ['```', '~~~~', '```` trailing', '    ````', '\t````'])
def test_a01_invalid_closer_cannot_end_fence(ci_workspace, false_close):
    args, infra, _ = ci_workspace
    prefix = '## Owner 决定 approval #1\n\n````md\n' + false_close + '\n## Ordinary example\n````\n\n'
    reset_document(args, infra, prefix + '选 A\n', prefix + '选 B\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'owner_claim_removed' in result.stderr and 'owner_claim_unlinked' in result.stderr


@pytest.mark.parametrize('not_a_fence', ['``', '~~', '    ```', '\t~~~'])
def test_a01_short_or_indented_marker_cannot_hide_heading(ci_workspace, not_a_fence):
    args, infra, _ = ci_workspace
    prefix = not_a_fence + '\n\n## Owner 决定 approval #1\n\n'
    reset_document(args, infra, prefix + '选 A\n', prefix + '选 B\n')
    result = invoke_stage(args, 'doc-policy')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'owner_claim_removed' in result.stderr and 'owner_claim_unlinked' in result.stderr


@pytest.mark.parametrize('violation,stage,error', [
    ('Owner 决定 A\n', 'doc-policy', 'owner_claim_unlinked'),
    ('line\n' * 501, 'code-health', 'code_health_regressed'),
])
def test_b01_push_checks_endpoints_not_restored_intermediate_commit(ci_workspace, tmp_path, violation, stage, error):
    args, infra, platform = ci_workspace
    args.purpose = 'push'
    git(infra, 'checkout', '--detach', args.base_sha)
    put(infra, DOC, violation)
    bad = args.revision = commit(infra)
    result = invoke_stage(args, stage)
    assert result.returncode == 1 and error in result.stderr, result.stdout + result.stderr
    put(infra, DOC, 'Restored\n')
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
    for check in ('scope', 'consumers', 'doc-policy', 'code-health'):
        result = invoke_stage(args, check)
        assert result.returncode == 0, result.stdout + result.stderr
        if check == 'doc-policy':
            assert 'Owner 决定 A' not in result.stdout
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
