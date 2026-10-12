"""Table B markers from logs, then the actual reducers and published bytes.

Only byte measurement is injected to select each level deterministically; no
fold document is authored or sealed by a test. Size pressure and fixtures are
also tested separately with actual measured bytes.
"""
import json
import pytest
import publish
from harness import APPR, P, RUN, WAIT_A, WORK, LogBuilder, _chain
from model import MAX_EVENTS, PUBLISH_TARGET_BYTES
from read import PROBES, fold_total
from test_rows import OBS, _round

_CACHE = {}


def _handle(row):
    if row in _CACHE:
        return _CACHE[row]
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    observer = []
    unread = 0
    now = 20
    if row == 1:
        unread = 3
    elif row == 5:
        observer = [_round(20, [dict(work_id=WORK, step_id=P, run_id=RUN)])]
    elif row == 6:
        for index in range(MAX_EVENTS - 1):
            log.add('note', 'coordinator', at=2, text='n')
    elif row == 7:
        log.add('note', 'coordinator', at=2, text='n', extra='invalid')
    elif row == 8:
        log.add('step_declared', 'wrapper', at=2, step_id=P, name='p', who='W', kind='other', watch='process')
    elif row == 9:
        log.add('owner_wait_opened', 'coordinator', at=2, wait_id=WAIT_A, title='ask', ref={'kind': 'approval', 'id': APPR})
    elif row == 10:
        observer = [dict(log.events[0])]
    elif row == 13:
        log.add('step_declared', 'wrapper', at=2, step_id=P, name='p', who='W', kind='other', watch='process')
        log.add('step_started', 'wrapper', at=3, step_id=P, run_id=RUN, command='echo')
        log.add('step_seen', 'wrapper', at=200, step_id=P, run_id=RUN, sampled_at=200, alive=True, output_bytes=1)
        now = 200
    data = _chain(log.events)
    if row == 2:
        data += b'invalid\n'
    elif row == 3:
        data += b'torn'
    obs = [(OBS, _chain(observer))] if observer else []
    if row == 11:
        def fail():
            raise RuntimeError('test injected')
        PROBES['line'] = fail
    try:
        folded = fold_total([(WORK, data)], obs, now, unread)
    finally:
        PROBES['line'] = None
    _CACHE[row] = folded
    return folded


@pytest.mark.parametrize('level', range(7))
@pytest.mark.parametrize('row', [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13])
def test_table_b_real_path_at_every_level(monkeypatch, row, level):
    folded = _handle(row)
    original = folded.document()
    # All transformations and the final shape check operate normally.
    monkeypatch.setattr(publish, '_nbytes', lambda doc, n, feed, cut: 1 if n >= level else PUBLISH_TARGET_BYTES + 1)
    doc = json.loads(publish.publish_total(folded, 'board'))
    assert 'recorder_failed' not in doc
    assert doc.get('reduced', 0) == level
    work = doc['works'][0]
    if row == 1:
        assert doc['logs_unread'] == 3 and doc['fold_complete'] is False
    elif row == 2:
        assert (work['log_invalid_at'], work['log_invalid_why']) == (2, 'bad_line')
        assert doc['fold_complete'] is False
    elif row == 3:
        assert work['torn_tail'] is True and doc['fold_complete'] is False
    elif row == 5:
        assert work['unrecorded_runs'] == 1
        assert doc['ball'] == {'holder': 'unknown', 'why': 'run_unrecorded'}
    elif row == 6:
        assert work['log_full'] is True
    elif row == 7:
        if 'defects' in work:
            assert work['defects'] == [{'seq': 2, 'reason': 'unknown_field'}]
        else:
            assert work['defects_count'] == 1
    elif row == 8:
        if 'steps' in work:
            assert work['steps'][0]['state'] == 'unknown'
            assert work['steps'][0]['reason'] == 'start_not_recorded'
        else:
            assert work['state_counts']['unknown'] == 1
            assert work['unknown_reasons'] == ['start_not_recorded']
    elif row == 9:
        assert doc['owner_all'][0]['can_act'] == 'unknown'
        assert doc['owner_all'][0]['reason'] == 'not_confirmed'
    elif row == 10:
        assert doc['observer']['defects_count'] == 1
    elif row == 11:
        assert doc['internal_errors'] == 1
        assert doc['internal'] == original['internal']
    elif row == 12:
        assert doc['works_total'] == {'open': 1, 'closed': 0}
        assert len(doc['feed']) + doc.get('feed_cut', 0) == len(original['feed'])
        assert len(doc['owner_all']) + doc.get('owner_all_cut', 0) == len(original['owner_all'])
    elif row == 13:
        if 'steps' in work:
            assert work['steps'][0]['gap'] is True
        else:
            assert 'gap' not in work
    if row in (1, 2, 3, 5, 8, 9, 11):
        assert doc['ball']['holder'] != 'nobody'


def test_table_b_fallback_real_path():
    doc = json.loads(publish.publish_total(fold_total([], [], True)))
    assert doc['recorder_failed']['reason'] == 'invalid_argument'
    assert doc['ball']['holder'] == 'unknown'
    assert doc['fold_complete'] is False
    assert 'works_total' not in doc and 'owner_all_cut' not in doc
