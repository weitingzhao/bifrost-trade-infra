"""Warn on the current quick execution; historical timing is not an input."""
import runpy
from pathlib import Path

T = runpy.run_path(str(Path(__file__).with_name('test_ci_infra_stages.py')))
ci_workspace = T['ci_workspace']
C = T['C']


def measure_quick(args, infra, platform, monkeypatch, seconds):
    (platform / 'api/cmd/infracheck').mkdir(parents=True, exist_ok=True)
    clock = iter((0.0, seconds))
    monkeypatch.setattr(C.time, 'monotonic', lambda: next(clock))
    real_run = C.run
    def generated_command(argv, **kwargs):
        if argv[0] == 'go':
            return 'exit 0'
        return real_run(argv, **kwargs)
    monkeypatch.setattr(C, 'run', generated_command)
    C.quick(args, infra, platform)


def test_last_ci_budget(ci_workspace, monkeypatch, capsys):
    # Keep the existing test entry for quick-list compatibility, while dropping
    # the unsupported historical artifact dependency (review 777 N-01).
    args, infra, platform = ci_workspace
    measure_quick(args, infra, platform, monkeypatch, 120.0)
    output = capsys.readouterr().out
    assert 'quick_seconds=120.000' in output
    assert 'quick_budget_exceeded' not in output


def test_budget_warning_and_unreadable(ci_workspace, monkeypatch, capsys, tmp_path):
    args, infra, platform = ci_workspace
    args.results_dir = tmp_path
    measure_quick(args, infra, platform, monkeypatch, 121.0)
    assert 'WARN quick_budget_exceeded seconds=121.0' in capsys.readouterr().out
    assert not (tmp_path / 'quick-timing.json').exists()
