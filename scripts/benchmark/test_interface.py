"""TD-373: the declarations a fix's tests call that the parent lacks, and the
repositories its TypeScript links beside it."""
import json
import os
import shutil
import subprocess

import pytest

from test_benchmark import repo as repo, write, commit, git, pick
import interface


def candidate(repo, message, language, before, after):
    """Two commits: the parent with before, the fix with after ({path: text});
    the candidate of the fix in language, as pick.py makes it."""
    for path, text in before.items():
        write(repo, path, text)
    commit(repo, 'Initial', list(before))
    for path, text in after.items():
        write(repo, path, text)
    sha = commit(repo, message, list(after))
    return next(c for c in pick.candidates_for_commit(repo, sha) if c['language'] == language)


@pytest.mark.skipif(not shutil.which('go'), reason='Go executable unavailable')
def test_go_new_changed_and_unchanged(repo):
    old = ('package calc\n\nimport "regexp"\n\ntype Old struct{ A int }\n\nvar Limit = 3\n\n'
           'func Same(x int) int { return x }\n\nfunc Changed(x int) int { return x }\n\n'
           'func helper() int { return 1 }\n')
    new = ('package calc\n\nimport "regexp"\n\ntype Old struct {\n\tA int\n\tAdded string\n}\n\nvar Limit = 4\n\n'
           'type rewrite struct {\n\tre    *regexp.Regexp\n\talias map[string]string\n}\n\n'
           'func newRewrite() *rewrite { return &rewrite{} }\n\nfunc (r *rewrite) apply(s string) string { return s }\n\n'
           'func Same(x int) int { return x }\n\nfunc Changed(x int, y string) (int, error) {\n\treturn x, nil\n}\n\n'
           'func helper() int { return 2 }\n\nfunc Unused() {}\n')
    test = ('package calc\n\nimport "testing"\n\nfunc TestRegression(t *testing.T) {\n\tr := newRewrite()\n'
            '\t_ = r.apply("x")\n\t_ = r.alias\n\t_, _ = Changed(1, "a")\n\t_ = Same(1) + helper() + Limit\n'
            '\t_ = Old{A: 1, Added: "y"}\n}\n')
    c = candidate(repo, 'fix: review 271 A1', 'go',
                  {'go.mod': 'module fixture\n\ngo 1.20\n', 'calc/calc.go': old},
                  {'calc/calc.go': new, 'calc/calc_test.go': test})
    got = interface.interface(c)
    text = '\n'.join(got)
    assert 'func newRewrite() *rewrite' in text
    assert 'func (r *rewrite) apply(s string) string' in text
    assert 'type rewrite struct {\n\talias map[string]string\n\t// other fields of your choosing\n}' in text
    assert '// calc (package calc), changed from what this checkout has\nfunc Changed(x int, y string) (int, error)' in text
    assert '// calc (package calc), in type Old\nAdded string' in text
    # unchanged, a body that changed, a value that changed, unused
    for absent in ('func Same', 'func helper', 'Limit', 'Unused'):
        assert absent not in text, absent


def test_python_new_changed_and_new_module(repo):
    old = 'def fold(events):\n    return {}\n\nLIMIT = 3\n\nclass Store:\n    def get(self, key):\n        return None\n'
    new = ('def fold(events, now, *, unread=0) -> dict:\n    return {}\n\nLIMIT = 4\n\n'
           'class Store:\n    def get(self, key):\n        return 1\n\n    def seal(self, document: dict) -> "Folded":\n        return None\n\n'
           'class Folded:\n    def __init__(self, doc):\n        self._doc = doc\n\n    def document(self):\n        return self._doc\n\n'
           'def folded_for_test(document) -> Folded:\n    return Folded(document)\n\ndef unused():\n    pass\n')
    test = ('from recorder.read import fold, folded_for_test, LIMIT, Store\nfrom recorder.extra import added\n\n'
            'def test_regression():\n    assert fold([], 1, unread=2) == {}\n    assert folded_for_test({}).document() == {}\n'
            '    assert Store().seal({}) is None and Store().get(1) and LIMIT and added()\n')
    c = candidate(repo, 'fix: regression test', 'python', {'recorder/read.py': old},
                  {'recorder/read.py': new, 'recorder/extra.py': 'def added():\n    return 1\n',
                   'recorder/test_read.py': test})
    text = '\n'.join(interface.interface(c))
    assert 'def fold(events, now, *, unread=0) -> dict:  # changed from what this checkout has' in text
    assert 'class Folded:\n    def document(self):' in text
    assert 'def folded_for_test(document) -> Folded:' in text
    assert "class Store:\n    def seal(self, document: dict) -> 'Folded':" in text
    assert '# recorder/extra.py (a new module)\ndef added():' in text
    for absent in ('LIMIT', 'def get', 'unused', '_doc'):
        assert absent not in text, absent


