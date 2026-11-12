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
    ('.gitea/workflows/x.yml', 'x: 1\n', 'hard_floor'),
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
    P['scope'](path, base, rev)
    P['consumers'](path, base, rev)


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


def test_baseline_scope_and_stable_main(repo):
    path, base, rev = candidate(repo)
    before = P['changes'](path, base, rev)
    command(path, 'update-ref', 'refs/heads/main', rev)
    assert before == P['changes'](path, base, rev)
    with pytest.raises(P['PolicyError'], match='base_mismatch'):
        P['scope'](path, rev, rev)
    # A floor candidate can propose policy changes, but scope reads the base.
    put(path, P['RULES'], 'repos: []\n')
    next_rev = commit_fixture(path)
    P['scope'](path, rev, next_rev)
    with pytest.raises(P['PolicyError'], match='infra_allow_missing'):
        P['allow'](path, next_rev)


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


def test_scope_limit_and_missing_allow(repo):
    path, base = repo
    for i in range(101):
        put(path, f'agent-config/work/multi-agent/REPORT-{i}.md', 'small\n')
    P['scope'](path, base, commit_fixture(path))
    put(path, P['RULES'], 'repos: []\n')
    base = commit_fixture(path)
    _, _, rev = candidate((path, base))
    with pytest.raises(P['PolicyError'], match='infra_allow_missing'):
        P['scope'](path, base, rev)


@pytest.mark.parametrize('count', [10, 100, 101])
def test_floor_file_limit(repo, count):
    path, base = repo
    for i in range(count):
        put(path, f'k8s/test-{i}.yaml', 'kind: ConfigMap\n')
    revision = commit_fixture(path)
    P['scope'](path, base, revision)


@pytest.mark.parametrize('name,text,error', [
    ('k8s/secret.yaml', 'kind: Secret\n', 'secret'),
    ('k8s/list.yaml', "- kind: 'Secret' # hidden\n", 'secret'),
    ('scripts/.env', 'fixture\n', 'hard_floor'),
    ('scripts/AGENTS.md', 'fixture\n', 'hard_floor'),
])
def test_floor_keeps_absolute_boundary(repo, name, text, error):
    path, base = repo
    put(path, name, text)
    with pytest.raises(P['PolicyError'], match=error):
        P['scope'](path, base, commit_fixture(path))


def test_floor_rejects_mixed_document(repo):
    path, base = repo
    put(path, 'scripts/task.py', 'pass\n')
    put(path, DOC, 'Changed\n')
    with pytest.raises(P['PolicyError'], match='mixed_floor_document'):
        P['scope'](path, base, commit_fixture(path))


def test_existing_executable_floor_script(repo):
    path, _ = repo
    name = 'scripts/helper.sh'
    put(path, name, '#!/bin/sh\necho before\n')
    os.chmod(path / name, 0o755)
    command(path, 'add', '--', name)
    base = commit_fixture(path)
    put(path, name, '#!/bin/sh\necho after\n')
    revision = commit_fixture(path)
    P['scope'](path, base, revision)
    base = revision
    os.chmod(path / name, 0o644)
    command(path, 'add', '--', name)
    with pytest.raises(P['PolicyError'], match='structural'):
        P['scope'](path, base, commit_fixture(path))


@pytest.mark.parametrize('name', ['scripts/a\\b.py', 'scripts/a\tb.py', 'scripts/a\x7fb.py'])
def test_floor_rejects_invalid_paths(repo, name):
    path, base = repo
    put(path, name, 'pass\n')
    with pytest.raises(P['PolicyError'], match='path_invalid'):
        P['scope'](path, base, commit_fixture(path))


def test_floor_rejects_new_executable(repo):
    path, base = repo
    name = 'scripts/new.sh'
    put(path, name, '#!/bin/sh\ntrue\n')
    os.chmod(path / name, 0o755)
    command(path, 'add', '--', name)
    with pytest.raises(P['PolicyError'], match='structural'):
        P['scope'](path, base, commit_fixture(path))


def test_deleted_document(repo):
    path, base = repo
    command(path, 'rm', DOC)
    rev = commit_fixture(path)
    P['scope'](path, base, rev)
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
    P['scope'](path, base, rev)
    with pytest.raises(P['PolicyError'], match='registry_overlap|consumed_path'):
        P['consumers'](path, base, rev)


def test_large_change_and_empty(repo):
    path, base, rev = candidate(repo, 'line\n' * 1600)
    P['scope'](path, base, rev)
    command(path, '-c', 'user.name=CI fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Empty')
    with pytest.raises(P['PolicyError'], match='scope_size'):
        P['scope'](path, rev, command(path, 'rev-parse', 'HEAD'))
