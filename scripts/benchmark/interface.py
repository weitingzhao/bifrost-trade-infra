"""What a fix's tests call that the code before the fix lacks (TD-373).

A hidden test that calls a name the fix introduced measures whether the
executor guessed the name, not whether it can make the change. interface()
lists, for one candidate, every declaration of the fix's changed non-test
files that its tests use and the parent does not have, or has with another
signature: Go through goapi.go (go/ast), Python through ast, TypeScript by its
exports, shell by its functions, the environment variables it newly reads and
its new options. Each entry is the declaration as the fix wrote it, without a
body, headed by where it is; agentd bench gives them to the executor.
siblings() names the repositories a TypeScript package links with file: and
the commit of each that the fix was made against (its main at the fix's
commit time).
"""
import ast
import copy
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

# pick loads subprocess without letting the sibling select.py shadow stdlib.
from pick import REPOS, git, module_dir, test_language
import subprocess

HERE = Path(__file__).resolve().parent
# agentd takes 4 KiB an entry and 32 KiB in all (bench.go).
MAX_ENTRY = 4000
MAX_TOTAL = 30000


def interface(candidate):
    language = candidate['language']
    if language == 'go':
        entries = go_interface(candidate)
    elif language == 'ts':
        entries = ts_interface(candidate)
    else:
        entries = python_interface(candidate) + shell_interface(candidate)
    entries += option_interface(candidate) + text_interface(candidate)
    return bounded(entries, candidate.get('missing_symbols', []))


def size(text):
    return len(text.encode())


def cut(text, limit):
    """text within limit UTF-8 bytes, on a character boundary."""
    if size(text) <= limit:
        return text
    return text.encode()[:limit - len(' …'.encode())].decode(errors='ignore').rstrip() + ' …'


def bounded(entries, required=()):
    """Unique entries, each and all within agentd's bounds (UTF-8 bytes, as
    bench.go counts); a name verify.py found missing is never left out: when
    the entries naming them do not fit, the candidate is refused."""
    out, seen = [], set()
    for entry in entries:
        entry = cut(entry.strip(), MAX_ENTRY)
        if entry and entry not in seen:
            seen.add(entry)
            out.append(entry)

    def names(entry):
        return {n for n in required if re.search(rf'(?<![\w$]){re.escape(n)}(?![\w$])', entry)}

    for name in required:
        if not any(name in names(e) for e in out):
            out.append(f'{name} (the tests call it; the code before the fix does not declare it)')
    note = 'and more declarations the tests use, not listed (the list is bounded)'
    if sum(map(size, out)) > MAX_TOTAL:
        while sum(map(size, out)) + size(note) > MAX_TOTAL:
            optional = [i for i, e in enumerate(out) if not names(e)]
            if not optional:
                raise ValueError('the declarations of the names the tests call do not fit the interface bound')
            out.pop(optional[-1])
        out.append(note)
    return out


def show(repo, commit, path):
    return git(repo, 'show', f'{commit}:{path}', missing=True)


def files_in(repo, commit, directory):
    listing = git(repo, 'ls-tree', '--name-only', commit, '--', f'{directory}/' if directory != '.' else '.', missing=True)
    return [p for p in listing.splitlines() if p]


# ---------------------------------------------------------------- Go

def goapi(mode, sources):
    """sources: {name: text}; the declarations or the uses of those files."""
    sources = {name: body for name, body in sources.items() if body}
    if not sources:
        return [] if mode == 'decls' else {'idents': [], 'selected': [], 'declared': [], 'imports': [], 'zero': [],
                                           'package': ''}
    with tempfile.TemporaryDirectory(prefix='goapi-') as temp:
        paths = []
        for i, (name, body) in enumerate(sorted(sources.items())):
            path = Path(temp) / f'{i:03d}_{PurePosixPath(name).name}'
            path.write_text(body)
            paths.append(str(path))
        env = dict(os.environ, GOTOOLCHAIN='local', GO111MODULE='off', GOFLAGS='')
        result = subprocess.run(['go', 'run', str(HERE / 'goapi.go'), mode, *paths], capture_output=True, text=True, env=env)
        if result.returncode:
            raise ValueError(f'goapi {mode}: {result.stderr.strip()}')
    out = json.loads(result.stdout)
    if mode == 'uses':  # Go writes an empty list as null
        return {k: (v if v is not None else []) for k, v in out.items()}
    return out if out is not None else []


