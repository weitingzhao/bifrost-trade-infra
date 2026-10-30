"""S6 immutable Git fixtures: positive controls and individual rejection layers."""
import os
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

P = runpy.run_path(str(Path(__file__).with_name('doc_policy.py')))
D = runpy.run_path(str(Path(__file__).with_name('doc_consumers.py')))
DOC = 'agent-config/work/multi-agent/REPORT-test.md'
ALLOW = ['agent-config/work/multi-agent/' + p for p in
         ('CUT-*.md', 'DESIGN-*.md', 'REPORT-*.md', 'REVIEW-*.md', 'LESSONS-*.md', 'reviews/*.md')]


def command(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=False, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def put(repo, name, data):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    command(repo, 'add', '--', name)


def commit_fixture(repo):
    command(repo, '-c', 'user.name=CI fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'Fixture')
    return command(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    command(repo, 'init', '-q')
    put(repo, P['RULES'], yaml.safe_dump({'repos': [{'repo': P['REPO'], 'allow': ALLOW}]}))
    put(repo, DOC, '# Report\n\nInitial\n')
    put(repo, 'scripts/reader.py', 'path = "agent-config/work/closed.json"\n')
    found = D['hits']('scripts/reader.py', (repo / 'scripts/reader.py').read_bytes())
    rows = [dict(file='scripts/reader.py', **{'class': 'reader'}, reads=['agent-config/work/closed.json'],
                 hits=D['fingerprint'](found), why='Fixture', checked_by='review #1', effect='test')]
    put(repo, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(repo)
    return repo, base


def candidate(repo, text='# Report\n\nChanged\n'):
    path, base = repo
    put(path, DOC, text)
    return path, base, commit_fixture(path)


def test_scope_and_consumers_positive(repo):
    path, base, rev = candidate(repo)
    P['scope'](path, base, rev)
    P['consumers'](path, base, rev)
    P['documents'](path, base, rev, path, base)


@pytest.mark.parametrize('name,content,error', [
    ('scripts/x.py', 'x=1\n', 'hard_floor'),
    ('docs/REPORT-x.md', 'x\n', 'scope'),
    ('agent-config/work/multi-agent/reviews/SKILL.md', 'x\n', 'hard_floor'),
    (DOC, b'\0binary\xff', 'structural'),
])
def test_scope_rejects_each_layer(repo, name, content, error):
    path, base = repo
    put(path, name, content)
    rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match=error):
        P['scope'](path, base, rev)


def test_mode_delete_and_rename(repo):
    path, base = repo
    os.chmod(path / DOC, 0o755)
    command(path, 'add', '--', DOC)
    rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='structural'):
        P['scope'](path, base, rev)
    command(path, 'checkout', '--detach', base)
    command(path, 'mv', DOC, DOC.replace('test', 'renamed'))
    rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='change_kind'):
        P['scope'](path, base, rev)


def test_symlink(repo):
    path, base = repo
    (path / DOC).unlink()
    (path / DOC).symlink_to('elsewhere')
    command(path, 'add', '--', DOC)
    with pytest.raises(P['PolicyError'], match='structural'):
        P['scope'](path, base, commit_fixture(path))


@pytest.mark.parametrize('name', ['', '/abs', 'x/../y', './x', 'a//b', 'a\0b'])
def test_path_parser(name):
    with pytest.raises(P['PolicyError'], match='path_invalid'):
        P['path_name'](name)


def test_globs():
    assert P['matches']('a/*.md', 'a/x.md')
    assert not P['matches']('a/*.md', 'a/b/x.md')
    assert P['matches']('a/**/*.md', 'a/x.md')
    assert P['matches']('a/**/*.md', 'a/b/x.md')


@pytest.mark.parametrize('data', [b'\xff', b'a\0b', b'x' * (256 * 1024 + 1)])
def test_content_refuses(data):
    with pytest.raises(P['PolicyError'], match='doc_content'):
        P['content'](data, DOC)


def test_content_boundary():
    assert len(P['content'](b'x' * (256 * 1024), DOC)) == 256 * 1024


@pytest.mark.parametrize('proof', ['审批 #182', 'request #12', '线程 2026-10-29 12:01'])
def test_owner_evidence_positive(repo, proof):
    path, base, rev = candidate(repo, f'# Report\n\nOwner 决定 A（{proof}）\n')
    P['documents'](path, base, rev, path, base)


@pytest.mark.parametrize('text', ['Owner 决定 A\n', '# Owner 决定\n\n选 A\n'])
def test_owner_unlinked(repo, text):
    path, base, rev = candidate(repo, text)
    with pytest.raises(P['PolicyError'], match='owner_claim_unlinked'):
        P['documents'](path, base, rev, path, base)


def test_existing_section_and_commit_only(repo):
    path, _ = repo
    put(path, 'agent-config/work/multi-agent/CUT-test.md', '# 11.14 Decision\n')
    base = commit_fixture(path)
    text = 'Owner 决定 A（CUT-test.md §11.14）\n'
    P['owner_claims']('', text, path, base, path, base, DOC)
    P['owner_claims']('', 'Owner 决定 A ' + base[:9], path, base, path, base, DOC)
    put(path, 'agent-config/work/multi-agent/CUT-test.md', '# 11.14 Decision\n# 11.99 New\n')
    new = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='owner_claim_unlinked'):
        P['owner_claims']('', 'Owner 决定 A（CUT-test.md §11.99）', path, base, path, base, DOC)
    with pytest.raises(P['PolicyError'], match='owner_claim_unlinked'):
        P['owner_claims']('', 'Owner 决定 A ' + new, path, base, path, base, DOC)


