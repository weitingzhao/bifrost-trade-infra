"""Round object shapes are field defects, never swallowed by guards."""
import copy
import json
import pytest
from harness import P, RUN, WORK, _chain
from publish import publish_total
from read import fold_total
from test_rows import OBS, _round

_ITEM = dict(work_id=WORK, step_id=P, run_id=RUN)
_KEY = f'step:{WORK}/{P}'
_CASES = [
    ('unrecorded', None, 'bad_type'), ('unrecorded', {}, 'bad_type'),
    ('unrecorded', [None], 'bad_type'), ('unrecorded', [{}], 'missing_field'),
    ('unrecorded', [dict(_ITEM, extra=1)], 'unknown_field'),
    ('confirmed', [None], 'bad_type'), ('confirmed', [{}], 'bad_type'),
    ('confirmed', ['bad'], 'bad_value'), ('confirmed', ['x' * 201], 'bad_value'),
    ('failed', [None], 'bad_type'), ('failed', [{}], 'missing_field'),
    ('failed', [dict(key=_KEY)], 'missing_field'), ('failed', [dict(error='timeout')], 'missing_field'),
    ('failed', [dict(key=_KEY, error='timeout', extra=1)], 'unknown_field'),
    ('failed', [dict(key=None, error='timeout')], 'bad_type'),
    ('failed', [dict(key=_KEY, error=None)], 'bad_type'),
    ('failed', [dict(key='bad', error='timeout')], 'bad_value'),
    ('failed', [dict(key=_KEY, error='not-a-code')], 'bad_error'),
]
for _field in ('work_id', 'step_id', 'run_id'):
    _missing = dict(_ITEM)
    del _missing[_field]
    _CASES.append(('unrecorded', [_missing], 'missing_field'))
    for _value, _reason in ((None, 'bad_type'), (1, 'bad_type'), ('-', 'bad_value')):
        _CASES.append(('unrecorded', [dict(_ITEM, **{_field: _value})], _reason))


@pytest.mark.parametrize('field,value,reason', _CASES)
def test_round_fields_expected_defect_at_real_boundary(field, value, reason):
    event = _round(20, [])
    event[field] = copy.deepcopy(value)
    folded = fold_total([], [(OBS, _chain([event]))], 20)
    local = folded.document()
    assert 'recorder_failed' not in local and local['internal_errors'] == 0
    assert local['observer']['defects'] == [{'file': OBS, 'seq': 1, 'reason': reason}]
    assert 'last_round_at' not in local['observer']
    doc = json.loads(publish_total(folded))
    assert doc['observer'] == {'defects_count': 1}
    assert doc['internal_errors'] == 0
    assert doc['ball']['holder'] == 'nobody'