def test_shell_functions_variables_and_options(repo):
    old = '#!/usr/bin/env bash\nstep_creds() {\n  src=~agent/.config/creds\n}\ncase "$1" in run) step_creds ;; esac\n'
    new = ('#!/usr/bin/env bash\nstep_creds() {\n  dir=${CREDS_DIR:-~agent/.config} # a test points elsewhere\n'
           '  [ "${OTHER_KNOB:-}" ] && [ "$HOME" ] && :\n}\nsend_secret() {\n  :\n}\nfail() {\n  :\n}\ncase "$1" in run) step_creds ;; --dry-run) : ;; esac\n')
    test = ('import subprocess\n\ndef test_creds_regression():\n'
            '    subprocess.run(["bash", "tool.sh", "--dry-run"], env={"CREDS_DIR": "/x"})\n'
            '    assert "send_secret" in open("tool.sh").read(), "fail"\n')
    c = candidate(repo, 'fix: regression test for tool.sh', 'shell', {'tool.sh': old},
                  {'tool.sh': new, 'test_tool.py': test})
    text = '\n'.join(interface.interface(c))
    assert 'reads the environment variable CREDS_DIR, which the tests set' in text
    assert '~agent/.config' not in text  # the line that reads it is the change's
    assert 'send_secret()  # a new function' in text
    assert 'fail()' not in text and 'HOME' not in text
    assert '# tool.sh takes the new option --dry-run' in text
    assert 'OTHER_KNOB' not in text and 'step_creds' not in text


def test_typescript_exports(repo):
    old = ("export const GROUP = 'a'\n\nexport function rows(input: string[]): string[] {\n  return input\n}\n"
           "export interface Row {\n  id: string\n}\n")
    new = ("export const GROUP = 'b'\n\nexport const FAILED = '__failed__'\n\n"
           "export function rows(input: string[], failed = false): string[] {\n  return input\n}\n"
           "export interface Row {\n  id: string\n  failed?: boolean\n}\n\nexport function unused(): void {}\n")
    test = ("import { describe, it, expect } from 'vitest'\nimport { rows, FAILED, GROUP, type Row } from './model'\n"
            "import { panel } from '@/pages/panel'\n\ndescribe('rows', () => { it('keeps a failed row', () => {\n"
            "  const r: Row = { id: 'x', failed: true }\n  expect(rows([FAILED], true)).toEqual([FAILED]); expect(GROUP).toBe('b'); panel(r)\n}) })\n")
    c = candidate(repo, 'fix: regression test', 'ts',
                  {'package.json': '{"name": "x"}\n', 'src/model.ts': old},
                  {'src/model.ts': new, 'src/pages/panel.ts': 'export function panel(r: unknown) {\n  return r\n}\n',
                   'src/model.test.ts': test})
    text = '\n'.join(interface.interface(c))
    assert 'export const FAILED = …' in text and '__failed__' not in text
    assert ('export function rows(input: string[], failed = false): string[]  '
            '// changed from what this checkout has') in text
    assert 'export interface Row {\n  id: string\n  failed?: boolean\n}  // changed from what this checkout has' in text
    assert '// src/pages/panel.ts (a new module)\nexport function panel(r: unknown)' in text
    assert "GROUP = 'b'" not in text and 'unused' not in text


def test_siblings_at_the_fix_time(tmp_path):
    def init(path):
        path.mkdir()
        git(path, 'init', '-b', 'main')
        git(path, 'config', 'user.name', 'Benchmark Fixture')
        git(path, 'config', 'user.email', 'fixture@example.invalid')
        git(path, 'config', 'commit.gpgsign', 'false')
        return path

    ui, app = init(tmp_path / 'bifrost-ui'), init(tmp_path / 'bifrost-trade-frontend')
    def dated(path, name, when, text=None):
        write(path, name, text or when)
        subprocess.run(['git', '-C', str(path), 'add', name], check=True)
        subprocess.run(['git', '-C', str(path), 'commit', '-qm', name], check=True,
                       env={**os.environ, 'GIT_COMMITTER_DATE': when, 'GIT_AUTHOR_DATE': when})
        return git(path, 'rev-parse', 'HEAD')

    early = dated(ui, 'a.txt', '2026-10-01T10:00:00Z')
    dated(ui, 'b.txt', '2026-10-03T10:00:00Z')
    fix = dated(app, 'package.json', '2026-10-02T10:00:00Z',
                json.dumps({'dependencies': {'@bifrost/ui': 'file:../bifrost-ui', 'react': '^19'}}))
    c = {'language': 'ts', 'repo': str(app), 'fix_commit': fix, 'tests_to_run': [{'cwd': '.', 'argv': []}]}
    assert interface.siblings(c) == [{'repo': 'bifrost-ui', 'commit': early}]
    assert interface.siblings(dict(c, language='go')) == []
    fix = dated(app, 'package.json', '2026-10-04T10:00:00Z', json.dumps({'dependencies': {'x': 'file:../../elsewhere'}}))
    with pytest.raises(ValueError):
        interface.siblings(dict(c, fix_commit=fix))


