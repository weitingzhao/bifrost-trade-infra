"""Mechanical, single-site AST mutations; no recorder or test execution here.

Scope is every function of the modules on the fold and publish path, minus
EXCLUSIONS. Each exclusion names why that function is not on the path.
Input/output are strings.
"""
import ast

PATH_FILES = (
    'contextual.py',
    'fold.py',
    'model.py',
    'ownerball.py',
    'publish.py',
    'read.py',
    'redact_bound.py',
    'survive.py',
    'validate.py',
)

# file:qualified-name -> why it is not reachable from fold_total or publish_total.
EXCLUSIONS = {
    'fold.py:select_logs': 'Caller-side mtime cut. fold never sees a clock or a directory.',
    'fold.py:_prepare': 'Legacy event-list adapter. fold receives ReadLog values from read_log.',
    'fold.py:_rounds': 'Legacy observer adapter. fold reads rounds from the observer ReadLog.',
    'read.py:round_trip': 'Writer check before append. Not called from fold_total or publish_total.',
    'validate.py:refusal': 'Writer pre-check. Not called from fold_total or publish_total.',
    'validate.py:classify': 'Only refusal and the excluded _rounds helper call it. The byte path uses read_log.',
}

SWAPS = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE,
         ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
         ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot,
         ast.IsNot: ast.Is}


def _functions(root):
    found = [(node.name, node) for node in root.body if isinstance(node, ast.FunctionDef)]
    found += [
        (cls.name + "." + node.name, node)
        for cls in root.body if isinstance(cls, ast.ClassDef)
        for node in cls.body if isinstance(node, ast.FunctionDef)
    ]
    return found


def generate(sources):
    """Return every mutation of every non-excluded function, without sampling.

Each entry includes a stable site id, original/replacement expression and the
complete mutated module. Nested functions are walked inside their parent.
"""
    out = []
    for filename, source in sources.items():
        if not source or not source.strip():
            continue
        root = ast.parse(source)
        for qualified, function in _functions(root):
            if f'{filename}:{qualified}' in EXCLUSIONS:
                continue
            def emit(node, kind, field, replacement, ordinal=0):
                site = f'{filename}:{qualified}:{node.lineno}:{node.col_offset}:{kind}:{ordinal}'
                cloned = ast.parse(sources[filename])
                target = next(n for n in ast.walk(cloned) if type(n) is type(node) and
                              getattr(n, 'lineno', None) == node.lineno and
                              getattr(n, 'col_offset', None) == node.col_offset)
                before = ast.unparse(target)
                if field is None:
                    class Replace(ast.NodeTransformer):
                        def generic_visit(self, item):
                            if item is target:
                                return replacement
                            return super().generic_visit(item)
                    cloned = Replace().visit(cloned)
                    after = ast.unparse(replacement)
                else:
                    setattr(target, field, replacement)
                    after = ast.unparse(target)
                ast.fix_missing_locations(cloned)
                source = ast.unparse(cloned) + '\n'
                # A compiler error is a generator defect, never a killed mutant.
                compile(source, filename, 'exec')
                out.append(dict(name=site, file=filename, function=qualified,
                                kind=kind, before=before, after=after, source=source))

            def walk(node, guarded=False):
                if isinstance(node, ast.BoolOp):
                    for index in range(len(node.values)):
                        values = node.values[:index] + node.values[index + 1:]
                        replacement = values[0] if len(values) == 1 else ast.BoolOp(op=node.op, values=values)
                        emit(node, 'operand', None, replacement, index)
                if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                    emit(node, 'negate', 'test', ast.UnaryOp(op=ast.Not(), operand=node.test))
                if isinstance(node, ast.comprehension):
                    for index, condition in enumerate(node.ifs):
                        # Conditions are normal positioned expressions.
                        emit(condition, 'negate', None, ast.UnaryOp(op=ast.Not(), operand=condition), index)
                if isinstance(node, ast.Compare):
                    for index, operator in enumerate(node.ops):
                        if type(operator) in SWAPS:
                            ops = list(node.ops)
                            ops[index] = SWAPS[type(operator)]()
                            emit(node, 'compare', 'ops', ops, index)
                    for index, value in enumerate(child for operand in [node.left] + node.comparators for child in ast.walk(operand)):
                        if isinstance(value, ast.Constant) and type(value.value) in (int, str):
                            neighbours = (value.value - 1, value.value + 1) if type(value.value) is int else (value.value[:-1], value.value + '~')
                            for nth, neighbour in enumerate(neighbours):
                                if neighbour == value.value:
                                    continue
                                emit(value, 'constant', 'value', neighbour, index * 2 + nth)
                if guarded and isinstance(node, (ast.Return, ast.Continue)):
                    emit(node, 'guard_pass', None, ast.Pass())
                for child in ast.iter_child_nodes(node):
                    walk(child, guarded or isinstance(node, ast.If))
            walk(function)
    assert len({item['name'] for item in out}) == len(out)
    return out
