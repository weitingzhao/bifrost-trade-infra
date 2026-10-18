"""Conservative attribution of compiler/import diagnostics to the pinned source delta."""
import ast
from pathlib import PurePosixPath
import re

from pick import changed_lines, git


def python_definitions(text):
    """Definitions with their owner, module-level imports included as exported bindings."""
    result = set()
    def visit(body, owner=''):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                result.add((owner, node.name))
                if isinstance(node, ast.ClassDef):
                    visit(node.body, node.name)
                elif owner and node.args.args:
                    receiver = node.args.args[0].arg
                    for item in ast.walk(node):
                        if isinstance(item, (ast.Assign, ast.AnnAssign)):
                            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                            for target in targets:
                                if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                                        and target.value.id == receiver):
                                    result.add((owner, target.attr))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        result.add((owner, target.id))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    result.add((owner, alias.asname or alias.name.split('.')[0]))
    visit(ast.parse(text).body)
    return result


def module_names(path):
    parts = list(PurePosixPath(path).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    # src layouts and repository-root modules both occur in these repositories.
    return {'.'.join(parts[i:]) for i in range(len(parts))}


def source_delta(candidate):
    """Keep evidence by package/module; never accept a symbol merely mentioned in a diff."""
    go, python, modules = {}, {}, set()
    repo, fix, parent = (candidate[k] for k in ('repo', 'fix_commit', 'parent'))
    for path in candidate['non_test_files']:
        if not path.endswith(('.go', '.py')):
            continue
        new = git(repo, 'show', f'{fix}:{path}', missing=True)
        old = git(repo, 'show', f'{parent}:{path}', missing=True)
        if not new:
            continue
        if path.endswith('.py'):
            try:
                additions = python_definitions(new) - python_definitions(old)
            except SyntaxError:
                continue
            for module in module_names(path):
                python.setdefault(module, set()).update(additions)
                if not old:
                    modules.add(module)
        else:
            changed = changed_lines(old, new)
            # Ignore declarations merely quoted in comments or string literals.
            new = re.sub(r'''(?s)/\*.*?\*/|//[^\n]*|`[^`]*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''',
                         lambda m: re.sub(r'[^\n]', ' ', m[0]), new, flags=re.X)
            package = str(PurePosixPath(path).parent)
            symbols = go.setdefault(package, set())
            package_name = re.search(r'(?m)^package\s+(\w+)', new)
            if package_name:
                symbols.add('@package:' + package_name[1])
            # Multiline parameter changes still belong to the enclosing function.
            for declaration in re.finditer(r'(?m)^func\s+(?:\([^)]*\)\s*)?(\w+)(?:\[[^]]+\])?\s*\([^{}]*?\)[^{]*\{', new):
                start = new[:declaration.start()].count('\n') + 1
                end = new[:declaration.end()].count('\n') + 1
                if changed.intersection(range(start, end + 1)):
                    symbols.add(declaration[1])
            for group in re.finditer(r'(?ms)^(?:const|var)\s*\((.*?)^\)', new):
                start = new[:group.start(1)].count('\n') + 1
                for offset, line in enumerate(group[1].splitlines()):
                    if start + offset in changed:
                        match = re.match(r'\s*(\w+(?:\s*,\s*\w+)*)', line)
                        if match:
                            symbols.update(re.split(r'\s*,\s*', match[1]))
            for block in re.finditer(r'\btype\s+\w+\s+(?:struct|interface)\s*\{([^}]*)\}', new):
                start = new[:block.start(1)].count('\n') + 1
                for offset, line in enumerate(block[1].splitlines()):
                    if start + offset in changed:
                        for member in line.split(';'):
                            match = re.match(r'\s*(\w+)\s*(?:\(|\s+[^=])', member)
                            if match:
                                symbols.add(match[1])
            for i, line in enumerate(new.splitlines(), 1):
                if i not in changed:
                    continue
                # Function/method declarations, type/variable/constant declarations,
                # and struct/interface members (not expressions or calls).
                match = re.match(r'^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(', line)
                match = match or re.match(r'^(?:type|var|const)\s+(\w+)\b', line)
                match = match or re.match(r'^\s+(\w+)\s+(?:\*?[\w\[\]]|func\b)', line)
                if match and not re.match(r'\s*(?:return|if|for|switch|case|else|go|defer)\b', line):
                    symbols.add(match[1])
    return go, python, modules


def missing_symbols(run, candidate, delta):
    if run['timed_out'] or run['returncode'] not in (1, 2) or run.get('truncated'):
        return []
    output = run['tail']
    go, python, modules = delta
    found = []
    if run['argv'][0] == 'go':
        package = str(PurePosixPath(run['cwd']) / run['argv'][2].removeprefix('./'))
        allowed = go.get(package, set())
        diagnostics = re.findall(r'(?m)^(\S+\.go):\d+(?::\d+)?:\s*(.+)$', output)
        if not diagnostics or re.search(r'(?i)syntax error|cannot find|no required module|missing go.sum|permission denied|too many errors', output):
            return []
        for file, error in diagnostics:
            # The diagnostic must belong to the tested package, not an imported one.
            location = str(PurePosixPath(run['cwd']) / PurePosixPath(file).parent)
            if location != package:
                return []
            undefined = re.fullmatch(r'undefined: (?:(\w+)\.)?(\w+)', error)
            if undefined:
                if undefined[1] and '@package:' + undefined[1] not in allowed:
                    return []
                name = undefined[2]
            else:
                match = re.fullmatch(r'.+\.(\w+) undefined \(type .+ has no field or method \w+\)', error)
                match = match or re.fullmatch(r'too (?:many|few) arguments in call to (?:\w+\.)?(\w+)', error)
                match = match or re.fullmatch(r'not enough arguments in call to (?:\w+\.)?(\w+)', error)
                if not match:
                    return []
                name = match[1]
            if name not in allowed:
                return []
            found.append(name)
        # Reject any unparsed diagnostic, including linker/environment failures.
        for line in output.splitlines():
            if (not line.strip() or line.startswith('# ') or line == 'FAIL'
                    or re.match(r'^FAIL\s+\S+ \[build failed\]$', line)
                    or re.match(r'^\S+\.go:\d+(?::\d+)?:\s*', line)
                    or re.match(r'^\s+(?:have|want) \(', line)):
                continue
            return []
    elif candidate['language'] == 'python':
        errors = re.findall(r'(?m)^(?:E\s+)?([\w.]*(?:Error|Exception)|SystemExit|KeyboardInterrupt|ExceptionGroup):\s*(.+)$', output)
        if not errors:
            return []
        for kind, error in errors:
            if kind == 'ImportError':
                match = re.match(r"cannot import name '([^']+)' from '([^']+)'", error)
                if not match or ('', match[1]) not in python.get(match[2], set()):
                    return []
                found.append(match[1])
            elif kind == 'ModuleNotFoundError':
                match = re.fullmatch(r"No module named '([^']+)'", error)
                if not match or match[1] not in modules:
                    return []
                found.append(match[1])
            elif kind == 'AttributeError':
                match = re.match(r"module '([^']+)' has no attribute '([^']+)'", error)
                if match and ('', match[2]) in python.get(match[1], set()):
                    found.append(match[2])
                    continue
                match = re.match(r"(?:type object '([^']+)'|'([^']+)' object) has no attribute '([^']+)'", error)
                if not match:
                    return []
                owner, _, name = match.groups()
                owner = owner or match[2]
                if not any((owner, name) in definitions for definitions in python.values()):
                    return []
                found.append(name)
            else:
                return []
    return sorted(set(found))
