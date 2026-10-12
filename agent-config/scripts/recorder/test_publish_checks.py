"""The publisher self-check and caught errors preserve typed classification."""
import json
import pytest
import publish
from read import PROBES, fold_total


@pytest.mark.parametrize('reason', ['shape', 'too_large'])
def test_publish_output_checks_classify_defects_without_catching(monkeypatch, reason):
    folded = fold_total([], [], 42)
    malformed = folded.document()
    if reason == 'shape':
        malformed['owner_now'] = 0
    else:
        malformed['padding'] = 'x' * (publish.PUBLISH_TARGET_BYTES + 1)
    monkeypatch.setattr(publish, 'publish_view', lambda *args: malformed)
    doc = json.loads(publish.publish_total(folded))
    assert doc['recorder_failed'] == {'stage': 'publish', 'reason': reason}
    assert doc['at'] == 42 and doc['internal_errors'] == 0
    assert doc['fold_complete'] is False and doc['ball']['holder'] == 'unknown'


def test_publish_caught_error_preserves_registry_time():
    def fail():
        raise RuntimeError('not published')
    folded = fold_total([], [], 42)
    PROBES['publish'] = fail
    try:
        doc = json.loads(publish.publish_total(folded))
    finally:
        PROBES['publish'] = None
    assert doc['at'] == 42 and doc['internal_errors'] == 1
    assert doc['recorder_failed'] == {'stage': 'publish', 'reason': 'caught', 'error_class': 'RuntimeError'}
