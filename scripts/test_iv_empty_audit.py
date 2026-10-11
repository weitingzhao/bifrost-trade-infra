import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('empty_audit',Path(__file__).with_name('audit-iv-empty-responses.py'))
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def response(http=200, **extra):
    return {'http':http,'status':'OK','truncated':False,'contracts':[],**extra}


def test_absence_needs_two_reference_evidences_and_empty_bar():
    assert audit.classify(response(404),response(),'x',response(days=[]),'d')=='not_listed_as_of_vendor'
    assert audit.classify(response(),response(),'x',response(days=[]),'d')=='reference_conflict'
    assert audit.classify(response(404),response(),'x',response(days=['d']),'d')=='reference_bar_conflict'
    assert audit.classify(response(404),response(),'x',response(days=[],truncated=True),'d')=='fetch_problem'


def test_listed_empty_is_not_claimed_to_mean_zero_trades():
    assert audit.classify(response(),response(contracts=[{'ticker':'x'}]),'x',response(days=[]),'d')=='listed_no_eligible_aggregate'


def test_permissions_errors_and_pagination_are_not_no_trade():
    assert audit.classify(response(),response(),'x',response(403,days=[]),'d')=='permission_restricted'
    assert audit.classify(response(404),response(truncated=True),'x',response(days=[]),'d')=='reference_unprobed'
    assert audit.classify(response(),response(contracts=[{'ticker':'x'}]),'x',response(500,days=[]),'d')=='fetch_problem'
    assert audit.classify(response(404),response(),'x',response(500,days=[]),'d')=='fetch_problem'


def test_retrievable_exact_session_is_reported_for_confirmation():
    assert audit.classify(response(),response(contracts=[{'ticker':'x'}]),'x',response(days=['d']),'d')=='retrievable_now'


def test_scope_digest_and_exact_cardinality(tmp_path):
    import csv
    import hashlib

    import pytest

    path=tmp_path/'scope.csv'
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=['symbol','option_ticker','session','expiry','status']);w.writeheader()
        for n in range(97):
            w.writerow({'symbol':'SPY','option_ticker':f'O:SPY261113C{700000+n:08}',
                        'session':'2026-08-10','expiry':'2026-11-13','status':'no_bar_unknown'})
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(audit.load_scope(path,digest))==97
    with pytest.raises(ValueError,match='scope changed'):
        audit.load_scope(path,'0'*64)
    content=path.read_text().replace('O:SPY261113C','O:NVDA261113C',1);path.write_text(content)
    with pytest.raises(ValueError,match='ticker disagrees'):
        audit.load_scope(path,hashlib.sha256(path.read_bytes()).hexdigest())