def test_bounded_and_required_names():
    entries = ['x' * 5000, 'func Added() int', 'func Added() int']
    out = interface.bounded(entries, ['Added', 'handIn'])
    assert len(out[0]) <= interface.MAX_ENTRY and out[1] == 'func Added() int'
    assert out[2].startswith('handIn (the tests call it')
    many = interface.bounded([f'decl {i} ' + 'y' * 3000 for i in range(20)])
    assert sum(map(len, many)) <= interface.MAX_TOTAL
    assert many[-1].startswith('and more declarations')


def test_task_text_drops_known_trailer_blocks():
    message = ('subject\n\nbody\n\nTests: TestA, TestB\n\nClaude-Session: local_29f61f03-92c1-4662-a1ec-015a773a4eb7\n'
               'Claude-Transcript: e8aa54eb-e0c2-47cb-9ead-e9ec043fcead\nChange-Id: I93b84a9f5be685b4f08015c79fb29608f1f0521f\n'
               'Work: W-31, TD-370\n\nCo-Authored-By: C <c@example.invalid>\n')
    assert pick.task_text(message) == 'subject\n\nbody\n\nTests: TestA, TestB'
    # Review 292 B7: a paragraph that only starts like a trailer is the task's.
    prose = ('fix: description\n\nWork: retry a partial batch after a crash\n  Preserve its completed rows.\n\n'
             'Co-Authored-By: A <a@example.invalid>')
    assert pick.task_text(prose) == ('fix: description\n\nWork: retry a partial batch after a crash\n'
                                     '  Preserve its completed rows.')
    assert pick.task_text('fix: x\n\nChange-Id: soon\n\nCo-Authored-By: A <a@example.invalid>') == 'fix: x\n\nChange-Id: soon'


def test_nothing_of_the_answer(repo):
    """Review 292 B2: a test that looks for a line of code, a function value,
    a shell function that reads a new variable: the interface names them and
    gives no body."""
    old = 'def cap(x):\n    return x\n'
    new = 'def cap(x):\n    return min(x, 100)\n\nanswer = lambda x: min(x, 100)\n\nLABEL = "over the cap"\n'
    test = ('import inspect\nimport cap as m\n\ndef test_cap_regression():\n'
            '    assert "return min(x, 100)" in inspect.getsource(m)\n    assert m.answer(200) == 100\n'
            '    assert m.LABEL == "over the cap"\n')
    c = candidate(repo, 'fix: regression test', 'python', {'cap.py': old}, {'cap.py': new, 'test_cap.py': test})
    text = '\n'.join(interface.interface(c))
    assert 'answer = lambda x: …' in text and 'LABEL = …' in text
    assert '"over the cap"' in text  # a string the fix wrote and the test compares
    assert 'min(x, 100)' not in text


def test_nothing_of_the_answer_in_shell_go_and_ts(repo):
    sh_old = '#!/usr/bin/env bash\nf() { :; }\n'
    sh_new = '#!/usr/bin/env bash\nf() { test "${CHECK_MODE:-}" = 1 && printf correct; }\n'
    test = ('import subprocess\n\ndef test_mode_regression():\n'
            '    assert subprocess.run(["bash", "mode.sh"], env={"CHECK_MODE": "1"}).returncode == 0\n')
    c = candidate(repo, 'fix: regression test for mode.sh', 'shell', {'mode.sh': sh_old}, {'mode.sh': sh_new, 'test_mode.py': test})
    text = '\n'.join(interface.interface(c))
    assert 'CHECK_MODE' in text and 'printf' not in text and 'correct' not in text


