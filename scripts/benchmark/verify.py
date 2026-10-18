#!/usr/bin/env python3
"""Verify one JSON/JSONL candidate (use --index for JSONL); execute trusted history only."""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import sys
import tarfile
import tempfile

# pick loads subprocess without allowing the sibling select.py to shadow stdlib.
from pick import candidates_for_commit
from missing_symbols import missing_symbols, source_delta
import subprocess


def export_tree(repo, commit, destination):
    archive = subprocess.run(['git', '-C', str(repo), 'archive', '--format=tar', commit],
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        members = tree.getmembers()
        root = destination.resolve()
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe archive path')
            target = destination / item.name
            if not target.resolve().is_relative_to(root):
                raise ValueError('archive path escapes work directory')
            if item.issym():
                if not (target.parent / item.linkname).resolve().is_relative_to(root):
                    raise ValueError('archive symlink escapes work directory')
            elif not (item.isdir() or item.isfile()):
                raise ValueError('unsupported archive member')
        # Files first: never write through a symlink supplied by the archive.
        for item in members:
            if item.issym():
                continue
            target = destination / item.name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tree.extractfile(item).read())
                target.chmod(item.mode & 0o777)
        for item in members:
            if item.issym():
                target = destination / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(item.linkname)


def run_test(spec, tree, work, timeout):
    env = os.environ.copy()
    env.update({'GOFLAGS': '-mod=mod', 'GOCACHE': str(work / 'go-cache'),
                'npm_config_offline': 'true', 'npm_config_userconfig': os.devnull,
                'npm_config_cache': str(work / 'npm-cache'),
                'npm_config_update_notifier': 'false', 'npm_config_audit': 'false',
                'CI': 'true', 'NO_COLOR': '1',
                'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOTOOLCHAIN': 'local',
                'PYTHONDONTWRITEBYTECODE': '1'})
    # Prefer archived code over editable installations in the source checkout.
    env['PYTHONPATH'] = os.pathsep.join(str(p.resolve()) for p in (tree, tree / 'src')
                                      if p.is_dir())
    env.setdefault('GOMAXPROCS', '2')
    argv = spec['argv']
    record = {'cwd': spec['cwd'], 'argv': argv, 'returncode': None,
              'timed_out': False, 'tail': ''}
    # Disk-backed capture bounds memory even when a broken test floods stdout.
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(argv, cwd=tree / spec['cwd'], env=env,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                record['returncode'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            output.seek(0, os.SEEK_END)
            record['truncated'] = output.tell() > 12000
            output.seek(max(0, output.tell() - 12000))
            record['tail'] = output.read().decode(errors='replace')
        except OSError as exc:
            record['tail'] = str(exc)
    return record


def passed(run):
    if run['timed_out'] or run['returncode'] != 0:
        return False
    argv, output = run['argv'], run['tail']
    if argv[0] == 'go':
        return '[no tests to run]' not in output and '[no test files]' not in output
    if argv[0] == 'npx':
        return bool(re.search(r'Tests\s+.*\d+ passed', output))
    if argv[:3] == ['python3', '-m', 'pytest']:
        return bool(re.search(r'\b\d+ passed\b', output)) and not re.search(
            r'\b\d+ (?:skipped|xfailed|xpassed)\b', output)
    return True


def assertion_failure(run):
    if run['timed_out'] or run['returncode'] != 1:
        return False
    argv, output = run['argv'], run['tail']
    if argv[0] == 'go':
        return '--- FAIL:' in output and '[build failed]' not in output
    if argv[:3] == ['python3', '-m', 'pytest']:
        errors = re.findall(r'(?m)^(?:E\s+)?([\w.]*(?:Error|Exception)|SystemExit|KeyboardInterrupt):', output)
        summaries = re.findall(r'(?m)^FAILED [^\n]+$', output)
        # Chained exceptions inside pytest.raises are context; the terminal
        # assertion in pytest's summary determines the actual test failure.
        assertions = (all(re.search(r' - (?:AssertionError\b|assert\b|Failed\b)', line)
                          for line in summaries) if summaries else
                      all(error in ('AssertionError', 'Failed') for error in errors))
        return bool(re.search(r'\b\d+ failed\b', output)) and assertions and not re.search(
            r'\b\d+ errors?\b|ERROR collecting', output)
    if argv[0] == 'npx':
        return bool(re.search(r'Tests\s+.*\d+ failed', output)) and not re.search(
            r'Failed Suites|Cannot find|Failed to resolve|Unhandled Error', output)
    # A bash harness communicates failure by exit 1; other exit codes are setup errors.
    return argv[0] == 'bash'


def link_node_modules(repo, tree, runs):
    linked = set()
    for run in runs:
        if run['argv'][0] != 'npx':
            continue
        for test in run['argv'][3:]:
            directory = (PurePosixPath(run['cwd']) / test).parent
            found = False
            while True:
                source = repo / directory / 'node_modules'
                if source.is_dir():
                    destination = tree / directory / 'node_modules'
                    if destination not in linked:
                        if destination.exists() or destination.is_symlink():
                            raise ValueError('export already contains node_modules')
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.symlink_to(source, target_is_directory=True)
                        linked.add(destination)
                    found = True
                    break
                if str(directory) == '.':
                    break
                directory = directory.parent
            if not found:
                raise ValueError(f'cannot link node_modules from source checkout for {test}')


def verify(candidate, timeout=120, work_dir=None):
    result = dict(candidate, status='rejected', reason='', before=[], after=[])
    try:
        if timeout <= 0:
            raise ValueError('timeout must be positive')
        # Rebuild commands from pinned history rather than trusting JSON command text.
        matches = [c for c in candidates_for_commit(candidate['repo'], candidate['fix_commit'])
                   if c['language'] == candidate['language']
                   and c['test_files'] == candidate['test_files']]
        if len(matches) != 1:
            raise ValueError('candidate does not match eligible commit metadata')
        canonical = matches[0]
        if any(candidate.get(key) != canonical[key] for key in canonical):
            raise ValueError('candidate metadata or commands differ from pinned history')
        repo = Path(candidate['repo'])
        with tempfile.TemporaryDirectory(prefix='benchmark-', dir=work_dir) as temp:
            work = Path(temp)
            if work_dir is not None:
                # Go's content-addressed cache can safely serve successive replays.
                cache = Path(work_dir).resolve() / 'go-cache'
                cache.mkdir(exist_ok=True)
                (work / 'go-cache').symlink_to(cache, target_is_directory=True)
            before, after = work / 'before', work / 'after'
            before.mkdir()
            after.mkdir()
            export_tree(repo, candidate['parent'], before)
            export_tree(repo, candidate['fix_commit'], after)
            for name in candidate['test_files']:
                source, target = after / name, before / name
                if source.is_symlink() or not source.is_file():
                    raise ValueError('test overlay must be a regular file')
                if not target.resolve().is_relative_to(before.resolve()):
                    raise ValueError('test overlay escapes parent tree')
                if any(p.is_symlink() for p in [target, *target.parents]
                       if p.is_relative_to(before)):
                    raise ValueError('test overlay traverses a symlink')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                target.chmod(source.stat().st_mode & 0o777)
            runs = candidate['tests_to_run']
            for tree in (before, after):
                link_node_modules(repo, tree, runs)
            # Both phases are run even when the first phase is unsuitable.
            result['before'] = [run_test(r, before, work, timeout) for r in runs]
            result['after'] = [run_test(r, after, work, timeout) for r in runs]
            delta = source_delta(candidate)
            symbols = [missing_symbols(r, candidate, delta) for r in result['before']]
            failures = ['missing_symbol' if names else 'assertion' if assertion_failure(r) else None
                        for r, names in zip(result['before'], symbols)]
            for run, kind in zip(result['before'], failures):
                run['fails_by'] = kind
            if not all(passed(r) for r in result['after']):
                result['reason'] = 'fix tests did not pass (failure, setup error, empty run or timeout)'
            elif not all(failures):
                result['reason'] = 'parent tests must fail assertions or attributable missing symbols; already passing/setup errors/timeouts rejected'
            else:
                result.update(status='verified', reason='parent fails; fix passes',
                              fails_by='missing_symbol' if any(symbols) else 'assertion',
                              missing_symbols=sorted({name for names in symbols for name in names}))
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        result['reason'] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    try:
        rows = [json.loads(line) for line in args.candidate.read_text().splitlines() if line.strip()]
        if args.index < 0:
            raise ValueError('--index must be nonnegative')
        result = verify(rows[args.index], args.timeout, args.work_dir)
    except (ValueError, IndexError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(main())
