"""Reduction preserves exact state vectors, prior cuts and byte-edge metadata."""
import json
import pytest
import publish
from harness import LOCATOR, RUN, WORK, LogBuilder, _chain
from read import fold_total


def _mixed():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    for index, state in enumerate(('done', 'failed', 'waiting', 'running', 'unknown', 'dead', 'slow', 'quiet')):
        step = f'{index + 1:08x}'
        watch = 'process' if state in ('unknown', 'dead', 'quiet') else 'none'
        log.add('step_declared', 'wrapper' if state == 'unknown' else 'coordinator', step_id=step,
                name=state, kind='other', watch=watch, who='C',
                **({'usual_s': 1, 'usual_basis': 'declared'} if state == 'slow' else {}))
        if state in ('waiting', 'unknown'):
            continue
        log.add('step_started', 'wrapper' if watch == 'process' else 'coordinator', step_id=step, run_id=RUN,
                **({'command': 'echo'} if watch == 'process' else {}))
        if state in ('done', 'failed'):
            log.add('step_finished', 'coordinator', step_id=step, run_id=RUN, reported='finished' if state == 'done' else 'failed')
        if state == 'dead':
            log.add('step_seen', 'observer', step_id=step, run_id=RUN, sampled_at=log.at + 1, alive=False)
        if state == 'quiet':
            log.add('step_seen', 'wrapper', at=600, step_id=step, run_id=RUN, sampled_at=600, alive=True, output_bytes=0)
    return fold_total([(WORK, _chain(log.events))], [], 600)


@pytest.mark.parametrize('level', [4, 5, 6])
def test_reduction_exact_state_vectors(monkeypatch, level):
    folded = _mixed()
    original = folded.document()
    assert [step['state'] for step in original['works'][0]['steps']] == ['done', 'failed', 'waiting', 'running', 'unknown', 'dead', 'slow', 'quiet']
    monkeypatch.setattr(publish, '_nbytes', lambda doc, n, feed, cut: 1 if n >= level else publish.PUBLISH_TARGET_BYTES + 1)
    doc = json.loads(publish.publish_total(folded))
    assert 'recorder_failed' not in doc
    work = doc['works'][0]
    assert work['title'] == 'T'
    if level == 4:
        assert [step['state'] for step in work['steps']] == ['unknown', 'dead', 'quiet', 'slow', 'running']
        assert work['omitted'] == dict(dead=0, done=1, failed=1, quiet=0, running=0, slow=0, unknown=0, waiting=1)
    else:
        assert work['state_counts'] == dict(dead=1, done=1, failed=1, quiet=1, running=1, slow=1, unknown=1, waiting=1)
        assert work['unknown_reasons'] == ['start_not_recorded']


@pytest.mark.parametrize('level', [3, 4, 5, 6])
def test_summary_counts_and_reasons_include_omitted_steps(monkeypatch, level):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    for index in range(26):
        record = index >= 20
        log.add('step_declared', 'coordinator' if record else 'wrapper', step_id=f'{index + 1:08x}',
                name='n', kind='release' if record else 'other', watch='record' if record else 'process', who='C',
                **({'locator': LOCATOR} if record else {}))
    folded = fold_total([(WORK, _chain(log.events))], [], log.at)
    monkeypatch.setattr(publish, '_nbytes', lambda doc, n, feed, cut: 1 if n >= level else publish.PUBLISH_TARGET_BYTES + 1)
    doc = json.loads(publish.publish_total(folded))
    assert 'recorder_failed' not in doc
    work = doc['works'][0]
    assert work['title'] == 'T'
    if level >= 5:
        assert work['state_counts']['unknown'] == 26
        assert work['unknown_reasons'] == ['start_not_recorded', 'not_confirmed']
    else:
        kept = 5 if level == 4 else 20
        assert work['steps_total'] == 26 and len(work['steps']) == kept
        assert work['omitted']['unknown'] == 26 - kept


def _many_owners():
    logs = []
    for index in range(3):
        log = LogBuilder()
        name = f'w{index}'
        log.add('work_opened', 'coordinator', work_id=name, title='T')
        for wait in range(20):
            log.add('owner_wait_opened', 'coordinator', wait_id=f'{wait + 1:08x}', title='title',
                    ref={'kind': 'none', 'id': f'{wait + 100:08x}'}, can_act='yes', advice='x' * 200)
        logs.append((name, _chain(log.events)))
    return fold_total(logs, [], 21)