@pytest.mark.skipif(not shutil.which('go'), reason='Go executable unavailable')
def test_go_values_embedded_and_interface_methods(repo):
    old = 'package calc\n\ntype I interface {\n\tF() int\n}\n'
    new = ('package calc\n\nimport "sync"\n\ntype I interface {\n\tF() string\n}\n\n'
           'var New = func(x int) int { return x + 7 }\n\ntype Guard struct {\n\tsync.Mutex\n\tn int\n}\n')
    test = ('package calc\n\nimport "testing"\n\nfunc TestGuard(t *testing.T) {\n\tvar g Guard\n\tg.Lock()\n'
            '\tdefer g.Unlock()\n\tvar i I\n\t_ = i.F\n\tif New(1) != 8 {\n\t\tt.Fatal("x")\n\t}\n}\n')
    c = candidate(repo, 'fix: review 271 A2', 'go', {'go.mod': 'module fixture\n\ngo 1.20\n', 'calc/calc.go': old},
                  {'calc/calc.go': new, 'calc/calc_test.go': test})
    text = '\n'.join(interface.interface(c))
    assert 'var New func(x int) int' in text and 'x + 7' not in text
    assert 'type Guard struct {\n\tsync.Mutex\n\t// other fields of your choosing\n}' in text
    assert '// calc (package calc), in type I, changed from what this checkout has\nF() string' in text


def test_typescript_default_arrow_and_index(repo):
    old = 'export const scale = (x: number): number => x\n'
    new = ('export const scale = (x: number, by: number): number => x * by\n\n'
           'export default function Panel(props: { rows: number }): string {\n  return ""\n}\n')
    impl = 'export function added(n: number): number {\n  return n + 1\n}\n'
    test = ("import Panel from './panel'\nimport { scale } from './panel'\nimport { added } from './lib'\n\n"
            "it('scales a regression', () => { expect(scale(2, 3) + added(1) + Panel({ rows: 1 }).length).toBe(8) })\n")
    c = candidate(repo, 'fix: regression test', 'ts', {'package.json': '{"name": "x"}\n', 'src/panel.ts': old},
                  {'src/panel.ts': new, 'src/lib/index.ts': "export { added } from './impl'\n", 'src/lib/impl.ts': impl,
                   'src/panel.test.ts': test})
    text = '\n'.join(interface.interface(c))
    assert 'export const scale = (x: number, by: number): number => …  // changed from what this checkout has' in text
    assert 'export default function Panel(props: { rows: number }): string' in text
    assert '// src/lib/impl.ts (a new module)\nexport function added(n: number): number' in text
    assert 'x * by' not in text and 'n + 1' not in text


def test_bounded_in_bytes_and_required_kept():
    out = interface.bounded(['中' * 3000])
    assert len(out[0].encode()) <= interface.MAX_ENTRY
    many = [f'decl {i} ' + 'y' * 3990 for i in range(9)] + ['func Required() int']
    kept = interface.bounded(many, ['Required'])
    assert 'func Required() int' in kept and sum(len(e.encode()) for e in kept) <= interface.MAX_TOTAL
    with pytest.raises(ValueError):
        interface.bounded([f'Required{i} ' + 'z' * 3990 for i in range(9)], [f'Required{i}' for i in range(9)])


def test_a_comment_is_not_a_string_and_an_anonymous_default(repo):
    """Review 293 B2, B3: a line of code quoted in a comment is not a text the
    fix wrote; a default export without a name has its signature."""
    old = ('export function cap(x: number) { return x }\n'
           'export default function (x: number): number { return x }\n')
    new = ('// "return Math.min(x, 100)"\nexport function cap(x: number) { return Math.min(x, 100) }\n'
           'export default function (x: number, by: number): number { return x * by }\n')
    test = ("import Calc, { cap } from './panel'\nimport source from './panel.ts?raw'\n\n"
            "it('caps a regression', () => {\n  expect(source).toContain(\"return Math.min(x, 100)\")\n"
            "  expect(cap(200) + Calc(2, 3)).toBe(106)\n})\n")
    arrow = "export default (rows: string[]): number => rows.length + 7\n"
    c = candidate(repo, 'fix: regression test', 'ts', {'package.json': '{"name": "x"}\n', 'src/panel.ts': old},
                  {'src/panel.ts': new, 'src/count.ts': arrow, 'src/panel.test.ts': test + "import count from './count'\n"})
    text = '\n'.join(interface.interface(c))
    assert 'Math.min' not in text and 'x * by' not in text and 'length + 7' not in text
    assert ('export default function (x: number, by: number): number  // changed from what this checkout has') in text
    assert '// src/count.ts (a new module)\nexport default (rows: string[]): number => …' in text
    assert interface.literals('x.sh', 'echo "$f did not reach $u" # "not a string"\n') == ['', ' did not reach ', '']
