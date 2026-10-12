"""Handle identity and round-five planted violations, through public byte entries."""
import copy
import gc
import importlib.util
import json
import pickle
import weakref
from pathlib import Path

import pytest

from harness import LOCATOR, P, R, RUN, RUN2, WORK, LogBuilder, _chain, round_for
from publish import publish_total
from read import Folded, fold_total
from test_rows import OBS, _round


def _invalid(value):
    doc = json.loads(publish_total(value))
    assert doc['recorder_failed'] == {'stage': 'publish', 'reason': 'invalid_argument', 'argument': 'document'}
    assert doc['internal_errors'] == 0


def test_writing_any_handle_attribute_fails():
    for folded in (fold_total([], [], 1), fold_total([], [], True)):
        for name in ('_doc', '_token', 'document', 'anything', '__weakref__', '__class__'):
            for setter in (setattr, object.__setattr__):
                with pytest.raises(AttributeError):
                    setter(folded, name, {})
        assert not hasattr(folded, '__dict__')


def test_object_new_shell_is_invalid_argument():
    _invalid(object.__new__(Folded))


def test_copy_is_invalid_argument():
    _invalid(copy.copy(fold_total([], [], 1)))


def test_deepcopy_is_invalid_argument():
    _invalid(copy.deepcopy(fold_total([], [], 1)))


def test_pickle_is_invalid_argument():
    folded = fold_total([], [], 1)
    for protocol in range(2, pickle.HIGHEST_PROTOCOL + 1):
        _invalid(pickle.loads(pickle.dumps(folded, protocol)))


def test_second_import_is_invalid_argument():
    spec = importlib.util.spec_from_file_location('recorder_other_read', Path(__file__).with_name('read.py'))
    other = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = other
    try:
        spec.loader.exec_module(other)
        _invalid(other.fold_total([], [], 1))
    finally:
        del sys.modules[spec.name]


def test_public_constructor_rejects_every_nonprivate_token():
    for token in (None, object(), fold_total([], [], 1)):
        with pytest.raises(TypeError):
            Folded(token, {})


def test_fallback_identity_cannot_be_changed_by_caller():
    for bad in (False, True):
        folded = fold_total([], [], True if bad else 1)
        before = publish_total(folded)
        doc = folded.document()
        doc.clear()
        doc.update(fold_total([], [], 1 if bad else True).document())
        assert publish_total(folded) == before
        assert ('recorder_failed' in json.loads(before)) is bad


def test_registry_does_not_retain_handle_or_confuse_new_shells():
    folded = fold_total([], [], 1)
    ref = weakref.ref(folded)
    del folded
    gc.collect()
    assert ref() is None
    for _ in range(100):
        _invalid(object.__new__(Folded))


@pytest.mark.parametrize('watch', ['none', 'process', 'record'])
def test_different_run_id_counts_on_open_recorded_step(watch):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', work_id=WORK, title='T')
    fields = dict(step_id=P, name='n', who='C', kind='release' if watch == 'record' else 'other', watch=watch)
    if watch == 'record':
        fields['locator'] = LOCATOR
    log.add('step_declared', 'coordinator', **fields)
    if watch != 'record':
        log.add('step_started', 'wrapper' if watch == 'process' else 'coordinator', step_id=P, run_id=RUN, **({'command': 'echo'} if watch == 'process' else {}))
    observer = _round(20, [dict(work_id=WORK, step_id=P, run_id=RUN2)])
    doc = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [(OBS, _chain([observer]))], 20)))
    assert doc['works'][0]['unrecorded_runs'] == 1
    assert doc['ball'] == {'holder': 'unknown', 'why': 'run_unrecorded'}
    assert doc['internal_errors'] == 0


def test_unread_work_unrecorded_forces_unknown_without_per_work_marker():
    observer = _round(20, [dict(work_id='missing', step_id=P, run_id=RUN)])
    doc = json.loads(publish_total(fold_total([], [(OBS, _chain([observer]))], 20)))
    assert doc['works'] == []
    assert doc['ball'] == {'holder': 'unknown', 'why': 'run_unrecorded'}
    assert doc['internal_errors'] == 0


