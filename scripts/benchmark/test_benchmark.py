"""Offline integration tests: real Git histories and real pytest/Go/bash runs."""
import collections
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
pick = importlib.import_module('pick')
verify = importlib.import_module('verify')

# Do not shadow the standard library's select module used by subprocess.
spec = importlib.util.spec_from_file_location('benchmark_select', HERE / 'select.py')
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(repo, message, paths):
    git(repo, 'add', '--', *paths)
    git(repo, 'commit', '-m', message)
    return git(repo, 'show', '-s', '--format=%H', 'HEAD')


@pytest.fixture
def repo(tmp_path):
    directory = tmp_path / 'repo'
    directory.mkdir()
    git(directory, 'init', '-b', 'main')
    git(directory, 'config', 'user.name', 'Benchmark Fixture')
    git(directory, 'config', 'user.email', 'fixture@example.invalid')
    git(directory, 'config', 'commit.gpgsign', 'false')
    git(directory, 'config', 'core.hooksPath', '/dev/null')
    return directory


def python_fix(repo, before='0', after='1', expected='1'):
    write(repo, 'answer.py', f'def answer():\n    return {before}\n')
    commit(repo, 'Initial implementation', ['answer.py'])
    write(repo, 'answer.py', f'def answer():\n    return {after}  # repaired\n')
    write(repo, 'test_answer.py', 'from answer import answer\n\n'
          f'def test_regression():\n    assert answer() == {expected}\n')
    sha = commit(repo, 'fix: answer regression test\n\nHandle the boundary.\n\n'
                 'Claude-Session: fixture\nChange-Id: I123\nCo-Authored-By: Test <t@example.invalid>',
                 ['answer.py', 'test_answer.py'])
    return pick.candidates_for_commit(repo, sha)[0]


def test_python_round_trip_and_non_fix(repo, tmp_path):
    candidate = python_fix(repo)
    write(repo, 'notes.txt', 'not a fix\n')
    commit(repo, 'Document usage', ['notes.txt'])
    candidates = list(pick.scan(repo))
    assert candidates == [candidate]
    assert candidate['language'] == 'python'
    assert candidate['non_test_files'] == ['answer.py']
    assert candidate['tests_to_run'][0]['argv'][-2:] == ['-k', 'test_regression']
    assert candidate['task_text'] == 'fix: answer regression test\n\nHandle the boundary.'
    result = verify.verify(candidate, work_dir=tmp_path)
    assert result['status'] == 'verified', result
    assert result['before'][0]['returncode'] == 1
    assert '1 failed' in result['before'][0]['tail']
    assert result['after'][0]['returncode'] == 0
    assert not list(tmp_path.glob('benchmark-*'))
    assert git(repo, 'status', '--porcelain') == ''


@pytest.mark.parametrize('before,after,reason', [
    ('1', '1', 'parent tests must fail'), ('0', '2', 'fix tests did not pass')])
def test_reject_invalid_replays(repo, before, after, reason):
    result = verify.verify(python_fix(repo, before, after))
    assert result['status'] == 'rejected'
    assert reason in result['reason']


def test_reject_collection_error(repo):
    python_fix(repo)
    write(repo, 'test_answer.py', 'import nonexistent_benchmark_dependency\n'
          'def test_regression():\n    assert False\n')
    write(repo, 'answer.py', 'def answer():\n    return 2\n')
    sha = commit(repo, 'fix: regression test import', ['test_answer.py', 'answer.py'])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0])
    assert result['status'] == 'rejected'
    assert result['before'][0]['returncode'] == 2
    assert not verify.assertion_failure(result['before'][0])


