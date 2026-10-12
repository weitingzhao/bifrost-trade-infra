"""Mechanical, single-site AST mutations; no recorder or test execution here.

TARGETS is the one inventory: Table A-2, Table B propagation/judgment,
Table C selection and the typed argument boundary. Input/output are strings.
"""
import ast

TARGETS = {
    'fold.py': ('_apply_unrecorded',),
    'ownerball.py': ('_ball',),
    'survive.py': ('kept', 'apply_keep'),
    'read.py': ('_is_folded', '_exact_pair_list', 'exact_types', 'bad_number',
                'bad_count', '_in_range', '_leaf_ok', '_bad_string', 'exact_tree', 'select', 'Folded.__init__'),
    'publish.py': ('_host_decision', '_merge_blocks', '_block_ok', '_summary',
                   '_counts', '_works_total', 'publish_total', '_publish_observer',
                   'publish_view', '_stamp', '_level1', '_level3', '_level4',
                   '_level5', '_level6', '_trim_works', '_trim_steps', '_trim_owner',
                   '_anything_cut', '_note', '_attach_events'),
    'validate.py': ('_round_lists', '_unrecorded_item'),
}

SWAPS = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE,
         ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
         ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot,
         ast.IsNot: ast.Is}


def generate(sources):
    """Return every listed mutation at every eligible site, without sampling.

Each entry includes a stable site id, original/replacement expression and the
complete mutated module. Walk paths, rather than line replacement, distinguish
multiple comparisons/operands on the same line. Nested functions are included.
"""
    out = []
    for filename, names in TARGETS.items():
        root = ast.parse(sources[filename])
        functions = [(node.name, node) for node in root.body if isinstance(node, ast.FunctionDef)]
        functions += [(cls.name + "." + node.name, node) for cls in root.body if isinstance(cls, ast.ClassDef)
                      for node in cls.body if isinstance(node, ast.FunctionDef)]
        for qualified, function in functions:
            if qualified not in names:
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