def go_sources(repo, commit, directory, tests):
    names = [p for p in files_in(repo, commit, directory)
             if p.endswith('.go') and (p.endswith('_test.go') == tests)
             and str(PurePosixPath(p).parent) == directory]
    return {p: show(repo, commit, p) for p in names}


def go_type(d, decls, names, zero=()):
    """A type as declared; a struct with only the fields the tests use (the
    rest are the executor's to choose)."""
    if not re.match(r'type\s+\w+(?:\[[^]]*\])?\s+struct\s*\{', d['text']):
        return d['text']
    fields = [f for f in decls if f['kind'] in ('field', 'embedded') and f['key'].split('.')[0] == d['key']]
    # an embedded type always: what it promotes is the tests' as well
    used = [f for f in fields if f['name'] in names or f['kind'] == 'embedded']
    head = d['text'].split('{', 1)[0] + '{'
    body = ''.join(f'\n\t{f["text"]}' for f in used)
    if len(used) < len(fields):
        body += '\n\t// other fields of your choosing'
    if d['name'] in zero:
        body += f'\n\t// the tests also use {d["name"]}{{}}, its zero value'
    return head + body + '\n}'


def go_interface(candidate):
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    tests = candidate['test_files']
    changed_dirs = {str(PurePosixPath(p).parent) for p in candidate['non_test_files']
                    if p.endswith('.go') and not p.endswith('_test.go')}
    if not changed_dirs:
        return []
    # The tests' own packages, and the packages of this module they import.
    use = {}
    for directory in sorted({str(PurePosixPath(p).parent) for p in tests}):
        sources = {p: show(repo, fix, p) for p in tests if str(PurePosixPath(p).parent) == directory}
        use[directory] = goapi('uses', sources)
    targets = {}
    for directory, u in use.items():
        targets.setdefault(directory, set()).update(u['idents'] + u['selected'])
        module = module_dir(repo, fix, directory)
        gomod = show(repo, fix, f'{module}/go.mod' if module != '.' else 'go.mod')
        match = re.search(r'(?m)^module\s+(\S+)', gomod)
        if not match:
            continue
        for path in u['imports']:
            if path == match[1] or path.startswith(match[1] + '/'):
                rel = path[len(match[1]):].lstrip('/')
                imported = str(PurePosixPath(module) / rel) if rel else module
                targets.setdefault(imported, set()).update(u['selected'])
    declared_by_tests = {n for u in use.values() for n in u['declared']}
    zero = {n for u in use.values() for n in u['zero']}
    entries = []
    for directory in sorted(changed_dirs & set(targets)):
        names = targets[directory]
        before = {d['key']: d for d in goapi('decls', go_sources(repo, parent, directory, False))}
        after = goapi('decls', go_sources(repo, fix, directory, False))
        own = use.get(directory)
        internal = own is not None and own['package'] == next((d['package'] for d in after), None)
        new_types = {d['key'] for d in after if d['kind'] == 'type' and d['key'] not in before}
        wanted_types = set()
        for d in after:
            old = before.get(d['key'])
            if old is not None and (old['text'] == d['text'] or d['kind'] in ('var', 'const')):
                continue  # unchanged, or a value that changed: its name was there
            name = d['name']
            if d['kind'] in ('method', 'field', 'embedded'):
                owner = d['key'].split('.')[0]
                if name not in names and not (d['kind'] == 'embedded' and owner in names):
                    continue
                if owner in new_types:
                    wanted_types.add(owner)  # a field shows in its type
                    if d['kind'] != 'method':
                        continue
            elif name not in names or (name in declared_by_tests and internal):
                continue
            elif not name[:1].isupper() and not internal:
                continue
            if d['kind'] == 'type':
                if old is None or not re.match(r'type\s+\w+(?:\[[^]]*\])?\s+(?:struct|interface)\s*\{', d['text']):
                    wanted_types.add(d['key'])
                continue  # an existing struct's or interface's change is its members'
            entries.append((directory, d, old))
        for d in after:
            if d['kind'] == 'type' and d['key'] in wanted_types:
                entries.append((directory, dict(d, text=go_type(d, after, names, zero)), before.get(d['key'])))
    out = []
    for directory, d, old in entries:
        where = f'// {directory} (package {d["package"]})'
        if d['kind'] in ('field', 'embedded'):
            where += f', in type {d["key"].split(".")[0]}'
        if old is not None:
            where += ', changed from what this checkout has'
        out.append(where + '\n' + d['text'].strip())
    return out


