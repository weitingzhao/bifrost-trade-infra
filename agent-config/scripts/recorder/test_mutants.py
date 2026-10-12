"""Named failures and exhaustive AST mutations; slow gate: RECORDER_MUTANTS=1.

Generated mutants run the default suite minus enumeration, fuzz, and Go fixture
families, exhaustive field-type fuzz, physical 16 MiB/20k writer capacity,
writer concurrency, plus offline release integration/scan in test_guard.py. Those independent slow families remain in both acceptance suite runs.
Generated runs stop after the first genuine FAILED test; survivors run all selected tests.
Each subprocess has its own package copy and cannot modify this working tree.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from mutants import MUTANTS
from mutagen import TARGETS, generate
from mutants_equivalent import EQUIVALENT

HERE = Path(__file__).resolve().parent
SLOW = ('not enumeration and not fuzz and not handleput and not fixtures_match '
        'and not every_field_type_mutant and not sixteen_mebibytes '
        'and not twenty_thousand and not held_lock and not two_processes')


def _failures(proc):
    output = proc.stdout + '\n' + proc.stderr
    failed = {line[len('FAILED '):].split(' - ', 1)[0] for line in output.splitlines() if line.startswith('FAILED ')}
    # Exit 1 is ordinary test failure; exit 2–5, ERROR and collection errors
    # must never masquerade as a killed mutant.
    assert proc.returncode in (0, 1), output
    assert not any(line.startswith(('ERROR ', 'ERRORS', 'E   SyntaxError')) for line in output.splitlines()), output
    assert 'error during collection' not in output and 'errors during collection' not in output, output
    assert (proc.returncode == 1) == bool(failed), output
    return failed


def _run(item, named=False):
    env = {k: v for k, v in os.environ.items() if k not in ('RECORDER_MUTANTS', 'RECORDER_FULL')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / 'bifrost-trade-infra' / 'agent-config' / 'scripts' / 'recorder'
        shutil.copytree(HERE, folder, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        (Path(tmp) / 'bifrost-platform').symlink_to(HERE.parents[2].parent / 'bifrost-platform', target_is_directory=True)
        target = folder / item['file']
        target.write_text(target.read_text().replace(item['old'], item['new'], 1) if named else item['source'])
        args = item['must_fail'] if named else ['--maxfail=1', '--ignore=test_mutants.py', '--ignore=test_guard.py', '-k', SLOW]
        proc = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=no', '-p', 'no:cacheprovider', *args],
                              cwd=folder, capture_output=True, text=True, env=env)
        failed = _failures(proc)
        if named:
            assert set(item['must_fail']) <= failed, (item['name'], failed, proc.stdout, proc.stderr)
        return item, failed


def test_mutant_anchors_are_unique():
    names = [item['name'] for item in MUTANTS]
    assert len(names) == len(set(names)) == 122
    for item in MUTANTS:
        assert (HERE / item['file']).read_text().count(item['old']) == 1, item['name']
        assert item['old'] != item['new'] and item['must_fail']
    collected = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider'],
                               cwd=HERE, capture_output=True, text=True)
    assert collected.returncode == 0, collected.stdout + collected.stderr
    have = set(collected.stdout.splitlines())
    assert all(node in have for item in MUTANTS for node in item['must_fail'])


def test_meta_rejects_collection_syntax_missing_nodes_and_unrelated_failures():
    for code, output in ((2, 'ERROR test.py'), (4, 'ERROR: not found: test.py::missing'),
                         (1, 'ERROR test.py::x'), (1, 'SyntaxError: invalid syntax')):
        with pytest.raises(AssertionError):
            _failures(subprocess.CompletedProcess([], code, output, ''))
    assert _failures(subprocess.CompletedProcess([], 1, 'FAILED test.py::named - assert', '')) == {'test.py::named'}
    assert _failures(subprocess.CompletedProcess([], 0, '1 passed', '')) == set()
    assert _failures(subprocess.CompletedProcess([], 1, 'FAILED test.py::named[bad host] - assert', '')) == {'test.py::named[bad host]'}


def test_generator_sites_are_unique_complete_and_compilable():
    import ast
    for filename, wanted in TARGETS.items():
        tree = ast.parse((HERE / filename).read_text())
        have = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        have |= {cls.name + "." + node.name for cls in tree.body if isinstance(cls, ast.ClassDef)
                 for node in cls.body if isinstance(node, ast.FunctionDef)}
        assert set(wanted) <= have
    sources = dict.fromkeys(TARGETS, "")
    sources["fold.py"] = "def _apply_unrecorded(x, y):\n    if x == 1 and y in ('a', 'b'):\n        return 1\n    return 0\n"
    items = generate(sources)
    assert len({item['name'] for item in items}) == len(items)
    assert Counter(item['kind'] for item in items) == dict(operand=2, negate=1, compare=2, constant=6, guard_pass=1)
    for item in items:
        compile(item['source'], item['file'], 'exec')


def test_every_mutant_fails_its_tests():
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item, failed in pool.map(lambda item: _run(item, True), MUTANTS):
            print(f"{item['name']} → {', '.join(sorted(failed))}", flush=True)
    print(f'legacy: {len(MUTANTS)} killed; {time.monotonic() - started:.2f}s', flush=True)


def test_generated_mutants():
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    items = generate({file: (HERE / file).read_text() for file in TARGETS})
    assert set(EQUIVALENT) <= {item['name'] for item in items}
    _baseline, failed = _run(dict(file='fold.py', source=(HERE / 'fold.py').read_text()))
    assert not failed, failed
    started = time.monotonic()
    survivors = []
    killed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for item, failed in pool.map(_run, items):
            if failed:
                killed += 1
            else:
                survivors.append(item['name'])
            print(f"generated {item['name']} → {'killed' if failed else 'SURVIVED'} | FAILED={sorted(failed)} | {item['before']!r} => {item['after']!r}", flush=True)
    unexplained = set(survivors) - set(EQUIVALENT)
    print(f'generated kinds: {dict(Counter(item["kind"] for item in items))}', flush=True)
    print(f'generated: {len(items)} total; {killed} killed; {len(survivors)} survived; {len(unexplained)} unexplained; {time.monotonic() - started:.2f}s', flush=True)
    for name in survivors:
        print(f'equivalent {name}: {EQUIVALENT.get(name, "MISSING TEST")}', flush=True)
    assert not unexplained, sorted(unexplained)