def test_level_six_prior_cut_and_exact_byte_budget(monkeypatch):
    folded = _many_owners()
    assert len(folded.document()['owner_all']) == 60
    measured = publish._nbytes
    monkeypatch.setattr(publish, '_nbytes', lambda doc, n, feed, cut: 1 if n == 6 and len(doc['owner_all']) <= 5 else publish.PUBLISH_TARGET_BYTES + 1)
    reference = json.loads(publish.publish_total(folded, 'bad host'))
    assert reference['owner_all_cut'] == 55 and len(reference['owner_all']) == 5
    # Now measure actual bytes at level 6. The chosen last item fits exactly;
    # all trial metadata (prior cuts, host and feed markers) is included.
    target = len(publish.encoded(reference))
    monkeypatch.setattr(publish, 'PUBLISH_TARGET_BYTES', target)
    monkeypatch.setattr(publish, '_nbytes', lambda doc, n, feed, cut: measured(doc, n, feed, cut) if n == 6 else target + 1)
    raw = publish.publish_total(folded, 'bad host')
    doc = json.loads(raw)
    assert 'recorder_failed' not in doc
    assert len(raw) == target
    assert doc['reduced'] == 6
    assert doc['owner_all_cut'] == 55 and len(doc['owner_all']) == 5
    assert doc['incomplete'] == ['host', 'owner_all']
    monkeypatch.setattr(publish, 'PUBLISH_TARGET_BYTES', target - 1)
    smaller = json.loads(publish.publish_total(folded, 'bad host'))
    assert 'recorder_failed' not in smaller
    assert len(smaller['owner_all']) == 4 and smaller['owner_all_cut'] == 56
    assert smaller['incomplete'] == ['host', 'owner_all']


@pytest.mark.parametrize('kind', ['works', 'steps', 'owner', 'feed'])
def test_exact_publication_caps_do_not_claim_a_cut(kind):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    logs = []
    if kind == 'works':
        for index in range(30):
            opened = LogBuilder()
            opened.add('work_opened', 'coordinator', work_id=f'w{index}', title='T')
            logs.append((f'w{index}', _chain(opened.events)))
    elif kind == 'steps':
        for index in range(20):
            log.add('step_declared', 'coordinator', step_id=f'{index + 1:08x}', name='n', who='C', kind='other', watch='none')
        logs = [(WORK, _chain(log.events))]
    elif kind == 'owner':
        for index in range(2):
            owned = LogBuilder()
            owned.add('work_opened', 'coordinator', work_id=f'w{index}', title='T')
            for wait in range(15):
                owned.add('owner_wait_opened', 'coordinator', wait_id=f'{wait + 1:08x}', title='W', ref={'kind': 'none', 'id': f'{wait + 100:08x}'}, can_act='yes')
            logs.append((f'w{index}', _chain(owned.events)))
    else:
        for _ in range(25):
            log.add('note', 'coordinator', text='n')
        logs = [(WORK, _chain(log.events))]
    doc = json.loads(publish.publish_total(fold_total(logs, [], 100)))
    assert 'recorder_failed' not in doc
    assert 'full_at' not in doc and 'reduced' not in doc
    assert 'incomplete' not in doc and 'omitted_works' not in doc
    assert 'owner_all_cut' not in doc and 'feed_cut' not in doc
    if kind == 'steps':
        assert len(doc['works'][0]['steps']) == 20
        assert 'omitted' not in doc['works'][0]


@pytest.mark.parametrize('cut', ['commands', 'blocks', 'feed', 'steps', 'works', 'owner'])
def test_initial_cut_metadata_is_measured_before_reduction(monkeypatch, cut):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    if cut == 'commands':
        log.add('owner_wait_opened', 'coordinator', wait_id='f1b2c3d4', title='W',
                ref={'kind': 'none', 'id': 'c0ffee01'}, can_act='yes', where='terminal', commands=['echo'])
    elif cut == 'steps':
        for index in range(21):
            log.add('step_declared', 'coordinator', step_id=f'{index + 1:08x}', name='n', who='C', kind='other', watch='none')
    for _ in range(26 if cut == 'feed' else 25):
        log.add('note', 'coordinator', text='x' * 200)
    logs = [(WORK, _chain(log.events))]
    if cut == 'works':
        for index in range(30):
            opened = LogBuilder()
            opened.add('work_opened', 'coordinator', work_id=f'z{index}', title='T')
            logs.append((f'z{index}', _chain(opened.events)))
    folded = _many_owners() if cut == 'owner' else fold_total(logs, [], 100)
    blocks = {'bad': 'value'} if cut == 'blocks' else None
    reference = publish.publish_total(folded, 'board', blocks)
    doc = json.loads(reference)
    assert 'recorder_failed' not in doc and doc['full_at'] == 'local_board'
    target = len(reference) - 1
    monkeypatch.setattr(publish, 'PUBLISH_TARGET_BYTES', target)
    reduced = json.loads(publish.publish_total(folded, 'board', blocks))
    assert 'recorder_failed' not in reduced
    assert reduced.get('reduced', 0) > 0
    assert reduced['full_at'] == 'local_board'
    assert set(doc.get('incomplete', [])) <= set(reduced.get('incomplete', []))


