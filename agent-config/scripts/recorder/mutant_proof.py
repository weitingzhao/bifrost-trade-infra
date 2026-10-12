"""Show that a mutant was exercised, not merely left untested.

The checker compiles a probe into a copy of the mutant. The probe evaluates
the original expression and the mutated expression on the same input and
counts a hit only when those values differ. ``guard_pass`` has no expression:
reaching the replaced return or continue records ``("return", value)`` against
``("pass", None)``. Published bytes are compared on the uninstrumented mutant.
"""

from __future__ import annotations

import ast
import copy
import sys
import tempfile
from pathlib import Path


_HELPER = """
_MUTANT_PROBE_HITS = 0
def _mutant_probe_pair(original, mutant):
    global _MUTANT_PROBE_HITS
    try:
        differs = original != mutant
    except Exception:
        differs = True
    if differs:
        _MUTANT_PROBE_HITS += 1
    return mutant
"""


def _get(node, field, index):
    value = getattr(node, field)
    return value[index] if index is not None else value


def _set(node, field, index, new):
    if index is None:
        setattr(node, field, new)
    else:
        getattr(node, field)[index] = new


def _same(left, right):
    """Structural equality. Comparison operators are singletons, so identity is useless."""
    if type(left) is not type(right):
        return False
    for field in left._fields:
        lv, rv = getattr(left, field), getattr(right, field)
        if isinstance(lv, list) and isinstance(rv, list):
            if len(lv) != len(rv):
                return False
            for item_l, item_r in zip(lv, rv):
                if isinstance(item_l, ast.AST) or isinstance(item_r, ast.AST):
                    if not _same(item_l, item_r):
                        return False
                elif item_l != item_r:
                    return False
        elif isinstance(lv, ast.AST) or isinstance(rv, ast.AST):
            if not _same(lv, rv):
                return False
        elif lv != rv:
            return False
    return True


def _steps(node):
    found = []
    for field in node._fields:
        value = getattr(node, field)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, ast.AST):
                    found.append((field, index))
        elif isinstance(value, ast.AST):
            found.append((field, None))
    return found


def _diff_paths(left, right, path=()):
    """Paths of the highest nodes that differ. One mutation is one path."""
    if type(left) is not type(right):
        yield path
        return
    for field in left._fields:
        lv, rv = getattr(left, field), getattr(right, field)
        if isinstance(lv, list) and isinstance(rv, list) and len(lv) != len(rv):
            yield path
            return
    differing = []
    for field, index in _steps(left):
        if not _same(_get(left, field, index), _get(right, field, index)):
            differing.append((field, index))
    for field in left._fields:
        lv, rv = getattr(left, field), getattr(right, field)
        if not isinstance(lv, (list, ast.AST)) and not isinstance(rv, (list, ast.AST)) and lv != rv:
            yield path
            return
    if len(differing) == 1:
        field, index = differing[0]
        yield from _diff_paths(_get(left, field, index), _get(right, field, index), path + ((field, index),))
    elif differing:
        yield path


def _at(tree, path):
    node = tree
    for field, index in path:
        node = _get(node, field, index)
    return node


def _condition_path(tree, path):
    """The comparison, boolean, or test whose value the mutation changes."""
    chosen = path
    for cut in range(len(path) + 1):
        node = _at(tree, path[:cut])
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp, ast.IfExp)):
            chosen = path[:cut]
    return chosen


def _call(original, mutant):
    return ast.Call(
        func=ast.Name(id="_mutant_probe_pair", ctx=ast.Load()),
        args=[original, mutant],
        keywords=[],
    )


def _inject_helper(tree):
    helper = ast.parse(_HELPER).body
    index = 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        index = 1
    if index < len(body) and isinstance(body[index], ast.ImportFrom) and body[index].module == "__future__":
        index += 1
    body[index:index] = helper


def instrument(original_source: str, mutant_source: str) -> str:
    """Return mutant source that counts when the mutated value actually changes.

    Both sides are compared after ``ast.unparse``, so a formatting difference is
    not a second mutation. The probe wraps the comparison or boolean whose
    result changed, located by path: parsed comparison operators are singletons
    and cannot be told apart by identity.
    """
    original = ast.parse(ast.unparse(ast.parse(original_source)))
    mutant = ast.parse(mutant_source)
    paths = list(_diff_paths(original, mutant))
    if len(paths) != 1:
        raise AssertionError(f"expected one AST difference, found {len(paths)}")
    path = paths[0]
    orig_node = _at(original, path)
    mut_node = _at(mutant, path)
    if isinstance(mut_node, ast.Pass) and isinstance(orig_node, (ast.Return, ast.Continue)):
        value = orig_node.value if isinstance(orig_node, ast.Return) and orig_node.value is not None else ast.Constant(None)
        kind = "return" if isinstance(orig_node, ast.Return) else "continue"
        probe = ast.Expr(value=_call(
            ast.Tuple(elts=[ast.Constant(kind), copy.deepcopy(value)], ctx=ast.Load()),
            ast.Tuple(elts=[ast.Constant("pass"), ast.Constant(None)], ctx=ast.Load()),
        ))
        parent_path, (field, index) = path[:-1], path[-1]
        body = _get(_at(mutant, parent_path), field, None)
        body[index:index + 1] = [probe, mut_node]
    else:
        path = _condition_path(mutant, path)
        orig_expr = _at(original, path)
        mut_expr = _at(mutant, path)
        if not isinstance(orig_expr, ast.expr) or not isinstance(mut_expr, ast.expr):
            raise AssertionError(f"mutation is not an expression: {type(orig_node).__name__}")
        parent_path, (field, index) = path[:-1], path[-1]
        _set(_at(mutant, parent_path), field, index, _call(copy.deepcopy(orig_expr), mut_expr))
    _inject_helper(mutant)
    ast.fix_missing_locations(mutant)
    source = ast.unparse(mutant) + "\n"
    compile(source, "<mutant-probe>", "exec")
    return source