def test_go_replay_nested_module_modified_function(repo, monkeypatch):
    if not shutil.which('go'):
        pytest.skip('Go executable unavailable')
    monkeypatch.setenv('GOPROXY', 'off')
    monkeypatch.setenv('GOSUMDB', 'off')
    monkeypatch.setenv('GOTOOLCHAIN', 'local')
    write(repo, 'api/go.mod', 'module example.invalid/fixture\n\ngo 1.20\n')
    write(repo, 'api/calc/calc.go', 'package calc\nfunc Answer() int { return 0 }\n')
    write(repo, 'api/calc/calc_test.go', 'package calc\nimport "testing"\n'
          'func TestAnswer(t *testing.T) { if Answer() != 0 { t.Fatal("old") } }\n')
    commit(repo, 'Initial Go module', ['api/go.mod', 'api/calc/calc.go', 'api/calc/calc_test.go'])
    write(repo, 'api/calc/calc.go', 'package calc\nfunc Answer() int { return 1 }\n')
    write(repo, 'api/calc/calc_test.go', 'package calc\nimport "testing"\n'
          'func TestAnswer(t *testing.T) { if Answer() != 1 { t.Fatal("regression") } }\n'
          'func TestBoundary(t *testing.T) { if Answer() < 1 { t.Fatal("boundary") } }\n')
    sha = commit(repo, 'fix: fail on the old code', ['api/calc/calc.go', 'api/calc/calc_test.go'])
    candidate = pick.candidates_for_commit(repo, sha)[0]
    assert candidate['tests_to_run'] == [{'cwd': 'api', 'argv': [
        'go', 'test', './calc', '-run', '^(TestAnswer|TestBoundary)$', '-count=1']}]
    result = verify.verify(candidate, timeout=90)
    assert result['status'] == 'verified', result


@pytest.mark.parametrize('harness', ['python', 'bash'])
def test_shell_replay(repo, harness):
    write(repo, 'scripts/answer.sh', 'echo 0\n')
    commit(repo, 'Initial shell script', ['scripts/answer.sh'])
    write(repo, 'scripts/answer.sh', 'echo 1\n')
    if harness == 'python':
        name = 'tests/test_shell.py'
        text = ('import subprocess\n'
                'def test_script():\n'
                '    assert subprocess.check_output(["bash", "scripts/answer.sh"], text=True).strip() == "1"\n')
    else:
        name, text = 'tests/test_answer.sh', '[ "$(bash scripts/answer.sh)" = 1 ]\n'
    write(repo, name, text)
    sha = commit(repo, 'fix: shell 回归测试', ['scripts/answer.sh', name])
    candidate = pick.candidates_for_commit(repo, sha)[0]
    assert candidate['language'] == 'shell'
    result = verify.verify(candidate)
    assert result['status'] == 'verified', result


@pytest.mark.parametrize('path', ['k8s/deployment.yaml', 'config/a.secret.yaml',
                                 '.env.local', 'config/.env', 'x.secret'])
def test_exclude_sensitive_commits(repo, path):
    python_fix(repo)
    write(repo, path, 'fixture\n')
    write(repo, 'test_answer.py', 'def test_boundary():\n    assert True\n')
    sha = commit(repo, 'fix: regression test', [path, 'test_answer.py'])
    assert pick.candidates_for_commit(repo, sha) == []


def test_exclude_renamed_secret(repo):
    python_fix(repo)
    write(repo, 'sample.secret.txt', 'fixture\n')
    commit(repo, 'fixture', ['sample.secret.txt'])
    git(repo, 'mv', 'sample.secret.txt', 'ordinary.txt')
    write(repo, 'test_answer.py', 'def test_other():\n    assert True\n')
    sha = commit(repo, 'fix: regression test', ['ordinary.txt', 'test_answer.py'])
    assert pick.candidates_for_commit(repo, sha) == []


def test_modified_python_test_names_and_trailers(repo):
    python_fix(repo)
    write(repo, 'answer.py', 'def answer():\n    return 2\n')
    write(repo, 'test_answer.py', 'from answer import answer\n\n'
          'def test_regression():\n    assert answer() == 2\n')
    sha = commit(repo, 'fix: regression test\n\nBody\n\nWork: W-31\nSigned-off-by: X\n continuation',
                 ['answer.py', 'test_answer.py'])
    candidate = pick.candidates_for_commit(repo, sha)[0]
    assert candidate['tests_to_run'][0]['argv'][-1] == 'test_regression'
    assert candidate['task_text'] == 'fix: regression test\n\nBody'
    assert pick.task_text('fix: regression test') == 'fix: regression test'


def test_ts_missing_node_modules(repo):
    write(repo, 'answer.ts', 'export const answer = 0;\n')
    commit(repo, 'Initial TS', ['answer.ts'])
    write(repo, 'answer.ts', 'export const answer = 1;\n')
    write(repo, 'answer.test.ts', "import {expect, test} from 'vitest';\n"
          "import {answer} from './answer';\ntest('regression', () => expect(answer).toBe(1));\n")
    sha = commit(repo, 'fix: regression test', ['answer.ts', 'answer.test.ts'])
    candidate = pick.candidates_for_commit(repo, sha)[0]
    assert candidate['tests_to_run'][0]['argv'] == ['npx', 'vitest', 'run', 'answer.test.ts']
    result = verify.verify(candidate)
    assert result['status'] == 'rejected'
    assert 'cannot link node_modules' in result['reason']


