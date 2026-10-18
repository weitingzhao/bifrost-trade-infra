#!/usr/bin/env python3
"""Find replayable regression candidates; stdout is JSONL, diagnostics stderr."""
import argparse
import ast
import collections
import difflib
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

# The required CLI name select.py must not shadow the stdlib select extension
# when subprocess imports selectors in a directly executed script.
_entry_path = sys.path.pop(0) if sys.path and Path(sys.path[0]).resolve() == Path(__file__).parent.resolve() else None
subprocess = importlib.import_module('subprocess')
if _entry_path is not None:
    sys.path.insert(0, _entry_path)

EVIDENCE = re.compile(r"fails? on (?:the )?old code|regression test|旧代码上失败|回归测试", re.I)
REVIEW = re.compile(r'\breview[ _-]*2\d{2}\b|(?:\bfix(?:es|ed)?\b|修复)[^\n]{0,100}\b[AB][1-9]\b|\b[AB][1-9]\b[^\n]{0,100}(?:\bfix(?:es|ed)?\b|修复)', re.I)
REVIEW_TEST = re.compile(r'(?:test[ _-]*review[ _-]*\d+|review[ _-]*\d+)', re.I)
ROOT = Path('/Users/vision-mac-trader/Desktop/stocks')
REPOS = ['bifrost-platform', 'bifrost-research', 'bifrost-trade-core',
         'bifrost-trade-api', 'bifrost-trade-worker', 'bifrost-trade-socket',
         'bifrost-trade-frontend', 'bifrost-trade-infra', 'bifrost-platform-plugin',
         'bifrost-platform-plugin-market-data', 'bifrost-platform-plugin-flex-query',
         'bifrost-ui']


def git(repo, *args, missing=False):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True)
    if result.returncode:
        if missing:
            return ''
        raise ValueError(result.stderr.decode(errors='replace').strip())
    return result.stdout.decode('utf-8', errors='replace')


def task_text(message):
    """Drop the final RFC-style trailer block, including folded continuations."""
    lines = message.strip().splitlines()
    trailer = re.compile(r'^[A-Za-z][A-Za-z0-9-]*:\s*.*$')
    for start in range(len(lines) - 1, -1, -1):
        if start == 0:  # A colon in the subject is not a trailer.
            continue
        if start and lines[start - 1].strip():
            continue
        block = lines[start:]
        if block and trailer.match(block[0]) and all(
                trailer.match(line) or line.startswith((' ', '\t')) for line in block):
            return '\n'.join(lines[:start]).rstrip()
    return message.strip()


def forbidden(path):
    parts = PurePosixPath(path).parts
    return any(p == 'k8s' or '.secret' in p.lower() or p.startswith('.env')
               for p in parts)


def test_language(path):
    name = PurePosixPath(path).name
    if name.endswith('_test.go'):
        return 'go'
    if re.fullmatch(r'.+\.test\.tsx?', name):
        return 'ts'
    if name.endswith('.py') and (name.startswith('test_') or name.endswith('_test.py')):
        return 'python'
    if name.endswith('.sh') and (name.startswith('test_') or name.endswith('_test.sh')):
        return 'shell'
    return None


def changed_lines(old, new):
    changed = set()
    for tag, _, _, start, end in difflib.SequenceMatcher(
            a=old.splitlines(), b=new.splitlines(), autojunk=False).get_opcodes():
        if tag != 'equal':
            changed.update(range(start + 1, max(start + 2, end + 1)))
    return changed


def python_names(text, lines):
    tree = ast.parse(text)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            if lines.intersection(range(start, node.end_lineno + 1)):
                names.append(node.name)
    return sorted(set(names))


def go_names(text, lines):
    # A Go top-level declaration starts in column zero; include a whole changed test.
    declarations = list(re.finditer(r'(?m)^(?:func|type|var|const)\b', text))
    names = []
    for i, decl in enumerate(declarations):
        end = declarations[i + 1].start() if i + 1 < len(declarations) else len(text)
        segment = text[decl.start():end]
        match = re.match(r'func\s+(Test[A-Z0-9_]\w*)\s*\(\s*\w+\s+\*testing\.T\s*\)', segment)
        start_line = text[:decl.start()].count('\n') + 1
        if match and lines.intersection(range(start_line, start_line + segment.count('\n') + 1)):
            names.append(match[1])
    return sorted(set(names))


def module_dir(repo, commit, package, marker='go.mod'):
    directory = PurePosixPath(package)
    while True:
        name = str(directory / marker)
        if git(repo, 'show', f'{commit}:{name}', missing=True):
            return str(directory)
        if str(directory) == '.':
            if marker != 'go.mod':
                return '.'
            raise ValueError(f'no go.mod above {package}')
        directory = directory.parent


