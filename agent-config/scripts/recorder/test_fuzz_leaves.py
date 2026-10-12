"""Family C: real legal lifecycles, schema fields and nested leaves, resealed."""
import copy
import hashlib
import json

from harness import APPR, LOCATOR, N, P, R, RUN, WAIT_A, WAIT_D, WORK, LogBuilder
from model import SCHEMAS
from read import read_log
from test_rows import OBS


def _valid_sequence(kind, field):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T', goal='G', work_ref='ref')
    if kind == 'work_opened':
        return log.events, False
    declare = dict(step_id=P, name='p', who='C', kind='other', watch='none')
    if kind in ('step_started', 'step_seen', 'step_finished', 'step_superseded', 'note'):
        if kind in ('step_started', 'step_seen', 'step_finished'):
            declare['watch'] = 'process'
        log.add('step_declared', 'coordinator', at=2, **declare)
    if kind in ('step_seen', 'step_finished'):
        log.add('step_started', 'wrapper', at=3, step_id=P, run_id=RUN, command='echo', pid=123)
    if kind == 'step_declared':
        log.add('step_declared', 'coordinator', at=2, **declare)
        log.add('owner_wait_opened', 'coordinator', at=3, wait_id=WAIT_D, title='W', ref={'kind': 'none', 'id': 'c0ffee01'}, can_act='not_yet')
        fields = dict(step_id=N, name='n', who='C', kind='other', watch='none',
                      round=1, after=P, usual_s=10, usual_basis='declared', waiting_on=[WAIT_D],
                      replaces=P, replaces_text='replace')
        if field.startswith('locator'):
            fields.update(kind='release', watch='record', locator=LOCATOR)
        log.add(kind, 'coordinator', at=10, **fields)
    elif kind == 'step_started':
        log.add(kind, 'wrapper', at=3, step_id=P, run_id=RUN, command='echo', pid=123)
    elif kind == 'step_seen':
        log.add(kind, 'wrapper', at=10, step_id=P, run_id=RUN, sampled_at=10, alive=True, output_bytes=1, text='out')
    elif kind == 'step_finished':
        if field == 'reported':
            log.events[1]['watch'] = 'none'
            log.events[2]['by'] = 'coordinator'
            log.events[2].pop('command')
            log.add(kind, 'coordinator', at=10, step_id=P, run_id=RUN, reported='finished', quote='q')
        else:
            log.add(kind, 'wrapper', at=10, step_id=P, run_id=RUN, exit={'code': 0}, quote='q')
    elif kind == 'step_superseded':
        log.add(kind, 'coordinator', at=10, step_id=P, text='replace')
    elif kind == 'record_seen':
        log.add('step_declared', 'coordinator', at=2, step_id=R, name='r', who='C', kind='release', watch='record', locator=LOCATOR)
        log.add(kind, 'observer', at=10, step_id=R, sampled_at=10, found=True, uid='uid-1', started_at=5, ended_at=10, condition='True', reason_quote='q')
    elif kind == 'owner_wait_opened':
        log.add('step_declared', 'coordinator', at=2, **declare)
        log.add(kind, 'coordinator', at=3, wait_id=WAIT_A, title='old', ref={'kind': 'none', 'id': 'c0ffee02'}, can_act='not_yet')
        log.add(kind, 'coordinator', at=10, wait_id=WAIT_D, title='W', ref={'kind': 'none', 'id': 'c0ffee01'},
                can_act='not_yet', where='terminal', after=P, deadline=100, no_deadline=True,
                blocks_nothing=True, reply_needed=False, reply='r', reply_words='rw',
                advice='a', blocks_text='b', after_text='a', not_before_text='n', commands=['echo'], replaces=WAIT_A)
        log.events[-1].pop('deadline' if field == 'no_deadline' else 'no_deadline')
    elif kind in ('owner_wait_seen', 'owner_wait_ready', 'owner_wait_closed'):
        ref = {'kind': 'approval', 'id': APPR} if kind == 'owner_wait_seen' else {'kind': 'none', 'id': 'c0ffee01'}
        log.add('owner_wait_opened', 'coordinator', at=2, wait_id=WAIT_A, title='W', ref=ref, **({} if kind == 'owner_wait_seen' else {'can_act': 'not_yet'}))
        fields = dict(wait_id=WAIT_A)
        if kind == 'owner_wait_seen':
            fields.update(sampled_at=10, ref_state='pending', expires_at=100, number=1)
        if kind == 'owner_wait_closed':
            fields['how'] = 'done'
        log.add(kind, 'observer' if kind == 'owner_wait_seen' else 'coordinator', at=10, **fields)
    elif kind == 'work_closed':
        log.add(kind, 'coordinator', at=10, claim='landed')
    elif kind == 'note':
        log.add(kind, 'coordinator', at=10, step_id=P, text='n')
    elif kind == 'tail_repaired':
        log.add(kind, 'coordinator', at=10, repair_id='0-0123456789abcdef', bytes=1, sha256='ab' * 32)
    elif kind == 'observer_round':
        log = LogBuilder()
        log.add(kind, 'observer', at=10, round_id='ab12cd34', started_at=10, ended_at=10,
                confirmed=[f'approval:{APPR}'], failed=[{'key': f'step:{WORK}/{R}', 'error': 'timeout'}],
                unrecorded=[{'work_id': WORK, 'step_id': P, 'run_id': RUN}], truncated=True)
    else:
        raise AssertionError(kind)
    return log.events, kind == 'observer_round'