def test_timeout_kills_process_group(tmp_path):
    run = verify.run_test({'cwd': '.', 'argv': ['bash', '-c', 'sleep 30 & wait']},
                          tmp_path, tmp_path, .05)
    assert run['timed_out'] and not verify.assertion_failure(run)


def test_ts_subproject_command_and_module_link(repo, tmp_path):
    write(repo, 'console/package.json', '{}\n')
    write(repo, 'console/src/answer.ts', 'export const answer = 0;\n')
    commit(repo, 'Initial console', ['console/package.json', 'console/src/answer.ts'])
    write(repo, 'console/src/answer.ts', 'export const answer = 1;\n')
    write(repo, 'console/src/answer.test.tsx', 'test("answer", () => {});\n')
    sha = commit(repo, 'fix: regression test', ['console/src/answer.ts', 'console/src/answer.test.tsx'])
    candidate = pick.candidates_for_commit(repo, sha)[0]
    assert candidate['tests_to_run'] == [{'cwd': 'console', 'argv': [
        'npx', 'vitest', 'run', 'src/answer.test.tsx']}]
    (repo / 'console/node_modules').mkdir()
    tree = tmp_path / 'export'
    tree.mkdir()
    verify.link_node_modules(repo, tree, candidate['tests_to_run'])
    assert (tree / 'console/node_modules').resolve() == repo / 'console/node_modules'


def test_non_fix_and_tests_only_not_picked(repo):
    python_fix(repo)
    write(repo, 'answer.py', 'def answer():\n    return 2\n')
    write(repo, 'test_answer.py', 'def test_next():\n    assert True\n')
    sha = commit(repo, 'Adjust behavior', ['answer.py', 'test_answer.py'])
    assert pick.candidates_for_commit(repo, sha) == []
    write(repo, 'test_answer.py', 'def test_only():\n    assert True\n')
    sha = commit(repo, 'regression test', ['test_answer.py'])
    assert pick.candidates_for_commit(repo, sha) == []


def test_base_setup_failure_is_not_regression(repo):
    write(repo, 'answer.py', 'import missing_fixture_dependency\ndef answer():\n    return 0\n')
    commit(repo, 'Initial broken import', ['answer.py'])
    write(repo, 'answer.py', 'def answer():\n    return 1\n')
    write(repo, 'test_answer.py', 'from answer import answer\n'
          'def test_answer():\n    assert answer() == 1\n')
    sha = commit(repo, 'fix: regression test', ['answer.py', 'test_answer.py'])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0])
    assert result['status'] == 'rejected'
    assert result['after'][0]['returncode'] == 0
    assert result['before'][0]['returncode'] == 2


def test_archive_escape_rejected(repo, tmp_path):
    python_fix(repo)
    (repo / 'outside').symlink_to('../outside')
    sha = commit(repo, 'Add unsafe fixture symlink', ['outside'])
    tree = tmp_path / 'export'
    tree.mkdir()
    with pytest.raises(ValueError, match='symlink escapes'):
        verify.export_tree(repo, sha, tree)


def test_no_tests_and_build_failure_rejected():
    record = {'argv': ['go', 'test'], 'returncode': 0, 'tail': 'ok [no tests to run]',
              'timed_out': False}
    assert not verify.passed(record)
    record.update(returncode=1, tail='FAIL example [build failed]')
    assert not verify.assertion_failure(record)
    record.update(argv=['python3', '-m', 'pytest'], returncode=0, tail='1 skipped')
    assert not verify.passed(record)


def test_reject_tampered_command(repo):
    candidate = python_fix(repo)
    candidate['tests_to_run'][0]['argv'] = ['bash', '-c', 'exit 0']
    result = verify.verify(candidate)
    assert result['status'] == 'rejected' and 'differ' in result['reason']


def pool():
    rows = []
    for language, count in selector.QUOTAS.items():
        for i in range(count + 3):
            rows.append({'status': 'verified', 'repo': f'/repo/{i % 4}',
                         'fix_commit': f'{language}-{i}', 'parent': f'base-{language}-{i}',
                         'language': language, 'test_files': [f'test_{i}'],
                         'non_test_files': [f'code_{i}'], 'tests_to_run': [], 'task_text': 'Fix defect'})
    return rows