def commands(repo, commit, language, tests, names):
    if language == 'go':
        packages = collections.defaultdict(set)
        for path in tests:
            packages[str(PurePosixPath(path).parent)].update(names[path])
        runs = []
        for package, functions in sorted(packages.items()):
            if not functions:
                raise ValueError(f'no changed Test function in {package}')
            module = module_dir(repo, commit, package)
            relative = PurePosixPath(package).relative_to(PurePosixPath(module))
            target = './' + (str(relative) if str(relative) != '.' else '')
            runs.append({'cwd': module, 'argv': ['go', 'test', target, '-run',
                         '^(' + '|'.join(sorted(functions)) + ')$', '-count=1']})
        return runs
    if language in ('python', 'shell') and all(p.endswith('.py') for p in tests):
        selected = sorted({n for path in tests for n in names[path]})
        if not selected:
            raise ValueError('no changed pytest test functions')
        return [{'cwd': '.', 'argv': ['python3', '-m', 'pytest', '-q', *tests,
                                      '-k', ' or '.join(selected)]}]
    if language == 'shell':
        return [{'cwd': '.', 'argv': ['bash', path]} for path in tests]
    projects = collections.defaultdict(list)
    for path in tests:
        project = module_dir(repo, commit, str(PurePosixPath(path).parent), 'package.json')
        projects[project].append(str(PurePosixPath(path).relative_to(PurePosixPath(project))))
    return [{'cwd': project, 'argv': ['npx', 'vitest', 'run', *files]}
            for project, files in sorted(projects.items())]


def candidates_for_commit(repo, commit):
    repo = Path(repo).resolve()
    metadata = git(repo, 'show', '-s', '--format=%H%n%P%n%B', commit).split('\n', 2)
    sha, parents, message = metadata
    # Merge parents are ambiguous replay bases; root commits have no base.
    if len(parents.split()) != 1:
        return []
    parent = parents.strip()
    paths = git(repo, 'show', '--format=', '--name-only', '--no-renames', '-z', sha).split('\0')
    paths = sorted({p for p in paths if p})
    if any(forbidden(p) for p in paths):
        return []
    non_tests = [p for p in paths if not test_language(p)]
    if not non_tests:
        return []
    groups = collections.defaultdict(list)
    names = {}
    review_test = False
    scripts = [p for p in non_tests if p.endswith('.sh')]
    for path in paths:
        language = test_language(path)
        if not language:
            continue
        new = git(repo, 'show', f'{sha}:{path}', missing=True)
        if not new:  # Deleted tests cannot be overlaid.
            continue
        old = git(repo, 'show', f'{parent}:{path}', missing=True)
        lines = changed_lines(old, new)
        if language in ('ts', 'shell'):
            review_test |= bool(REVIEW_TEST.search(PurePosixPath(path).name))
            review_test |= any(REVIEW_TEST.search(line) and re.search(r'\b(?:test|it|function)\b', line)
                               for i, line in enumerate(new.splitlines(), 1) if i in lines)
        if language == 'python':
            try:
                names[path] = python_names(new, lines)
            except SyntaxError:
                continue
            # Only label a Python harness shell when it names a changed shell script.
            if any(p in new or PurePosixPath(p).name in new for p in scripts):
                language = 'shell'
        elif language == 'go':
            names[path] = go_names(new, lines)
        groups[language].append(path)
    evidence = EVIDENCE.search(task_text(message)) or REVIEW.search(task_text(message))
    if not evidence:
        evidence = any(REVIEW_TEST.search(name) for values in names.values() for name in values)
        evidence = evidence or review_test
    if not evidence:
        return []
    result = []
    for language, tests in sorted(groups.items()):
        try:
            runs = commands(repo, sha, language, tests, names)
        except ValueError:
            continue
        result.append({'repo': str(repo), 'fix_commit': sha, 'parent': parent,
                       'language': language, 'test_files': tests,
                       'non_test_files': non_tests, 'tests_to_run': runs,
                       'task_text': task_text(message)})
    return result


def scan(repo, ref='main', days=150):
    # Read metadata in one Git process; only inspect trees with evidence. A second
    # history search finds review-named tests even when the message omits review.
    history = git(repo, 'log', ref, f'--since={days} days ago', '--no-merges',
                  '--format=%x1e%H%x00%B%x00', '--name-only')
    named_tests = set(git(repo, 'log', ref, f'--since={days} days ago', '--no-merges',
                          '--format=%H', '-G', '[Rr][Ee][Vv][Ii][Ee][Ww][ _-]*[0-9]+',
                          '--', ':(glob)**/*test*', ':(glob)*test*').splitlines())
    for entry in history.split('\x1e'):
        if not entry.strip():
            continue
        commit, message, paths = entry.split('\x00', 2)
        paths = paths.splitlines()
        if (EVIDENCE.search(task_text(message)) or REVIEW.search(task_text(message))
                or commit in named_tests or any(REVIEW_TEST.search(p) for p in paths)):
            yield from candidates_for_commit(repo, commit)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repos', nargs='*', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--ref', default='main')
    parser.add_argument('--days', type=int, default=150)
    args = parser.parse_args()
    if args.days <= 0:
        parser.error('--days must be positive')
    failed = False
    for repo in args.repos or [args.root / name for name in REPOS]:
        try:
            for candidate in scan(repo, args.ref, args.days):
                print(json.dumps(candidate, ensure_ascii=False))
        except (ValueError, OSError) as exc:
            print(f'{repo}: {exc}', file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