def _reseal(events):
    """Reseal the entire chain, including hostile JSON leaves and surrogate escapes."""
    previous = ''
    out = []
    for index, event in enumerate(events):
        event = dict(event, v=2, seq=index + 1, prev_sha256=previous)
        body = json.dumps(event, ensure_ascii=True, allow_nan=True, sort_keys=True, separators=(',', ':')).encode()
        previous = hashlib.sha256(body).hexdigest()
        out.append(previous.encode() + b' ' + body + b'\n')
    return b''.join(out)


def _paths(value, prefix):
    if type(value) is dict:
        for key, child in value.items():
            yield from _paths(child, prefix + (key,))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from _paths(child, prefix + (index,))
    else:
        yield prefix


def field_cases():
    rows = []
    for kind, schema in sorted(SCHEMAS.items()):
        for field in sorted(schema['required'] | schema['optional'] | {'at', 'by', 'type'}):
            events, observer = _valid_sequence(kind, field)
            target = events[-1]
            assert field in target, (kind, field)
            for path in _paths(target[field], (field,)):
                rows.append((kind, field, path, events, observer))
    events, observer = _valid_sequence("step_finished", "exit")
    events[-1]["exit"] = {"signal": "SIGTERM"}
    rows.append(("step_finished", "exit", ("exit", "signal"), events, observer))
    return rows


# Null leaf classification specified by the field table, independent of the
# reader used by the test. Global text/number limits have their own variants.
_BAD_VALUE = {'work_id', 'step_id', 'run_id', 'wait_id', 'round_id', 'repair_id',
              'sha256', 'usual_s', 'output_bytes', 'bytes', 'no_deadline',
              'blocks_nothing', 'reply_needed', 'replaces'}


def expected_null(kind, field, path):
    if field == 'type':
        return 'unknown_type'
    if field == 'ref':
        return 'bad_type'
    if field == 'exit':
        return 'bad_type'
    if field == 'locator':
        return 'bad_type'
    if field == 'waiting_on':
        return 'bad_value'
    if field in ('confirmed', 'failed', 'unrecorded'):
        return 'bad_type'
    if field in _BAD_VALUE or (kind == 'owner_wait_opened' and field == 'after') or field == 'truncated':
        return 'bad_value'
    return 'bad_type'


ROWS = field_cases()


def leaf_case(index):
    kind, field, path, original, observer = ROWS[index % len(ROWS)]
    events = copy.deepcopy(original)
    target = events[-1]
    for key in path[:-1]:
        target = target[key]
    # Most cases must reach field validation; limit variants exercise the
    # earlier boundary with the same valid sequence and complete chain.
    variant = (index // len(ROWS)) % 4
    leaf = (None, 10**400, '\ud800', 'x' * 10000 + '\u202e')[variant]
    target[path[-1]] = leaf
    expected = (expected_null(kind, field, path), 'bad_number', 'limit_text', 'limit_text')[variant]
    blob = _reseal(events)
    logs = [(WORK, _reseal(_valid_sequence('work_opened', 'title')[0]))] if observer else [(WORK, blob)]
    obs = [(OBS, blob)] if observer else []
    return ('丙', logs, obs, 10, 0, 'board', None), expected, kind, path


def test_fuzz_c_baselines_are_valid_and_every_schema_field_is_walked():
    for kind, field, path, events, observer in ROWS:
        loaded = read_log(OBS if observer else WORK, _reseal(events), observer=observer)
        assert loaded.broken_line is None and loaded.defects == [], (kind, field, path, loaded.defects)
    assert {kind for kind, *_ in ROWS} == set(SCHEMAS)


def assert_leaf_document(doc, expected, observer):
    defects = doc['observer'].get('defects', []) if observer else doc['works'][0].get('defects', [])
    assert [item['reason'] for item in defects] == [expected], (expected, doc)
    assert not (doc.get('observer', {}).get('log_invalid_at'))
    assert all('log_invalid_at' not in work for work in doc['works'])