def test_record_created_since_restarts_after_disappearance():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    log.add('step_declared', 'coordinator', at=2, step_id=R, name='r', who='C', kind='release', watch='record', locator=LOCATOR)
    for at, found in ((10, True), (20, False), (30, True)):
        log.add('record_seen', 'observer', at=at, sampled_at=at, step_id=R, found=found, **({'uid': 'uid-1'} if found else {}))
    doc = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [(OBS, _chain([round_for(30, [f'step:{WORK}/{R}'])]))], 30)))
    assert doc['works'][0]['defects'] == []
    assert doc['ball']['why'] == 'record_created'
    assert doc['ball']['since'] == 30


def test_unread_names_merge_sort_then_cut_twenty():
    huge = b'x' * (64 * 1024 * 1024 + 1)
    logs = [('z', b''), ('z', b''), ('a', huge)] + [(f'b{i:02}', b'') for i in range(25)]
    for ordered in (logs, logs[::-1]):
        doc = fold_total(ordered, [], 1).document()
        assert doc['logs_unread'] == 28
        assert doc['logs_unread_names'] == ['a'] + [f'b{i:02}' for i in range(19)]


def test_object_setattr_cannot_swap_handle_class():
    class Empty:
        __slots__ = ('__weakref__',)
    folded = fold_total([], [], 1)
    with pytest.raises(AttributeError):
        object.__setattr__(folded, '__class__', Empty)


@pytest.mark.parametrize('age, counts', [(180, True), (181, False)])
@pytest.mark.parametrize('ghost', [False, True])
def test_unrecorded_round_expiry_exact_boundary(age, counts, ghost):
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    item = dict(work_id='missing' if ghost else WORK, step_id=P, run_id=RUN)
    folded = fold_total([(WORK, _chain(log.events))], [(OBS, _chain([_round(20, [item])]))], 20 + age)
    doc = json.loads(publish_total(folded))
    assert doc['internal_errors'] == 0
    assert doc['works'][0].get('unrecorded_runs', 0) == int(counts and not ghost)
    assert (doc['ball']['why'] == 'run_unrecorded') is counts


def test_unread_logs_override_running_agent_ball():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    log.add('step_declared', 'coordinator', at=2, step_id=P, name='n', who='C', kind='other', watch='none')
    log.add('step_started', 'coordinator', at=3, step_id=P, run_id=RUN)
    doc = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [], 3, 1)))
    assert doc['works'][0]['steps'][0]['state'] == 'running'
    assert doc['ball'] == {'holder': 'unknown', 'why': 'fold_incomplete'}
    assert doc['fold_complete'] is False


def test_unrecorded_withdrawn_wrapper_stays_absent_without_internal_error():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    log.add('step_declared', 'wrapper', at=2, step_id=P, name='n', who='W', kind='other', watch='process')
    log.add('step_superseded', 'coordinator', at=3, step_id=P)
    observer = _round(20, [dict(work_id=WORK, step_id=P, run_id=RUN)])
    doc = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [(OBS, _chain([observer]))], 20)))
    assert doc['works'][0]['steps'] == []
    assert doc['works'][0]['unrecorded_runs'] == 1
    assert doc['internal_errors'] == 0 and 'recorder_failed' not in doc


def test_unrecorded_does_not_overwrite_invalid_wrapper_observation():
    log = LogBuilder()
    log.add('work_opened', 'coordinator', at=1, work_id=WORK, title='T')
    log.add('step_declared', 'wrapper', at=2, step_id=P, name='n', who='W', kind='other', watch='process')
    observer = _round(20, [dict(work_id=WORK, step_id=P, run_id=RUN)])
    doc = json.loads(publish_total(fold_total([(WORK, _chain(log.events) + b'invalid\n')], [(OBS, _chain([observer]))], 20)))
    step = doc['works'][0]['steps'][0]
    assert step['reason'] == 'log_invalid'
    assert 'last_seen' not in step
    assert doc['works'][0]['unrecorded_runs'] == 1
    assert doc['internal_errors'] == 0