@pytest.mark.parametrize('closed', [False, True])
def test_work_omission_counts_exact_open_and_closed(closed):
    logs = []
    for index in range(33 if closed else 31):
        name = f'w{index:02}'
        log = LogBuilder()
        log.add('work_opened', 'coordinator', work_id=name, title='T')
        if closed and index >= 30:
            log.add('work_closed', 'coordinator', claim='stopped')
        logs.append((name, _chain(log.events)))
    doc = json.loads(publish.publish_total(fold_total(logs, [], 20)))
    assert doc['works_total'] == {'open': 30 if closed else 31, 'closed': 3 if closed else 0}
    assert doc['omitted_works'] == {'open': 0 if closed else 1, 'closed': 3 if closed else 0}
    assert len(doc['works']) == 30
    assert doc.get('incomplete', []) == ([] if closed else ['works'])
    assert doc['full_at'] == 'local_board'


def test_structural_step_omission_counts_each_actual_state():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    for index in range(26):
        log.add('step_declared', 'coordinator', step_id=f'{index + 1:08x}', name='n', kind='other', who='C', watch='none')
    doc = json.loads(publish.publish_total(fold_total([(WORK, _chain(log.events))], [], 100)))
    work = doc['works'][0]
    assert len(work['steps']) == 20 and work['steps_total'] == 26
    assert work['omitted'] == dict(dead=0, done=0, failed=0, quiet=0, running=0, slow=0, unknown=0, waiting=6)


def test_closed_summaries_stay_summaries_at_level_four(monkeypatch):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id='closed', title='T')
    log.add('step_declared', 'coordinator', step_id='11111111', name='n', kind='other', who='C', watch='none')
    log.add('step_started', 'coordinator', step_id='11111111', run_id=RUN)
    log.add('step_finished', 'coordinator', step_id='11111111', run_id=RUN, reported='finished')
    log.add('work_closed', 'coordinator', claim='stopped')
    folded = fold_total([('closed', _chain(log.events))], [], 10)
    monkeypatch.setattr(publish, '_nbytes', lambda doc, level, feed, cut: 1 if level >= 4 else publish.PUBLISH_TARGET_BYTES + 1)
    doc = json.loads(publish.publish_total(folded))
    work = doc['works'][0]
    assert 'recorder_failed' not in doc
    assert work['state_counts']['done'] == 1
    assert 'steps' not in work and 'steps_total' not in work
    assert work['closed_claim'] == 'stopped'


@pytest.mark.parametrize('level', range(7))
@pytest.mark.parametrize('already_cut', [False, True])
@pytest.mark.parametrize('feed_trimmed', [False, True])
def test_measured_stamp_matches_final_metadata(level, already_cut, feed_trimmed):
    import copy
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    for _ in range(3):
        log.add('note', 'coordinator', text='n')
    folded = fold_total([(WORK, _chain(log.events))], [], 10)
    doc = json.loads(publish.publish_total(folded, 'board', {'bad': 'x'} if already_cut else None))
    doc.pop('full_at', None)
    doc.pop('reduced', None)
    if feed_trimmed:
        doc['feed'] = doc['feed'][-2:]
    expected = copy.deepcopy(doc)
    if level:
        expected['reduced'] = level
    if feed_trimmed:
        expected['feed_cut'] = 1
        expected['incomplete'] = ['bad', 'feed'] if already_cut else ['feed']
    if level or already_cut or feed_trimmed:
        expected['full_at'] = 'local_board'
    stamped = publish._stamp(doc, level, 3, already_cut)
    assert stamped == expected
    assert publish._nbytes(doc, level, 3, already_cut) == len(publish.encoded(expected))
