"""Boundary cases for historical evidence and attributed setup failures."""
import pytest

from test_benchmark import repo as repo, write, commit, pick, verify, python_fix
from missing_symbols import missing_symbols, source_delta


@pytest.mark.parametrize('message,expected', [
    ('repair: review 267 B1', True), ('fix A1: handle boundary', True),
    ('B9 fixed: handle boundary', True), ('review style only', False),
    ('A10 fix: not a listed item', False), ('review 1267 unrelated', False),
    ('adjust behavior\n\nWork: review 267', False)])
def test_review_message_evidence(repo, message, expected):
    candidate = python_fix(repo)
    write(repo, 'answer.py', 'def answer():\n    return 2\n')
    write(repo, 'test_answer.py', 'from answer import answer\ndef test_boundary():\n    assert answer() == 2\n')
    sha = commit(repo, message, ['answer.py', 'test_answer.py'])
    assert bool(pick.candidates_for_commit(repo, sha)) == expected
    assert candidate['language'] == 'python'


def test_named_review_test(repo):
    python_fix(repo)
    write(repo, 'answer.py', 'def answer():\n    return 2\n')
    write(repo, 'test_answer.py', 'from answer import answer\ndef test_review_267_A1():\n    assert answer() == 2\n')
    sha = commit(repo, 'Handle boundary', ['answer.py', 'test_answer.py'])
    assert pick.candidates_for_commit(repo, sha)


@pytest.mark.parametrize('code,test', [
    ('def Added():\n    return 1\n', 'from added import Added\ndef test_new():\n    assert Added() == 1\n'),
    ('def Added():\n    return 1\n', 'import added\ndef test_new():\n    assert added.Added() == 1\n'),
    ('class Answer:\n    def Added(self):\n        return 1\n',
     'from added import Answer\ndef test_new():\n    assert Answer().Added() == 1\n')])
def test_added_module_or_attribute(repo, code, test):
    write(repo, 'added.py', 'class Answer:\n    pass\n')
    commit(repo, 'Initial', ['added.py'])
    # Use a new module for ModuleNotFoundError as well as existing module attributes.
    module = 'added' if 'import added' in test or 'Answer' in code else 'new_module'
    write(repo, module + '.py', code)
    write(repo, 'test_answer.py', test.replace('from added', 'from ' + module))
    sha = commit(repo, 'fix: regression test', [module + '.py', 'test_answer.py'])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0])
    assert result['status'] == 'verified', result
    assert result['fails_by'] == 'missing_symbol'


@pytest.mark.parametrize('output', [
    "E   ImportError: cannot import name 'Added' from 'answer'\nE   ModuleNotFoundError: No module named 'third_party'",
    "E   ImportError: cannot import name 'Added' from 'other_package'",
    "E   ImportError: cannot import name 'Added' from 'answer'\nE   SyntaxError: invalid syntax",
    "E   AttributeError: module 'other_package' has no attribute 'Added'",
])
def test_unrelated_or_mixed_python_errors(repo, output):
    candidate = python_fix(repo)
    # The delta has no added name; matching tokens alone never qualify.
    run = {'argv': ['python3', '-m', 'pytest'], 'returncode': 2,
           'timed_out': False, 'tail': output}
    assert not missing_symbols(run, candidate, source_delta(candidate))


@pytest.mark.parametrize('error,accepted', [
    ('undefined: Added', True),
    ('undefined: fixture.Added', True),
    ('undefined: thirdparty.Added', False),
    ('x.Added undefined (type Thing has no field or method Added)', True),
    ('too many arguments in call to Added', True),
    ('not enough arguments in call to Added', True),
    ('undefined: Other', False),
    ('syntax error: unexpected token', False),
    ('undefined: Added\nanswer_test.go:9:2: undefined: Other', False),
    ('undefined: Added\n../other/other.go:2:1: undefined: Added', False),
    ('undefined: Added\ngo: missing dependency', False),
])
def test_go_diagnostics(error, accepted):
    run = {'argv': ['go', 'test', './pkg'], 'cwd': '.', 'returncode': 1,
           'timed_out': False, 'tail': f'answer_test.go:4:2: {error}\nFAIL fixture [build failed]'}
    # Diagnostic filenames are relative to the module root.
    run['tail'] = run['tail'].replace('answer_test.go:', 'pkg/answer_test.go:')
    assert bool(missing_symbols(run, {'language': 'go'}, ({'pkg': {'Added', '@package:fixture'}}, {}, set()))) == accepted
    run['truncated'] = True
    assert not missing_symbols(run, {'language': 'go'}, ({'pkg': {'Added', '@package:fixture'}}, {}, set()))


