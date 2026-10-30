"""Consume a previous CI timing artifact; exceeding two minutes warns only."""
import json
import math
import os
import warnings
from pathlib import Path

import pytest


def check_budget(path):
    seconds = json.loads(Path(path).read_text())['seconds']
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('invalid quick timing')
    if seconds > 120:
        warnings.warn(f'quick_budget_exceeded {seconds}s > 120s', stacklevel=2)
    return seconds


def test_last_ci_budget():
    path = os.environ.get('CI_INFRA_QUICK_TIMING')
    if not path:
        warnings.warn('quick_budget_unmeasured: no previous CI timing artifact', stacklevel=1)
        return
    check_budget(path)  # An explicitly supplied unreadable artifact is a failure.


def test_budget_warning_and_unreadable(tmp_path):
    path = tmp_path / 'quick.json'
    path.write_text('{"seconds": 120}')
    assert check_budget(path) == 120
    path.write_text('{"seconds": 121}')
    with pytest.warns(UserWarning, match='quick_budget_exceeded'):
        assert check_budget(path) == 121
    path.unlink()
    with pytest.raises(OSError):
        check_budget(path)
