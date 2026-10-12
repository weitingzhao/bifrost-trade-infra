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
import ast
import importlib

from mutants import MUTANTS
from mutant_proof import instrument
from mutagen import EXCLUSIONS, PATH_FILES, generate
from mutants_equivalent import EQUIVALENT, UNREACHABLE

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
        digest = ""
        hits = 0
        if not named and not failed:
            digest = _corpus(folder)
            if item['name'] in EQUIVALENT:
                target.write_text(instrument((HERE / item['file']).read_text(), item['source']))
                hits = _hits(folder, item['file'])
        return item, failed, digest, hits


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
    only_a = generate({"fold.py": "def a(x):\n    if x == 1:\n        return 1\n    return 0\ndef b(y):\n    if y == 2:\n        return 2\n    return 0\n"}, only="fold.py:a")
    assert only_a and {item['function'] for item in only_a} == {'a'}
    from mutant_proof import instrument
    negated = next(item for item in only_a if item['kind'] == 'negate')
    namespace = {}
    exec(instrument("def a(x):\n    if x == 1:\n        return 1\n    return 0\ndef b(y):\n    if y == 2:\n        return 2\n    return 0\n", negated['source']), namespace)
    assert namespace['a'](1) == 0 and namespace['_MUTANT_PROBE_HITS'] >= 1
    from mutants_equivalent import EQUIVALENT, UNREACHABLE
    assert not set(EQUIVALENT) & set(UNREACHABLE)
    assert len(set(EQUIVALENT.values())) == len(EQUIVALENT)
    for cite in UNREACHABLE.values():
        if cite.startswith("constant:"):
            assert _constant_dead(cite) is None, cite
        elif cite.startswith("subset:"):
            assert _subset_dead(cite) is None, cite
        else:
            assert cite.count(":") == 1, cite


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


def _hits(folder: Path, filename: str) -> int:
    """Run the round-7 checks on an instrumented mutant and return the probe count."""
    module = filename[:-3]
    script = (
        "import test_round7\n"
        "import test_round8\n"
        f"import {module}\n"
        "test_round7.run_checks()\n"
        "test_round8.run_checks()\n"
        f"print({module}._MUTANT_PROBE_HITS)\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], cwd=folder, capture_output=True, text=True, env={
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": os.environ.get("PATH", ""),
    }, timeout=MUTANT_TIMEOUT_S)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return int(proc.stdout.strip().splitlines()[-1])


def _site_line(name: str) -> tuple[str, str]:
    parts = name.split(":")
    return parts[0], parts[-4]


def _constant_dead(cite: str) -> str | None:
    """None when the named module constants have the value that kills the branch.

    ``constant:survive.SUMMARY_GAP_3+survive.SUMMARY_GAP_5=0`` is read from the
    imported module. A mismatch is an error string.
    """
    body = cite[len("constant:"):]
    names, expected = body.split("=")
    expected_value = ast.literal_eval(expected)
    for qual in names.split("+"):
        module_name, attr = qual.split(".")
        module = importlib.import_module(module_name)
        if getattr(module, attr) != expected_value:
            return f"{qual} is {getattr(module, attr)!r}, not {expected_value!r}"
    return None


def _subset_dead(cite: str) -> str | None:
    """None when the first module constant is a subset of the second.

    ``subset:model.APPROVAL_TERMINAL<=model.APPROVAL_STATES`` is read from the
    imported modules. Membership in the smaller set then cannot change a
    conjunction that also requires membership in the larger one.
    """
    body = cite[len("subset:"):]
    left, right = body.split("<=")
    smaller = _module_attr(left)
    larger = _module_attr(right)
    if not isinstance(smaller, set) or not isinstance(larger, set):
        return f"{cite} is not a pair of sets"
    if not smaller <= larger:
        return f"{left} is not a subset of {right}"
    return None


def _module_attr(qual: str):
    module_name, attr = qual.split(".")
    return getattr(importlib.import_module(module_name), attr)