# ---------------------------------------------------------------- Python

def signature(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        head = copy.copy(node)
        head.body, head.decorator_list = [ast.Expr(ast.Constant(...))], []
        text = ast.unparse(head).rstrip()
        return text[:-len('...')].rstrip() if text.endswith('...') else text
    if isinstance(node, ast.ClassDef):
        bases = ', '.join(ast.unparse(b) for b in node.bases + node.keywords)
        return f'class {node.name}({bases}):' if bases else f'class {node.name}:'
    # An assignment: the name and its annotation, never its value; a lambda
    # its parameters (review 292 B2).
    target = node.targets[0] if isinstance(node, ast.Assign) else node.target
    name = ast.unparse(target)
    if isinstance(node, ast.AnnAssign):
        return f'{name}: {ast.unparse(node.annotation)}'
    if isinstance(node.value, ast.Lambda):
        return f'{name} = lambda {ast.unparse(node.value.args)}: …'
    return f'{name} = …'


def python_api(text):
    """{(owner, name): signature} of module-level and class-level definitions."""
    out = {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out

    def visit(body, owner):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[(owner, node.name)] = signature(node)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, node.name)
                elif owner and node.args.args:
                    receiver = node.args.args[0].arg
                    for item in ast.walk(node):
                        targets = (item.targets if isinstance(item, ast.Assign) else
                                   [item.target] if isinstance(item, ast.AnnAssign) else [])
                        for target in targets:
                            if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                                    and target.value.id == receiver and (owner, target.attr) not in out):
                                out[(owner, target.attr)] = f'{receiver}.{target.attr} (an attribute set in {node.name})'
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        one = ast.AnnAssign(target=target, annotation=node.annotation, value=None, simple=1) \
                            if isinstance(node, ast.AnnAssign) else ast.Assign(targets=[target], value=node.value)
                        out[(owner, target.id)] = signature(one)
    visit(tree.body, '')
    return out


def python_uses(text):
    imported, modules, names, strings = set(), set(), set(), set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return imported, modules, names
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or '')
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # monkeypatch.setattr("pkg.mod.name", ...), getattr(obj, "name")
            if re.fullmatch(r'[A-Za-z_][\w.]*', node.value):
                strings.update(node.value.split('.'))
    return imported, modules, names | strings


