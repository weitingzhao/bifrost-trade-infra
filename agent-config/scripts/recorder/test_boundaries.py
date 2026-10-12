"""Exact Unicode, numeric, tree and publication argument edges, through bytes."""
import json
import pytest
from harness import WORK, LogBuilder, _chain
from publish import publish_total
from read import fold_total


@pytest.mark.parametrize('code', sorted({0, 1, 30, 31, 32, 126, 127, 128, 158, 159, 160,
                                       0xd7ff, 0xd800, 0xd801, 0xdffe, 0xdfff, 0xe000,
                                       0x2027, 0x2028, 0x2029, 0x202a, 0x202b, 0x202d, 0x202e, 0x202f,
                                       0x2065, 0x2066, 0x2067, 0x2068, 0x2069, 0x206a}))
def test_text_control_range_boundaries(code):
    char = chr(code)
    bad = code <= 31 or 127 <= code <= 159 or 0xd800 <= code <= 0xdfff or 0x2028 <= code <= 0x202e or 0x2066 <= code <= 0x2069
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title=char)
    # ASCII JSON encoding permits hostile surrogate leaves to reach the reader.
    from test_fuzz_leaves import _reseal
    folded = fold_total([(WORK, _reseal(log.events))], [], 1)
    local = folded.document()
    assert [x['reason'] for x in local['works'][0]['defects']] == (['limit_text'] if bad else [])
    assert local['internal_errors'] == 0
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'recent': [char]}))
    assert doc.get('incomplete', []) == (['blocks'] if bad else [])
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('depth,valid', [(7, True), (8, True), (9, False)])
def test_block_tree_depth_boundary(depth, valid):
    nested = []
    for _ in range(depth - 2):
        nested = [nested]
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'graph': nested}))
    assert doc.get('incomplete', []) == ([] if valid else ['blocks'])
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('block,limit', [('recent', 30), ('graph', 60), ('queue', 30)])
@pytest.mark.parametrize('delta', [-1, 0, 1])
def test_block_array_cap_boundary(block, limit, delta):
    value = ['x'] * (limit + delta)
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {block: value}))
    assert doc.get('incomplete', []) == ([block] if delta == 1 else [])
    if delta != 1:
        assert doc[block] == value
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('length', [199, 200, 201])
def test_recent_string_cap_boundary(length):
    value = ['x' * length]
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'recent': value}))
    assert doc.get('incomplete', []) == (['recent'] if length == 201 else [])
    if length < 201:
        assert doc['recent'] == value


@pytest.mark.parametrize('host', ['', 'a', 'a' * 63, 'a' * 64, 'a' * 65, None])
def test_host_length_boundaries(host):
    doc = json.loads(publish_total(fold_total([], [], 1), host))
    bad = type(host) is str and len(host) == 65
    assert doc.get('incomplete', []) == (['host'] if bad else [])
    if host and not bad:
        assert doc['host'] == host
    else:
        assert 'host' not in doc


_NUMERIC_EDGES = [
    (-2**53, True), (2**53, True), (-2**53 - 1, False), (2**53 + 1, False),
    (float(-2**53), True), (float(2**53), True),
    (float(-2**53 - 2), False), (float(2**53 + 2), False),
]


@pytest.mark.parametrize('now,valid', _NUMERIC_EDGES)
@pytest.mark.parametrize('nonempty', [False, True])
def test_now_exact_numeric_endpoints_and_neighbours(now, valid, nonempty):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    logs = [(WORK, _chain(log.events))] if nonempty else []
    doc = json.loads(publish_total(fold_total(logs, [], now)))
    assert doc['internal_errors'] == 0
    if valid:
        assert 'recorder_failed' not in doc
        assert doc['at'] == now
    else:
        assert doc['recorder_failed'] == {'stage': 'fold', 'reason': 'invalid_argument', 'argument': 'now'}


@pytest.mark.parametrize('value,valid', _NUMERIC_EDGES)
def test_block_leaf_numeric_endpoints_and_neighbours(value, valid):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'graph': [value]}))
    assert doc['internal_errors'] == 0
    assert doc.get('incomplete', []) == ([] if valid else ['blocks'])
    if valid:
        assert doc['graph'] == [value]


@pytest.mark.parametrize('value', [True, False, 0, 1, 1.0, -0.0, 'text'])
def test_valid_block_leaf_types_are_kept(value):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'graph': [value]}))
    assert doc.get('incomplete', []) == []
    assert doc['graph'] == [value]


@pytest.mark.parametrize('key', ['bad\nkey', '\ud800', '\u202e'])
def test_hostile_nested_block_keys_drop_blocks(key):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'graph': [{key: 'x'}]}))
    assert doc['incomplete'] == ['blocks']
    assert 'graph' not in doc and doc['internal_errors'] == 0


