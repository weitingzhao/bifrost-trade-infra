"""The current run's budget must not depend on an unprovided previous artifact."""
import os
import runpy
import subprocess
import sys
from pathlib import Path

T = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_stages.py')))
ci_workspace = T['ci_workspace']


def test_n01_no_unwired_history_dependency(ci_workspace):
    _args, repo, _platform = ci_workspace
    T['put'](repo, 'previous-quick.json', '{corrupt stale artifact}\n')
    T['commit'](repo)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', str(Path(__file__).with_name('test_quick_budget.py'))],
                            env=dict(os.environ, CI_INFRA_QUICK_TIMING=str(repo / 'previous-quick.json')),
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
