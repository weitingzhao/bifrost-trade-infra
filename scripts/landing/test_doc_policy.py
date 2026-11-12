"""S6 immutable Git fixtures: positive controls and individual rejection layers."""
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

P = runpy.run_path(str(Path(__file__).with_name('doc_policy.py')))
D = runpy.run_path(str(Path(__file__).with_name('doc_consumers.py')))
DOC = 'agent-config/work/multi-agent/REPORT-test.md'


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


def test_consumers_and_documents_positive(repo):
    path, base, rev = candidate(repo)
    P['consumers'](path, base, rev)
    P['documents'](path, base, rev, path, base)


def test_scope_is_retired(capsys):
    # Cleanup wave 2 (2026-11-12): the platform judges the allow set and path
    # tables before it pushes; the stage reads nothing and succeeds.
    P['scope']()
    assert 'retired' in capsys.readouterr().out
    assert 'allow' not in P and 'hard' not in P and 'floor_path' not in P and 'RULES' not in P


@pytest.mark.parametrize('name', ['scripts/tool.py', '.gitea/workflows/x.yml', 'k8s/x.yaml', DOC,
                                  'agent-config/CLAUDE.md'])
def test_documents_check_every_changed_file(repo, name):
    path, base = repo
    put(path, name, b'\0binary\xff')
    with pytest.raises(P['PolicyError'], match='doc_content ' + name):
        P['documents'](path, base, commit_fixture(path), path, base)
    command(path, 'checkout', '-q', '--detach', base)
    put(path, name, 'text\n')
    P['documents'](path, base, commit_fixture(path), path, base)


def test_rename(repo):
    path, base = repo
    command(path, 'mv', DOC, DOC.replace('test', 'renamed'))
    rev = commit_fixture(path)
    P['consumers'](path, base, rev)
    P['documents'](path, base, rev, path, base)


@pytest.mark.parametrize('name', ['', '/abs', 'x/../y', './x', 'a//b', 'a\0b'])
def test_path_parser(name):
    with pytest.raises(P['PolicyError'], match='path_invalid'):
        P['path_name'](name)


def test_globs():
    assert P['matches']('a/*.md', 'a/x.md')
    assert not P['matches']('a/*.md', 'a/b/x.md')
    assert P['matches']('a/**/*.md', 'a/x.md')
    assert P['matches']('a/**/*.md', 'a/b/x.md')


@pytest.mark.parametrize('data', [b'\xff', b'a\0b'])
def test_content_refuses(data):
    with pytest.raises(P['PolicyError'], match='doc_content'):
        P['content'](data, DOC)


def test_content_has_no_size_cap():
    # Cleanup wave 1 (2026-11-11) removed the 256 KB per-document cap.
    assert len(P['content'](b'x' * (256 * 1024 + 1), DOC)) == 256 * 1024 + 1


@pytest.mark.parametrize('text', ['Owner 决定 A\n', '# Owner 决定\n\n选 A\n'])
def test_owner_claims_need_no_evidence(repo, text):
    # Cleanup wave 1 (2026-11-11) removed the rule that Owner-decision claims carry evidence.
    path, base, rev = candidate(repo, text)
    P['documents'](path, base, rev, path, base)
    command(path, 'rm', '-q', DOC)
    P['documents'](path, rev, commit_fixture(path), path, rev)


def test_stable_main_and_base_mismatch(repo):
    path, base, rev = candidate(repo)
    before = P['changes'](path, base, rev)
    command(path, 'update-ref', 'refs/heads/main', rev)
    assert before == P['changes'](path, base, rev)
    with pytest.raises(P['PolicyError'], match='base_mismatch'):
        P['consumers'](path, rev, rev)


def test_consumed_changed_path_constraint_and_missing(repo):
    path, base = repo
    rows = P['registry'](path, base)
    rows[0]['reads'] = ['agent-config/work/multi-agent/REPORT-*.md']
    put(path, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(path)
    _, _, rev = candidate((path, base))
    with pytest.raises(P['PolicyError'], match='consumed_path'):
        P['consumers'](path, base, rev)
    # A read set covering only unchanged files does not fail the run.
    rows[0]['reads'] = ['agent-config/work/multi-agent/REPORT-other.md']
    put(path, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(path)
    _, _, rev = candidate((path, base), '# Report\n\nUnrelated change\n')
    P['consumers'](path, base, rev)
    rows[0]['reads'] = ['agent-config/work/multi-agent/REPORT-*.md']
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


def test_deleted_document(repo):
    path, base = repo
    command(path, 'rm', DOC)
    rev = commit_fixture(path)
    P['consumers'](path, base, rev)
    P['documents'](path, base, rev, path, base)


def test_deleted_consumed_document(repo):
    path, base = repo
    rows = yaml.safe_load((path / P['REGISTRY']).read_text())
    rows[0]['reads'] = [DOC]
    put(path, P['REGISTRY'], yaml.safe_dump(rows))
    base = commit_fixture(path)
    command(path, 'rm', DOC)
    rev = commit_fixture(path)
    with pytest.raises(P['PolicyError'], match='consumed_path'):
        P['consumers'](path, base, rev)


def test_large_change(repo):
    path, base, rev = candidate(repo, 'line\n' * 1600)
    P['consumers'](path, base, rev)
    P['documents'](path, base, rev, path, base)