def test_every_mutant_fails_its_tests():
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, failed, _digest, _hits in pool.map(lambda item: _run(item, True), MUTANTS):
            print(f"{item['name']} → {', '.join(sorted(failed))}", flush=True)
    print(f'legacy: {len(MUTANTS)} killed; {time.monotonic() - started:.2f}s', flush=True)


def test_generated_mutants():
    """Killed, equivalent-shown, or unreachable-shown. Anything else fails the run."""
    if os.environ.get('RECORDER_MUTANTS') != '1':
        return
    only = os.environ.get('RECORDER_MUTANT_ONLY', '')
    items = generate({file: (HERE / file).read_text() for file in PATH_FILES}, only=only)
    names = {item['name'] for item in items}
    if not only:
        assert set(EQUIVALENT) <= names
        assert set(UNREACHABLE) <= names
    baseline_digest = _corpus(HERE)
    _baseline, failed, _digest, _hits = _run(dict(file='fold.py', source=(HERE / 'fold.py').read_text(), name='baseline'))
    assert not failed, failed
    started = time.monotonic()
    killed = 0
    shown = []
    unproven = []
    differed = []
    survivors = []
    pending_unreach = []
    unreachable = []
    bad_cite = []
    killed_at = set()
    killed_kind = Counter()
    killed_function = Counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for item, failed, digest, hits in pool.map(_run, items):
            name = item['name']
            if failed:
                killed += 1
                killed_at.add(_site_line(name))
                killed_kind[item['kind']] += 1
                killed_function[item['function']] += 1
                print(f"generated {name} → killed", flush=True)
                continue
            if digest != baseline_digest:
                differed.append(name)
                print(f"generated {name} → differed", flush=True)
                continue
            if name in EQUIVALENT:
                if hits > 0:
                    shown.append(name)
                    print(f"equivalent {name}: {EQUIVALENT[name]}", flush=True)
                else:
                    unproven.append(name)
                    print(f"unproven {name}", flush=True)
                continue
            if name in UNREACHABLE:
                cite = UNREACHABLE[name]
                if cite.startswith("constant:"):
                    error = _constant_dead(cite)
                    if error is None:
                        unreachable.append(name)
                        print(f"unreachable-constant {name}: {cite}", flush=True)
                    else:
                        bad_cite.append(f"{name} cites {cite}: {error}")
                    continue
                if cite.startswith("subset:"):
                    error = _subset_dead(cite)
                    if error is None:
                        unreachable.append(name)
                        print(f"unreachable-subset {name}: {cite}", flush=True)
                    else:
                        bad_cite.append(f"{name} cites {cite}: {error}")
                    continue
                pending_unreach.append(name)
                print(f"unreachable-pending {name}: {cite}", flush=True)
                continue
            survivors.append(name)
            print(f"generated {name} → SURVIVED | {item['before']!r} => {item['after']!r}", flush=True)
    for name in pending_unreach:
        file_name, line = UNREACHABLE[name].split(":")
        if (file_name, line) in killed_at:
            unreachable.append(name)
        else:
            bad_cite.append(f"{name} cites {UNREACHABLE[name]}")
    print(f"generated: {len(items)}", flush=True)
    print(f"killed: {killed}", flush=True)
    print(f"equivalent-shown: {len(shown)}", flush=True)
    print(f"unreachable-shown: {len(unreachable)}", flush=True)
    print(f"differed: {len(differed)}", flush=True)
    print(f"unproven: {len(unproven)}", flush=True)
    print(f"bad citations: {len(bad_cite)}", flush=True)
    print(f"survivors: {len(survivors)}", flush=True)
    print(f"killed kinds: {dict(killed_kind)}", flush=True)
    print(f"killed by function: {dict(killed_function)}", flush=True)
    print(f"mutant run: {time.monotonic() - started:.2f}s", flush=True)
    for name in survivors:
        print(f"survivor {name}", flush=True)
    for name in unproven + differed + bad_cite:
        print(f"not shown {name}", flush=True)
    assert not survivors, survivors
    assert not unproven, unproven
    assert not differed, differed
    assert not bad_cite, bad_cite