def test_owner_removal_same_hunk(repo):
    path, base = repo
    old = 'Owner 决定 A 审批 #1\n'
    P['owner_claims'](old, 'Changed approval #2\n', path, base, path, base, DOC)
    with pytest.raises(P['PolicyError'], match='owner_claim_removed'):
        P['owner_claims'](old, 'Changed\n', path, base, path, base, DOC)


def test_baseline_scope_and_stable_main(repo):
    path, base, rev = candidate(repo)
    before = P['changes'](path, base, rev)
    command(path, 'update-ref', 'refs/heads/main', rev)
    assert before == P['changes'](path, base, rev)
    with pytest.raises(P['PolicyError'], match='base_mismatch'):
        P['scope'](path, rev, rev)
    # Candidate cannot change its policy before passing scope.
    put(path, P['RULES'], 'repos: []\n')
    next_rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='hard_floor'):
        P['scope'](path, rev, next_rev)


def test_registry_overlap_constraint_and_missing(repo):
    path, base = repo
    rows = P['registry'](path, base)
    rows[0]['reads'] = ['agent-config/work/multi-agent/REPORT-*.md']
    put(path, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(path)
    _, _, rev = candidate((path, base))
    with pytest.raises(P['PolicyError'], match='registry_overlap'):
        P['consumers'](path, base, rev)
    rows[0]['class'] = 'constraint'
    put(path, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(path)
    _, _, rev = candidate((path, base), '# Report\n\nSecond change\n')
    P['consumers'](path, base, rev)
    command(path, 'rm', P['REGISTRY'])
    base = commit_fixture(path)
    _, _, rev = candidate((path, base), '# Report\n\nThird change\n')
    with pytest.raises(P['PolicyError'], match='git_read_failed'):
        P['consumers'](path, base, rev)


def test_consumer_detection_and_hash(repo):
    path, base = repo
    rows = P['registry'](path, base)
    found = D['hits']('scripts/reader.py', (path / 'scripts/reader.py').read_bytes())
    D['verify'](rows, {'scripts/reader.py': found}, P['REPO'])
    assert D['fingerprint'](found) == D['fingerprint']([(99, found[0][1])])
    with pytest.raises(D['P']['PolicyError'], match='unregistered_consumer'):
        D['verify'](rows, {'scripts/new.py': found}, P['REPO'])
    with pytest.raises(D['P']['PolicyError'], match='consumer_changed'):
        D['verify'](rows, {'scripts/reader.py': [(1, found[0][1] + ' changed')]}, P['REPO'])
    D['verify'](rows, {}, P['REPO'])  # stale registration warns, never invents reads
    with pytest.raises(P['PolicyError'], match='consumed_path'):
        P['consumed'](rows, ['agent-config/work/closed.json'])


@pytest.mark.parametrize('line', ['"multi-agent"', '"agent-config/work"', '"work/multi"',
                                 "root / 'work' / 'crew'", '"/work/"', 'git ls-files',
                                 'git grep', 'p.rglob(', 'os.walk(', 'p.glob(', 'readdirSync',
                                 'filepath.Walk', 'WalkDir', 'find .', 'find "$dir"'])
def test_discovery_signals(line):
    assert D['hits']('scripts/a.py', line.encode())
    assert not D['hits'](DOC, line.encode())
    assert D['hits']('CLAUDE.md', line.encode())
    if not D['S1'].search(line):
        assert not D['hits']('a.go', line.encode(), platform=True)


def test_real_git_hunk_cannot_borrow_distant_evidence(repo):
    path, _ = repo
    old = 'Owner 决定 A approval #1\n\n' + ''.join(f'context {i}\n' for i in range(30))
    put(path, DOC, old)
    base = commit_fixture(path)
    put(path, DOC, old.replace('Owner 决定 A approval #1', 'Removed') + '\nChanged approval #2\n')
    rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='owner_claim_removed'):
        P['documents'](path, base, rev, path, base)


def test_removed_claim_cannot_borrow_unchanged_paragraph_evidence(repo):
    path, base = repo
    with pytest.raises(P['PolicyError'], match='owner_claim_removed'):
        P['owner_claims']('Owner 决定 A\napproval #1\n', 'Changed\napproval #1\n',
                          path, base, path, base, DOC)


def test_scope_limit_and_missing_allow(repo):
    path, base = repo
    for i in range(6):
        put(path, f'agent-config/work/multi-agent/REPORT-{i}.md', 'small\n')
    with pytest.raises(P['PolicyError'], match='scope_size'):
        P['scope'](path, base, commit_fixture(path))
    put(path, P['RULES'], 'repos: []\n')
    base = commit_fixture(path)
    _, _, rev = candidate((path, base))
    with pytest.raises(P['PolicyError'], match='infra_allow_missing'):
        P['scope'](path, base, rev)
