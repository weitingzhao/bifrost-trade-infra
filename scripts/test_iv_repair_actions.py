import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('iv_actions', Path(__file__).with_name('build-iv-repair-actions.py'))
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


def test_embedded_csv_keeps_exact_reviewed_bytes_including_crlf(tmp_path):
    content = b'symbol,session,expiry\r\nSPY,2026-08-10,2026-12-18\r\n'
    (tmp_path/'scope.csv').write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    assert actions.manifest(tmp_path,'scope',digest).encode() == content
    with pytest.raises(ValueError, match='changed'):
        actions.manifest(tmp_path,'scope','0'*64)


def test_source_capsule_keeps_zero_and_loads_in_named_module():
    import sys
    try:
        exec(actions.capsule([('math.iv_repair_test','VALUE = 0')]))
        assert sys.modules['math.iv_repair_test'].VALUE == 0
    finally:
        sys.modules.pop('math.iv_repair_test',None)
