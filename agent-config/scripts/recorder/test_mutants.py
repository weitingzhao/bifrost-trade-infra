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
from mutagen import EXCLUSIONS, PATH_FILES, generate
from mutants_equivalent import EQUIVALENT

HERE = Path(__file__).resolve().parent
MUTANT_TIMEOUT_S = 90
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
        try:
            proc = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--tb=no', '-p', 'no:cacheprovider', *args],
                                  cwd=folder, capture_output=True, text=True, env=env, timeout=MUTANT_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(f'mutant hung and was not caught: {item["name"]}') from exc
        failed = _failures(proc)
        if named:
            assert set(item['must_fail']) <= failed, (item['name'], failed, proc.stdout, proc.stderr)
        digest = _corpus(folder) if not named and not failed else ""
        return item, failed, digest


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
    for filename in PATH_FILES:
        tree = ast.parse((HERE / filename).read_text())
        have = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        have |= {cls.name + "." + node.name for cls in tree.body if isinstance(cls, ast.ClassDef)
                 for node in cls.body if isinstance(node, ast.FunctionDef)}
        for key, reason in EXCLUSIONS.items():
            excluded_file, name = key.split(":", 1)
            if excluded_file == filename:
                assert name in have and reason, key
        for name in have:
            key = f"{filename}:{name}"
            assert key in EXCLUSIONS or name, key
    sources = dict.fromkeys(PATH_FILES, "")
    sources["fold.py"] = "def _apply_unrecorded(x, y):\n    if x == 1 and y in ('a', 'b'):\n        return 1\n    return 0\n"
    items = generate(sources)
    assert len({item['name'] for item in items}) == len(items)
    assert Counter(item['kind'] for item in items) == dict(operand=2, negate=1, compare=2, constant=6, guard_pass=1)
    for item in items:
        compile(item['source'], item['file'], 'exec')


def _corpus(folder: Path) -> str:
    """Byte digest of the public entries on a fixed corpus. A hang fails the run."""
    script = (
        "import hashlib\n"
        "from read import fold_total\n"
        "from publish import publish_total\n"
        "from harness import WORK, LogBuilder, _chain\n"
        "out = []\n"
        "def add(*args, **kwargs):\n"
        "    out.append(publish_total(*args, **kwargs))\n"
        "add(fold_total([], [], 1))\n"
        "add(fold_total([], [], 0), 'board', {'usage': {'a': 'x' * 210000}})\n"
        "add(fold_total([], [], 1), 'board', {'works': []})\n"
        "add(fold_total([], [], 1), 'board', {'usage': {'api_key': 'v', 'ok': 1}})\n"
        "add(fold_total([], [], 1, 1 << 53))\n"
        "log = LogBuilder()\n"
        "log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')\n"
        "log.add('owner_wait_opened', 'coordinator', at=10, wait_id='f1b2c3d4', title='a',\n"
        "        ref={'kind': 'none', 'id': 'c0ffee01'}, can_act='yes')\n"
        "log.add('owner_wait_opened', 'coordinator', at=20, wait_id='a2b2c3d4', title='b',\n"
        "        ref={'kind': 'none', 'id': 'c0ffee02'}, can_act='yes')\n"
        "add(fold_total([(WORK, _chain(log.events))], [], 20))\n"
        "print(hashlib.sha256(b'\\n'.join(out)).hexdigest())\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], cwd=folder, capture_output=True, text=True, env={
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.environ.get("PATH", ""),
    }, timeout=MUTANT_TIMEOUT_S)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def test_every_mutant_fails_its_tests():
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, failed, _digest in pool.map(lambda item: _run(item, True), MUTANTS):
            print(f"{item['name']} → {', '.join(sorted(failed))}", flush=True)
    print(f'legacy: {len(MUTANTS)} killed; {time.monotonic() - started:.2f}s', flush=True)


def test_generated_mutants():
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    items = generate({file: (HERE / file).read_text() for file in PATH_FILES})
    names = {item['name'] for item in items}
    assert set(EQUIVALENT) <= names
    baseline_digest = _corpus(HERE)
    _baseline, failed, _digest = _run(dict(file='fold.py', source=(HERE / 'fold.py').read_text(), name='baseline'))
    assert not failed, failed
    started = time.monotonic()
    survivors = []
    differed = []
    killed = 0
    killed_kind = Counter()
    killed_function = Counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, failed, digest in pool.map(_run, items):
            if failed:
                killed += 1
                killed_kind[item['kind']] += 1
                killed_function[item['function']] += 1
            elif digest != baseline_digest:
                differed.append(item['name'])
            else:
                survivors.append(item['name'])
            print(f"generated {item['name']} → {'killed' if failed else 'SURVIVED'} | FAILED={sorted(failed)} | {item['before']!r} => {item['after']!r}", flush=True)
        unexplained = (set(survivors) - set(EQUIVALENT)) | set(differed)
        for name in survivors:
            print(f'equivalent {name}: {EQUIVALENT.get(name, "MISSING TEST")}', flush=True)
        for name in differed:
            print(f'differed {name}', flush=True)
        print(f'generated kinds: {dict(Counter(item["kind"] for item in items))}', flush=True)
        print(f'killed kinds: {dict(killed_kind)}', flush=True)
        print(f'by function: {dict(Counter(item["function"] for item in items))}', flush=True)
        print(f'killed by function: {dict(killed_function)}', flush=True)
        print(f'generated: {len(items)} total; {killed} killed; {len(survivors)} survived; {len(differed)} differed; {len(unexplained)} unexplained; {time.monotonic() - started:.2f}s', flush=True)
        assert not unexplained, sorted(unexplained)