@pytest.mark.parametrize('argument', ['logs', 'observer'])
@pytest.mark.parametrize('pair', [(), ('w1',), ('w1', b'', 1), ('w1', ''), ('w1', None), ('w1', bytearray()), ('w1', [])])
def test_pair_arity_and_data_types_at_exact_boundary(argument, pair):
    args = dict(logs=[], observer=[], now=1)
    args[argument] = [pair]
    doc = json.loads(publish_total(fold_total(**args)))
    assert doc['recorder_failed']['reason'] == 'invalid_argument'
    assert doc['recorder_failed']['argument'] == argument
    assert doc['internal_errors'] == 0


def test_now_type_has_priority_when_several_arguments_are_invalid():
    doc = json.loads(publish_total(fold_total('bad logs', 'bad observer', None, True)))
    assert doc['recorder_failed']['argument'] == 'now'
    assert doc['internal_errors'] == 0


def test_bad_observer_filename_does_not_apply_its_valid_round():
    from test_rows import _round
    from harness import P, RUN
    round = _round(20, [dict(work_id='missing', step_id=P, run_id=RUN)])
    doc = json.loads(publish_total(fold_total([], [('bad.jsonl', _chain([round]))], 20)))
    assert doc['observer'] == {'files_unread': 1}
    assert doc['ball']['holder'] == 'nobody'
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('observer', [False, True])
def test_selection_capacity_includes_exact_byte_limit(observer):
    size = (16 if observer else 64) * 1024 * 1024
    data = b'x' * size  # no complete line: the test measures selection, not 64 MiB parsing
    if observer:
        files = [('2026-10-11-0001.jsonl', data)]
        doc = fold_total([], files, 1).document()
        assert doc['observer'] == {}
    else:
        doc = fold_total([('a', data), ('b', b'')], [], 1).document()
        assert doc['logs_unread'] == 0
        assert [work['work_id'] for work in doc['works']] == ['a', 'b']
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('block,value,valid', [
    ('coordinator', {}, True), ('coordinator', {'at': 1.5, 'state': 's', 'note': 'n'}, True),
    ('coordinator', [], False), ('coordinator', {'other': 1}, False),
    ('coordinator', {'at': True}, False), ('coordinator', {'state': 1}, False),
    ('coordinator', {'note': 1}, False), ('coordinator', {'at': '1'}, False),
    ('roadmap', {}, True), ('roadmap', [], False), ('usage', {'a': 1}, True), ('usage', [], False),
    ('events', {}, True), ('events', [], False), ('graph', {}, False), ('queue', {}, False),
    ('recent', {}, False),
])
def test_every_block_valid_shape_and_field_types(block, value, valid):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {block: value}))
    assert 'recorder_failed' not in doc and doc['internal_errors'] == 0
    assert doc.get('incomplete', []) == ([] if valid else [block])
    if valid and block != 'events':
        assert doc[block] == value
    elif not valid:
        assert block not in doc


@pytest.mark.parametrize('host,expected', [(None, None), ('', None), ('board', 'board'), ('bad host', None)])
def test_fallback_host_is_kept_omitted_or_marked_exactly(host, expected):
    doc = json.loads(publish_total(fold_total([], [], True), host))
    assert doc.get('host') == expected
    assert doc['incomplete'] == (['feed', 'host', 'owner_all', 'works'] if host == 'bad host' else ['feed', 'owner_all', 'works'])
    assert doc['internal_errors'] == 0
    assert doc['recorder_failed']['reason'] == 'invalid_argument'


def test_observer_capacity_suffix_valid_round_is_not_read():
    from test_rows import _round
    from harness import P, RUN
    round = _round(20, [dict(work_id='missing', step_id=P, run_id=RUN)])
    files = [('2026-10-11-0002.jsonl', b'x' * (16 * 1024 * 1024 + 1)),
             ('2026-10-11-0001.jsonl', _chain([round]))]
    doc = json.loads(publish_total(fold_total([], files, 20)))
    assert doc['observer'] == {'files_unread': 2}
    assert doc['ball']['holder'] == 'nobody'
    assert doc['internal_errors'] == 0


@pytest.mark.parametrize('blocks', [True, 1, 'text', [], (), [1]])
def test_non_dict_block_roots_are_named_blocks(blocks):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', blocks))
    assert 'recorder_failed' not in doc and doc['internal_errors'] == 0
    assert doc['incomplete'] == ['blocks']


@pytest.mark.parametrize('key,expected', [('unknown_block', 'blocks'), ('password', 'blocks')])
def test_unknown_and_sensitive_block_names_are_classified_exactly(key, expected):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {key: 'x'}))
    assert doc['incomplete'] == [expected]
    assert 'recorder_failed' not in doc and doc['internal_errors'] == 0


@pytest.mark.parametrize('leaf', [True, 1, 1.5, [], {}])
def test_recent_non_string_items_are_named_recent(leaf):
    doc = json.loads(publish_total(fold_total([], [], 1), 'board', {'recent': [leaf]}))
    assert 'recorder_failed' not in doc and doc['internal_errors'] == 0
    assert doc['incomplete'] == ['recent']