def module_names(path):
    parts = list(PurePosixPath(path).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return {'.'.join(parts[i:]) for i in range(len(parts))}


def python_interface(candidate):
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    imported, modules, names = set(), set(), set()
    for path in candidate['test_files']:
        if path.endswith('.py'):
            i, m, n = python_uses(show(repo, fix, path))
            imported |= i
            modules |= m
            names |= n
    out = []
    for path in candidate['non_test_files']:
        if not path.endswith('.py') or test_language(path):
            continue
        new_text, old_text = show(repo, fix, path), show(repo, parent, path)
        if not new_text:
            continue
        after, before = python_api(new_text), python_api(old_text)
        mods = module_names(path)
        by_module = bool(mods & modules)
        new_module = not old_text
        lines = []
        for (owner, name), sig in after.items():
            if before.get((owner, name)) == sig:
                continue  # unchanged (a value is not shown, so one that changed is too)
            if owner:
                used = name in names
            else:
                used = name in names or (by_module and name in imported)
            if not used:
                continue
            if owner:
                head = after.get(('', owner))  # the class line heads its members
                if head and head not in lines:
                    lines.append(head)
            lines.append(('    ' if owner else '') + sig + ('' if owner or ('', name) not in before else
                                                            '  # changed from what this checkout has'))
        if new_module and by_module and not lines:
            lines.append('(the tests import it)')
        if lines:
            head = f'# {path}' + (' (a new module)' if new_module else '')
            out.append(head + '\n' + '\n'.join(lines))
    return out


# ---------------------------------------------------------------- shell

SHELL_FUNCTION = re.compile(r'(?m)^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?')
SHELL_VARIABLE = re.compile(r'\$\{?([A-Z][A-Z0-9_]{2,})\b')
# The environment every process has: a script reading one is no hook.
COMMON_VARIABLES = {'HOME', 'PATH', 'USER', 'LOGNAME', 'SHELL', 'TMPDIR', 'PWD', 'LANG', 'TERM', 'UID', 'EUID', 'PPID',
                    'BASH_SOURCE', 'LINENO', 'FUNCNAME', 'RANDOM', 'SECONDS', 'OSTYPE', 'HOSTNAME', 'IFS', 'OPTARG', 'OPTIND'}


def shell_function_named(name):
    """A shell function's name is one the tests can be said to call when it is
    not a plain word (step_creds, send-secret; not fail or die)."""
    return '_' in name.strip('_') or '-' in name or len(name) >= 10


def shell_interface(candidate):
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    tests = '\n'.join(show(repo, fix, p) for p in candidate['test_files'])
    out = []
    for path in candidate['non_test_files']:
        if not path.endswith('.sh'):
            continue
        new, old = show(repo, fix, path), show(repo, parent, path)
        if not new:
            continue
        lines = []
        old_functions = set(SHELL_FUNCTION.findall(old))
        for name in dict.fromkeys(SHELL_FUNCTION.findall(new)):
            if (name not in old_functions and shell_function_named(name)
                    and re.search(rf'(?<![\w-]){re.escape(name)}(?![\w-])', tests)):
                lines.append(f'{name}()  # a new function')
        old_variables = set(SHELL_VARIABLE.findall(old)) | COMMON_VARIABLES
        # the name only: the line that reads it may be the change (review 292 B2)
        read = [name for name in dict.fromkeys(SHELL_VARIABLE.findall(new))
                if name not in old_variables and re.search(rf'\b{name}\b', tests)]
        if read:
            lines.append('reads the environment variable' + ('s ' if len(read) > 1 else ' ') + ', '.join(read)
                         + ', which the tests set')
        if lines:
            out.append(f'# {path}' + (' (a new script)' if not old else '') + '\n' + '\n'.join(lines))
    return out


# Where a file declares an option it takes: a shell case label, argparse, Go's
# flag package. An option it only passes to another command is not one.
OPTION_DECLARED = re.compile(r'(?m)(?:^|;;|\bin)\s*(?:[\w*|-]*\|)?(--[a-z][a-z0-9-]+)(?:=\*)?(?:\|[\w*|-]*)?\)'
                             r'|add_argument\(\s*(?:[\'"]-\w[\'"],\s*)?[\'"](--[a-z][a-z0-9-]+)[\'"]'
                             r'|\b\w+\.(?:String|Bool|Int|Int64|Uint|Float64|Duration|Var|Func)\(\s*(?:&\w+,\s*)?"([a-z][a-z0-9-]+)"')


def declared_options(text):
    return {'--' + m[3] if m[3] else (m[1] or m[2]) for m in OPTION_DECLARED.finditer(text)}


def option_interface(candidate):
    """Options (--name) a changed non-test file newly declares that the tests pass."""
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    tests = '\n'.join(show(repo, fix, p) for p in candidate['test_files'])
    used = set(re.findall(r'(?<![\w-])--[a-z][a-z0-9-]+', tests))
    out = []
    for path in candidate['non_test_files']:
        new = show(repo, fix, path)
        if not new:
            continue
        added = sorted((declared_options(new) - declared_options(show(repo, parent, path))) & used)
        if added:
            out.append(f'# {path} takes the new option' + ('s ' if len(added) > 1 else ' ') + ', '.join(added))
    return out


TEXT_MIN = 12


def literals(path, text):
    """The string literals of a file, a template's, an f-string's or a shell
    string's constant pieces each on its own. Comments are not strings
    (review 293 B2): Python through ast, the rest through a scan that skips
    // and /* */ comments, or # comments in a shell script."""
    if path.endswith('.py'):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
        return out
    shell = path.endswith('.sh') or text.startswith('#!')
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if not shell and text.startswith('//', i):
            i = text.find('\n', i)
            i = n if i < 0 else i
            continue
        if not shell and text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if shell and ch == '#' and (i == 0 or text[i - 1] in ' \t\n;|&('):
            i = text.find('\n', i)
            i = n if i < 0 else i
            continue
        if ch not in '"\'`':
            i += 1
            continue
        j, body = i + 1, []
        while j < n and text[j] != ch:
            if text[j] == '\\' and not (shell and ch == "'"):
                body.append(text[j:j + 2])
                j += 2
                continue
            if text[j] == '\n' and not shell and ch != '`':
                break  # not a string: a rune, an apostrophe in a regular expression
            body.append(text[j])
            j += 1
        raw = ''.join(body)
        if ch == '`' or (shell and ch == '"'):
            out.extend(re.split(r'\$\{[^}]*\}|\$\([^)]*\)|\$\w+', raw))
        elif shell:
            out.append(raw)
        else:
            try:
                out.append(json.loads('"' + raw.replace('\\\'', "'") + '"'))
            except ValueError:
                out.append(raw)
        i = j + 1
    return out


def text_interface(candidate):
    """Texts the tests look for that the fix wrote as strings into its non-test
    files: a message, a key, a query. The tests compare them as written. Only
    what the fix wrote inside a string literal: a test that looks for a line
    of code in the source gets nothing (review 292 B2)."""
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    pieces = []
    for path in candidate['test_files']:
        for piece in literals(path, show(repo, fix, path)):
            piece = piece.strip()
            if len(piece) >= TEXT_MIN and re.search(r'[\s:;,.()/\'"=<>-]', piece) and piece not in pieces:
                pieces.append(piece)
    if not pieces:
        return []
    before = '\n'.join(show(repo, parent, p) for p in candidate['non_test_files'])
    found = {}
    for path in candidate['non_test_files']:
        strings = literals(path, show(repo, fix, path))
        for piece in pieces:
            if (any(piece in string for string in strings) and piece not in before
                    and not any(piece in seen for seen in found.get(path, []))):
                found.setdefault(path, []).append(piece)
    return [f'# {path}: texts the tests look for, as it writes them\n' + '\n'.join(json.dumps(p, ensure_ascii=False) for p in texts)
            for path, texts in found.items()]


# ---------------------------------------------------------------- TypeScript

TS_EXPORT = re.compile(r'(?m)^export\s+(?:declare\s+)?(default\s+)?(?:async\s+)?'
                       r'(function\*?|const|let|var|class|interface|type|enum|abstract\s+class)\s+(\w+)')
TS_REEXPORT = re.compile(r'(?m)^export\s+(?:type\s+)?(\*|\{[^}]*\})\s+from\s+[\'"]([^\'"]+)[\'"]')
TS_SOURCE = ('.ts', '.tsx')


def ts_declaration(text, start, kind):
    """The declaration at start, without a body or a value: a type in full, a
    function or an arrow function to its signature, a class its line, a
    constant its name and type (review 292 B2)."""
    rest = text[start:]
    if kind in ('interface', 'type', 'enum'):
        depth, end = 0, None
        for i, ch in enumerate(rest):
            if ch in '{([':
                depth += 1
            elif ch in '})]':
                depth -= 1
            elif depth <= 0 and (ch == ';' or (ch == '\n' and i and rest[i - 1] == '}')):
                end = i + (1 if ch == ';' else 0)
                break
            elif ch == '\n' and depth <= 0 and kind == 'type' and not rest[:i].rstrip().endswith(('=', '|', '&', ',')):
                end = i
                break
        return rest[:end].strip() if end else rest.split('\n\n')[0].strip()
    first = rest.split('\n')[0].rstrip()
    if kind.startswith('function'):
        depth = 0
        for i, ch in enumerate(rest):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '{' and depth == 0 and rest[:i].count('(') and rest[:i].count('(') == rest[:i].count(')'):
                head = rest[:i].rstrip()
                # a return type may itself be an object type: { ... } before the body
                if head.endswith(':'):
                    continue
                return head
        return first.split('{')[0].rstrip()
    if kind in ('const', 'let', 'var'):
        arrow = re.match(r'export\s+(?:const|let|var)\s+\w+\s*(?::[^=]*)?=\s*(?:async\s*)?(?:<[^>]*>\s*)?\(', rest)
        end = rest.find('=>', arrow.end()) if arrow else -1
        if end != -1 and '\n\n' not in rest[:end]:
            return rest[:end + 2].strip() + ' …'
        bare = re.match(r'export\s+(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?(\w+)\s*=>', first)
        if bare:  # x => …
            return first[:bare.end()] + ' …'
        annotated = re.match(r'(export\s+(?:const|let|var)\s+\w+\s*:\s*[^=]+?)\s*=', first)
        if annotated:
            return annotated[1]
        named = re.match(r'export\s+(?:const|let|var)\s+\w+', first)
        return named[0] + ' = …'
    return first.split('{')[0].rstrip()


TS_ANONYMOUS_DEFAULT = re.compile(r'(?m)^export\s+default\s+(?:(async\s+)?(function)\b\*?\s*\(|(class)\s*\{|(async\s*)?\()')


def ts_exports(text):
    """{name: declaration}; a default export is also under 'default', a
    function, class or arrow function without a name only there (review
    293 B3)."""
    out = {}
    for m in TS_EXPORT.finditer(text):
        out[m[3]] = ts_declaration(text, m.start(), m[2])
        if m[1]:
            out['default'] = out[m[3]]
    m = TS_ANONYMOUS_DEFAULT.search(text)
    if m and 'default' not in out:
        if m[2]:
            out['default'] = ts_declaration(text, m.start(), 'function')
        elif m[3]:
            out['default'] = 'export default class'
        else:
            end = text.find('=>', m.end())
            if end != -1 and '\n\n' not in text[m.start():end]:
                out['default'] = text[m.start():end + 2].strip() + ' …'
    return out


def ts_reexports(text):
    """[(spec, {exported name: its name in spec} or None for *)]."""
    out = []
    for m in TS_REEXPORT.finditer(text):
        if m[1] == '*':
            out.append((m[2], None))
            continue
        names = {}
        for part in m[1].strip('{}').split(','):
            part = re.sub(r'^\s*type\s+', '', part).strip()
            if part:
                inner, _, outer = part.partition(' as ')
                names[(outer or inner).strip()] = inner.strip()
        out.append((m[2], names))
    return out


def ts_imports(text):
    """[(spec, names)]: named and default imports; a namespace import gives
    the names selected on it."""
    out = []
    for m in re.finditer(r'(?ms)^\s*import\s+(type\s+)?(.*?)\s+from\s+[\'"]([^\'"]+)[\'"]', text):
        clause, spec = m[2], m[3]
        names = set()
        brace = re.search(r'\{(.*?)\}', clause, re.S)
        if brace:
            for part in brace[1].split(','):
                part = re.sub(r'^\s*type\s+', '', part).strip()
                if part:
                    names.add(part.split(' as ')[0].strip())
        namespace = re.search(r'\*\s+as\s+(\w+)', clause)
        if namespace:
            names.update(re.findall(rf'\b{namespace[1]}\.(\w+)', text))
        default = re.match(r'\s*(\w+)\s*(?:,|$)', clause)
        if default and not clause.strip().startswith('{'):
            names.add('default')
        out.append((spec, names))
    return out


def ts_resolve(test, spec, package):
    """The repository path a relative or @/ import of test names, without extension."""
    if spec.startswith('@/'):
        return str(PurePosixPath(package) / 'src' / spec[2:])
    if spec.startswith('.'):
        parts = []
        for part in (PurePosixPath(test).parent / spec).parts:
            if part == '..':
                if parts:
                    parts.pop()
            elif part != '.':
                parts.append(part)
        return '/'.join(parts)
    return None


def ts_interface(candidate):
    repo, fix, parent = candidate['repo'], candidate['fix_commit'], candidate['parent']
    wanted = {}
    for test in candidate['test_files']:
        package = module_dir(repo, fix, str(PurePosixPath(test).parent), 'package.json')
        for spec, names in ts_imports(show(repo, fix, test)):
            target = ts_resolve(test, spec, package)
            if target:
                wanted.setdefault(target, set()).update(names)
    # A module that re-exports (an index) hands the names on (review 292 B3).
    for _ in range(3):
        for target, names in list(wanted.items()):
            for suffix in ('.ts', '.tsx', '/index.ts', '/index.tsx'):
                text = show(repo, fix, target + suffix)
                if text:
                    break
            for spec, mapping in ts_reexports(text):
                if not spec.startswith('.'):
                    continue
                inner = ts_resolve(target + suffix, spec, '.')
                handed = set(names) if mapping is None else {mapping[n] for n in names if n in mapping}
                if handed - wanted.get(inner, set()):
                    wanted.setdefault(inner, set()).update(handed)
    out = []
    for path in candidate['non_test_files']:
        if not path.endswith(TS_SOURCE) or test_language(path):
            continue
        stem = str(PurePosixPath(path).with_suffix(''))
        names = wanted.get(stem, set()) | (wanted.get(str(PurePosixPath(stem).parent), set())
                                           if PurePosixPath(stem).name == 'index' else set())
        if not names:
            continue
        new, old = show(repo, fix, path), show(repo, parent, path)
        after, before = ts_exports(new), ts_exports(old)
        lines = []
        for name, text in after.items():
            if name == 'default' and any(after[n] == text for n in after if n != 'default'):
                if any(after[n] == text and n in names for n in after if n != 'default'):
                    continue  # listed under its name
            if name in names and before.get(name) != text and text not in lines:
                lines.append(text + ('  // changed from what this checkout has' if name in before else ''))
        if not old and not lines:
            lines.append('// (the tests import it)')
        if lines:
            out.append(f'// {path}' + (' (a new module)' if not old else '') + '\n' + '\n'.join(lines))
    return out


# ---------------------------------------------------------------- siblings

def siblings(candidate):
    """[{repo, commit}] for each file: dependency of the candidate's
    TypeScript packages on a repository beside it: its main at the fix's
    commit time."""
    if candidate['language'] != 'ts':
        return []
    repo, fix = Path(candidate['repo']), candidate['fix_commit']
    out = {}
    for check in candidate['tests_to_run']:
        package = check['cwd']
        manifest = show(repo, fix, f'{package}/package.json' if package != '.' else 'package.json')
        if not manifest:
            continue
        data = json.loads(manifest)
        for deps in (data.get('dependencies') or {}, data.get('devDependencies') or {}):
            for spec in deps.values():
                if not isinstance(spec, str) or not spec.startswith('file:'):
                    continue
                target = PurePosixPath(package) / spec[len('file:'):]
                parts = []
                for part in target.parts:
                    if part == '..':
                        if not parts:
                            parts.append('..')
                        elif parts[-1] == '..':
                            parts.append('..')
                        else:
                            parts.pop()
                    elif part != '.':
                        parts.append(part)
                if len(parts) != 2 or parts[0] != '..' or parts[1] not in REPOS:
                    raise ValueError(f'{package}: {spec} is not a repository beside {repo.name}')
                name = parts[1]
                when = git(repo, 'show', '-s', '--format=%cI', fix).strip()
                commit = git(repo.parent / name, 'rev-list', '-n1', f'--before={when}', 'main').strip()
                if not re.fullmatch(r'[0-9a-f]{40}', commit):
                    raise ValueError(f'{name} has no main commit before {when}')
                out[name] = commit
    return [{'repo': name, 'commit': commit} for name, commit in sorted(out.items())]