@pytest.mark.parametrize('old,new,expression', [
    ('type Thing struct {}', 'type Thing struct { Added int }', '(Thing{}).Added'),
    ('func Added() int { return 1 }', 'func Added(n int) int { return n }', 'Added(1)'),
    ('func Added(n int) int { return n }', 'func Added() int { return 1 }', 'Added()'),
    ('func Added(\n) int { return 1 }', 'func Added(\n n int,\n) int { return n }', 'Added(1)'),
])
def test_go_field_and_signature_replays(repo, old, new, expression):
    import shutil
    if not shutil.which('go'):
        pytest.skip('Go executable unavailable')
    write(repo, 'go.mod', 'module fixture\n\ngo 1.20\n')
    write(repo, 'answer.go', 'package fixture\n' + old + '\n')
    commit(repo, 'Initial Go', ['go.mod', 'answer.go'])
    write(repo, 'answer.go', 'package fixture\n' + new + '\n')
    write(repo, 'answer_test.go', 'package fixture\nimport "testing"\n'
          'func TestAdded(t *testing.T) { if ' + expression + ' < 0 { t.Fatal("bad") } }\n')
    sha = commit(repo, 'fix: regression test', ['answer.go', 'answer_test.go'])
    result = verify.verify(pick.candidates_for_commit(repo, sha)[0], timeout=90)
    assert result['status'] == 'verified', result
    assert result['fails_by'] == 'missing_symbol'


def test_replay_src_precedes_host_pythonpath(tmp_path, monkeypatch):
    host, tree = tmp_path / 'host', tmp_path / 'tree'
    write(host, 'answer.py', 'VALUE = "host"\n')
    write(tree, 'src/answer.py', 'VALUE = "archived"\n')
    monkeypatch.setenv('PYTHONPATH', str(host))
    run = verify.run_test({'cwd': '.', 'argv': ['python3', '-c',
                           'from answer import VALUE; print(VALUE)']}, tree, tmp_path, 10)
    assert run['returncode'] == 0 and run['tail'].strip() == 'archived'


def test_declarations_not_comments_and_instance_attributes(repo):
    write(repo, 'answer.go', 'package fixture\n')
    write(repo, 'answer.py', 'class Answer:\n    pass\n')
    commit(repo, 'Initial', ['answer.go', 'answer.py'])
    write(repo, 'answer.go', 'package fixture\nconst (\n Added = 1\n)\n'
          '// func Fake() {}\nvar text = `\nfunc Quoted() {}\n`\n')
    write(repo, 'answer.py', 'class Answer:\n    def __init__(self):\n        self.added = 1\n')
    sha = commit(repo, 'Update declarations', ['answer.go', 'answer.py'])
    candidate = {'repo': str(repo), 'fix_commit': sha, 'parent': git_parent(repo, sha),
                 'non_test_files': ['answer.go', 'answer.py']}
    go, python, _ = source_delta(candidate)
    assert 'Added' in go['.'] and not {'Fake', 'Quoted'} & go['.']
    assert ('Answer', 'added') in python['answer']


def git_parent(repo, sha):
    from test_benchmark import git
    return git(repo, 'rev-parse', sha + '^')


def test_assertion_message_can_quote_script_error():
    run = {'argv': ['python3', '-m', 'pytest'], 'returncode': 1, 'timed_out': False,
           'tail': 'E AssertionError: bad result\nE ERROR: quoted script output\n1 failed\n'}
    assert verify.assertion_failure(run)
    run['tail'] = 'E SystemExit: 1\n1 failed\n'
    assert not verify.assertion_failure(run)


def test_chained_exception_ending_in_assertion_is_regression():
    run = {'argv': ['python3', '-m', 'pytest'], 'returncode': 1, 'timed_out': False,
           'tail': 'E RuntimeError: mocked first error\nE AssertionError: wrong error\n'
                   'FAILED test_answer.py::test_error - AssertionError: Regex pattern did not match\n1 failed\n'}
    assert verify.assertion_failure(run)
    run['tail'] = 'E AttributeError: missing\nFAILED test_answer.py::test_error - AttributeError: missing\n1 failed\n'
    assert not verify.assertion_failure(run)