def test_select_quotas_diversity_and_determinism():
    rows = pool()
    questions, missing = selector.select(rows + rows)
    assert not missing and len(questions) == 20
    assert collections.Counter(q['language'] for q in questions) == selector.QUOTAS
    assert len({q['id'] for q in questions}) == 20
    assert len({q['repo'] for q in questions[:4]}) == 4
    assert selector.select(list(reversed(rows)))[0] == questions
    assert all(q['base_commit'].startswith('base-') and 'check_command' in q for q in questions)


def test_select_prefers_new_files():
    rows = pool()[:3]
    for row in rows:
        row['repo'] = '/same'
    rows[1]['test_files'] = rows[0]['test_files']
    rows[1]['non_test_files'] = rows[0]['non_test_files']
    questions, _ = selector.select(rows, {'go': 2})
    assert [q['fix_commit'] for q in questions] == ['go-0', 'go-2']


def test_select_short_pool_cli(tmp_path):
    rows = pool()[:2]
    rows[1]['status'] = 'rejected'
    questions, missing = selector.select(rows)
    assert len(questions) == 1
    assert missing == {'go': 5, 'python': 7, 'ts': 5, 'shell': 2}
    source, output = tmp_path / 'verified.jsonl', tmp_path / 'questions.json'
    source.write_text('\n'.join(json.dumps(r) for r in rows))
    result = subprocess.run([sys.executable, str(HERE / 'select.py'), str(source),
                             '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 1 and not output.exists()
    assert json.loads(result.stderr)['missing'] == missing


def test_cli_pipeline(repo, tmp_path):
    python_fix(repo)
    picked = subprocess.run([sys.executable, str(HERE / 'pick.py'), str(repo)],
                            check=True, capture_output=True, text=True)
    source = tmp_path / 'candidates.jsonl'
    source.write_text(picked.stdout)
    verified = subprocess.run([sys.executable, str(HERE / 'verify.py'), str(source)],
                              check=True, capture_output=True, text=True)
    assert json.loads(verified.stdout)['status'] == 'verified'
    all_rows = tmp_path / 'verified.jsonl'
    all_rows.write_text('\n'.join(json.dumps(r) for r in pool()))
    output = tmp_path / 'questions.json'
    subprocess.run([sys.executable, str(HERE / 'select.py'), str(all_rows), '--output', str(output)],
                   check=True, capture_output=True)
    assert len(json.loads(output.read_text())) == 20


@pytest.mark.parametrize('language', ['go', 'python'])
def test_new_symbol_replay(repo, monkeypatch, language):
    if language == 'go' and not shutil.which('go'):
        pytest.skip('Go executable unavailable')
    monkeypatch.setenv('GOPROXY', 'off')
    monkeypatch.setenv('GOTOOLCHAIN', 'local')
    if language == 'go':
        write(repo, 'go.mod', 'module fixture\n\ngo 1.20\n')
        code, test = 'answer.go', 'answer_test.go'
        old, new = 'package fixture\n', 'package fixture\nfunc Added() int { return 1 }\n'
        body = 'package fixture\nimport "testing"\nfunc TestAdded(t *testing.T) { if Added() != 1 { t.Fatal("bad") } }\n'
        paths = ['go.mod', code]
    else:
        code, test = 'answer.py', 'test_answer.py'
        old, new = '# before\n', 'def Added():\n    return 1\n'
        body = 'from answer import Added\ndef test_added():\n    assert Added() == 1\n'
        paths = [code]
    write(repo, code, old)
    commit(repo, 'Initial implementation', paths)
    write(repo, code, new)
    write(repo, test, body)
    sha = commit(repo, 'fix: regression test added symbol', [code, test])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0], timeout=90)
    assert result['status'] == 'verified', result
    assert result['fails_by'] == 'missing_symbol'
    assert result['missing_symbols'] == ['Added']
    questions, _ = selector.select([result], {language: 1})
    assert 'they call Added, which does not exist yet' in questions[0]['task_text']


def test_missing_third_party_module_stays_rejected(repo):
    write(repo, 'answer.py', 'import absent_third_party_package\n')
    commit(repo, 'Initial import', ['answer.py'])
    write(repo, 'answer.py', 'def Added():\n    return 1\n')
    write(repo, 'test_answer.py', 'from answer import Added\ndef test_added():\n    assert Added() == 1\n')
    sha = commit(repo, 'fix: regression test', ['answer.py', 'test_answer.py'])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0])
    assert result['status'] == 'rejected', result
    assert result['after'][0]['returncode'] == 0
    assert 'absent_third_party_package' in result['before'][0]['tail']