def _classify_main():
    """Run the round-7 checks on every round-6 survivor. Not part of pytest."""
    import shutil
    import sys
    import tempfile
    import time
    from collections import Counter
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path

    from mutagen import PATH_FILES, generate
    from mutants_equivalent import EQUIVALENT

    here = Path(__file__).resolve().parent
    sources = {name: (here / name).read_text() for name in PATH_FILES}
    wanted = set(EQUIVALENT)
    items = [item for item in generate(sources) if item["name"] in wanted]
    print(f"checking {len(items)} survivors", flush=True)
    started = time.monotonic()
    passed = []
    failed = Counter()
    with ProcessPoolExecutor(max_workers=8, initializer=_worker_init, initargs=(str(here),)) as pool:
        for name, status, detail in pool.map(_worker_check, items, chunksize=4):
            if status == "pass":
                passed.append(name)
            else:
                failed[detail.split(":", 1)[0]] += 1
            if (len(passed) + sum(failed.values())) % 100 == 0:
                print(f"  {len(passed)} passed, {sum(failed.values())} failed", flush=True)
    out = Path("/tmp/round7-still-passing.txt")
    out.write_text("\n".join(passed) + "\n")
    print(f"passed {len(passed)} failed {sum(failed.values())} in {time.monotonic() - started:.1f}s", flush=True)
    print("fail kinds", dict(failed), flush=True)
    by = Counter(name.split(":")[1] if False else ":".join(name.split(":")[:2]) for name in passed)
    for key, count in by.most_common():
        print(f"{count:5} {key}")


_WORKER = {}


def _worker_init(src):
    import sys
    import tempfile
    from pathlib import Path
    src = Path(src)
    folder = Path(tempfile.mkdtemp())
    originals = {}
    for path in src.glob("*.py"):
        originals[path.name] = path.read_text()
        (folder / path.name).write_text(originals[path.name])
    sys.path.insert(0, str(folder))
    _WORKER["folder"] = folder
    _WORKER["originals"] = originals


def _purge():
    drop = {
        "contextual", "fold", "model", "ownerball", "publish", "read", "redact_bound",
        "survive", "validate", "harness", "events", "test_round7", "test_round7b", "commands", "estimate",
    }
    for name in list(sys.modules):
        if name.split(".")[0] in drop:
            del sys.modules[name]


def _worker_check(item):
    from pathlib import Path
    folder = Path(_WORKER["folder"])
    for name, text in _WORKER["originals"].items():
        (folder / name).write_text(text)
    (folder / item["file"]).write_text(item["source"])
    _purge()
    try:
        import test_round7
        test_round7.run_checks()
    except Exception as exc:
        return item["name"], "fail", f"{type(exc).__name__}: {exc}"
    return item["name"], "pass", ""


def _worker_hits(item):
    from pathlib import Path
    folder = Path(_WORKER["folder"])
    for name, text in _WORKER["originals"].items():
        (folder / name).write_text(text)
    try:
        probed = instrument(_WORKER["originals"][item["file"]], item["source"])
    except Exception as exc:
        return item["name"], "instrument", f"{type(exc).__name__}: {exc}"
    (folder / item["file"]).write_text(probed)
    _purge()
    try:
        import test_round7
        test_round7.run_checks()
    except Exception as exc:
        return item["name"], "fail", f"{type(exc).__name__}: {exc}"
    module = __import__(item["file"][:-3])
    return item["name"], "pass", str(getattr(module, "_MUTANT_PROBE_HITS", 0))


def _hit_main():
    """Which still-passing mutants already change a value under run_checks."""
    import time
    from collections import Counter
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path

    from mutagen import PATH_FILES, generate

    here = Path(__file__).resolve().parent
    sources = {name: (here / name).read_text() for name in PATH_FILES}
    wanted = set(Path("/tmp/round7-still-passing.txt").read_text().split())
    items = [item for item in generate(sources) if item["name"] in wanted]
    print(f"probing {len(items)}", flush=True)
    started = time.monotonic()
    rows = []
    with ProcessPoolExecutor(max_workers=8, initializer=_worker_init, initargs=(str(here),)) as pool:
        for row in pool.map(_worker_hits, items, chunksize=4):
            rows.append(row)
            if len(rows) % 100 == 0:
                print(f"  {len(rows)}", flush=True)
    Path("/tmp/round7-hits.txt").write_text("\n".join(f"{name}\t{status}\t{detail}" for name, status, detail in rows) + "\n")
    counts = Counter((status, int(detail) > 0 if status == "pass" and detail.isdigit() else status) for name, status, detail in rows)
    print(f"done {len(rows)} in {time.monotonic() - started:.1f}s", flush=True)
    print(dict(counts), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "hits":
        _hit_main()
    else:
        _classify_main()
