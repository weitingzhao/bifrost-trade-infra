"""Events blocks use typed trees and attach transactionally to open steps."""
import json
import pytest
from harness import P, RUN, WORK, LogBuilder, _chain
from publish import publish_total
from read import fold_total


def _folded(ended=False):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    log.add('step_declared', 'coordinator', step_id=P, name='p', who='C', watch='none', kind='other')
    log.add('step_started', 'coordinator', step_id=P, run_id=RUN)
    if ended:
        log.add('step_finished', 'coordinator', step_id=P, run_id=RUN, reported='finished')
    return fold_total([(WORK, _chain(log.events))], [], log.at)


@pytest.mark.parametrize('length', [0, 1, 29, 30, 31])
def test_event_rows_cap_exact_boundary(length):
    rows = [{'at': 1, 'text': 'n'}] * length
    doc = json.loads(publish_total(_folded(), 'board', {'events': {f'{WORK}/{P}': rows}}))
    assert 'recorder_failed' not in doc and doc['internal_errors'] == 0
    assert doc.get('incomplete', []) == (['events'] if length == 31 else [])
    step = doc['works'][0]['steps'][0]
    if length <= 30:
        assert step['events'] == rows
    else:
        assert 'events' not in step


@pytest.mark.parametrize('key,rows', [
    ('w1', []), ('w1//a1b2c3d4', []), ('missing/a1b2c3d4', []),
    ('w1/00000000', []), ('w1/a1b2c3d4', {}), ('w1/a1b2c3d4', [1]),
])
def test_event_block_bad_keys_and_rows_drop_events(key, rows):
    doc = json.loads(publish_total(_folded(), 'board', {'events': {key: rows}}))
    assert doc['incomplete'] == ['events']
    assert 'events' not in doc['works'][0]['steps'][0]
    assert doc['internal_errors'] == 0 and 'recorder_failed' not in doc


def test_event_blocks_do_not_attach_to_ended_steps():
    doc = json.loads(publish_total(_folded(True), 'board', {'events': {f'{WORK}/{P}': []}}))
    assert doc['incomplete'] == ['events']
    assert 'events' not in doc['works'][0]['steps'][0]


def test_bad_second_attachment_does_not_partly_apply_first():
    blocks = {'events': {f'{WORK}/{P}': [{'text': 'n'}], 'missing/00000000': []}}
    doc = json.loads(publish_total(_folded(), 'board', blocks))
    assert doc['incomplete'] == ['events']
    assert 'events' not in doc['works'][0]['steps'][0]
