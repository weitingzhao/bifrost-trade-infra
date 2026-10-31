"""Offline stage integration. Real Git snapshots; injected executables only at OS edges."""
import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
S = runpy.run_path(str(HERE / 'test_doc_policy.py'))
put, commit, git = S['put'], S['commit_fixture'], S['command']
spec = importlib.util.spec_from_file_location('ci_coverage', HERE / 'coverage_infra.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


@pytest.fixture
def ci_workspace(tmp_path):
    cand, base = tmp_path / 'cand', tmp_path / 'base'
    infra, platform = cand / 'bifrost-trade-infra', cand / 'bifrost-platform'
    for p in (infra, platform, base):
        p.mkdir(parents=True)
    for p in (infra, platform):
        git(p, 'init', '-q')
    put(platform, 'README', 'pinned platform\n')
    psha = commit(platform)
    for name in ('doc_policy.py', 'doc_consumers.py', 'coverage_infra.py', 'ci-infra.sh'):
        put(infra, 'scripts/landing/' + name, (HERE / name).read_bytes())
    for name in ('scan.sh', 'baselines.env'):
        put(infra, 'agent-config/scripts/code-health/' + name,
            (ROOT / 'agent-config/scripts/code-health' / name).read_bytes())
    put(infra, C.P['RULES'], 'repos:\n- repo: bifrost-trade-infra\n  allow:\n  - agent-config/work/multi-agent/REPORT-*.md\n')
    put(infra, S['DOC'], 'Old\n')
    pre_registry = commit(infra)
    found = S['D']['discover'](infra, pre_registry)
    rows = [dict(file=name, **{'class': 'constraint'}, hits=S['D']['fingerprint'](hits),
                 why='Fixture', effect='test', checked_by='fixture review #1') for name, hits in found.items()]
    put(infra, C.P['REGISTRY'], yaml.safe_dump(rows))
    m0 = commit(infra)
    git(infra, 'worktree', 'add', '--detach', str(base / 'bifrost-trade-infra'), m0)
    put(infra, S['DOC'], 'New\n')
    rev = commit(infra)
    return SimpleNamespace(cand=cand, base=base, revision=rev, base_sha=m0, platform_revision=psha,
                           purpose='landing', generation='1', results_dir=None), infra, platform


def test_workspace_identity_and_dirty(ci_workspace):
    args, infra, platform = ci_workspace
    assert C.check_workspace(args) == (infra, platform)
    (infra / S['DOC']).write_text('not committed\n')
    with pytest.raises(C.Error, match='checkout_dirty'):
        C.check_workspace(args)


def test_baseline_entry_export_and_scope_stops_all(ci_workspace):
    args, infra, _platform = ci_workspace
    # Candidate program is poisoned. The baseline copy must reject the scope
    # without ever executing the poisoned checker or any subsequent stage.
    put(infra, 'scripts/landing/doc_policy.py', 'raise SystemExit("POISON_EXECUTED")\n')
    rev = commit(infra)
    args.base_sha = args.revision
    args.revision = rev
    git(args.base / 'bifrost-trade-infra', 'checkout', '--detach', args.base_sha)
    result = subprocess.run(['bash', str(HERE / 'ci-infra.sh'), '--stage', 'scope', '--cand', str(args.cand),
                             '--base', str(args.base), '--base-sha', args.base_sha, '--revision', rev,
                             '--platform-revision', args.platform_revision], capture_output=True, check=False, text=True)
    assert result.returncode == 1
    assert 'hard_floor' in result.stderr and 'POISON_EXECUTED' not in result.stderr


def test_all_stops_before_consumers(ci_workspace, monkeypatch):
    args, infra, _platform = ci_workspace
    put(infra, 'scripts/x.py', 'x=1\n')
    args.revision = commit(infra)
    args.base_sha = git(infra, 'rev-parse', 'HEAD^')
    git(args.base / 'bifrost-trade-infra', 'checkout', '--detach', args.base_sha)
    seen = []
    real_stage = C.stage
    def record_stage(a, name, i, p):
        seen.append(name)
        if name != 'tools':
            real_stage(a, name, i, p)
    monkeypatch.setattr(C, 'stage', record_stage)
    monkeypatch.setattr(sys, 'argv', ['ci', '--stage', 'all', '--cand', str(args.cand), '--base', str(args.base),
                                    '--revision', args.revision, '--base-sha', args.base_sha,
                                    '--platform-revision', args.platform_revision])
    assert C.main() == 1
    assert seen == ['tools', 'scope']


def test_each_policy_stage_rejects_missing_baseline_input(ci_workspace):
    args, infra, platform = ci_workspace
    C.stage(args, 'scope', infra, platform)
    C.stage(args, 'doc-policy', infra, platform)
    C.stage(args, 'consumers', infra, platform)
    git(infra, 'rm', C.P['REGISTRY'])
    args.base_sha = commit(infra)
    put(infra, S['DOC'], 'Third\n')
    args.revision = commit(infra)
    with pytest.raises(C.Error, match='command_failed'):
        C.stage(args, 'consumers', infra, platform)  # registry absent at M0
    command = ['bash', str(HERE / 'ci-infra.sh'), '--stage', 'scope', '--cand', str(args.cand),
               '--base', str(args.base), '--revision', args.revision, '--base-sha', 'bad',
               '--platform-revision', args.platform_revision]
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0


def test_health_real_500_to_501(ci_workspace):
    args, infra, _platform = ci_workspace
    put(infra, 'agent-config/work/multi-agent/REPORT-big.md', 'line\n' * 500)
    args.revision = commit(infra)
    C.code_health(args, infra)
    put(infra, 'agent-config/work/multi-agent/REPORT-big.md', 'line\n' * 501)
    args.revision = commit(infra)
    with pytest.raises(C.Error, match='code_health_regressed'):
        C.code_health(args, infra)


def test_health_fails_unreadable_or_partial(tmp_path):
    path = tmp_path / 'health.json'
    with pytest.raises(OSError):
        C.metric_values(path)
    for data in ({}, {'not_measured': 'bifrost-trade-infra', 'metrics': []}, {'metrics': []}):
        path.write_text(json.dumps(data))
        with pytest.raises(C.Error):
            C.metric_values(path)


def test_tools_exact_version_and_missing(tmp_path, monkeypatch):
    answers = ['Python 3.12.16\n', 'git version 2.39.5\n', '5.2.15(1)-release',
               '{"clientVersion":{"gitVersion":"v1.31.4"}}', 'go version go1.25.3 linux/amd64\n']
    expected = tmp_path / 'expected'
    expected.write_bytes((ROOT / 'docker/ci-infra/TOOLS.expected').read_bytes())
    def setup():
        it = iter(answers)
        monkeypatch.setattr(C, 'run', lambda *a, **k: next(it))
    setup()
    C.tools_check(expected)
    expected.write_text('wrong\n')
    setup()
    with pytest.raises(C.Error, match='tools_version_mismatch'):
        C.tools_check(expected)
    expected.unlink()
    setup()
    with pytest.raises(OSError):
        C.tools_check(expected)


def test_quick_generator_only_and_failures(ci_workspace, monkeypatch, tmp_path):
    args, infra, platform = ci_workspace
    with pytest.raises(C.Error, match='platform_infracheck_missing'):
        C.quick(args, infra, platform)
    (platform / 'api/cmd/infracheck').mkdir(parents=True)
    marker = tmp_path / 'generated-was-run'
    calls = []
    real_run = C.run
    def generator(argv, **kwargs):
        if argv[0] == 'go':
            calls.append(argv)
            assert kwargs['env']['GOPROXY'] == 'off'
            return 'exit 0' if '--print-setup' in argv else f'printf ok > "{marker}"'
        return real_run(argv, **kwargs)
    monkeypatch.setattr(C, 'run', generator)
    C.quick(args, infra, platform)
    assert marker.read_text() == 'ok'
    assert calls[0][-3:] == ['--print-setup', '--wheelhouse', '/opt/wheels']
    assert calls[1][-1] == '--print-check'
    monkeypatch.setattr(C, 'run', lambda *a, **kw: '')
    with pytest.raises(C.Error, match='quick_setup_empty'):
        C.quick(args, infra, platform)


def test_statics_success_missing_and_failure(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    names = ('check_admission_guards.py', 'check_agent_access.py', 'check_platform_maintenance.py',
             'check_alert_routing.py', 'check-release-chain.py')
    for n in names:
        (scripts / n).write_text('import sys\nassert "--live" not in sys.argv\n')
    hp = tmp_path / 'agent-config/scripts/check_hardcoded_paths.py'
    hp.parent.mkdir(parents=True)
    hp.write_text('import sys\nassert sys.argv[1:] == ["--ref", "HEAD", "--new-only"]\n')
    C.statics(tmp_path)
    (scripts / names[0]).write_text('raise SystemExit(7)\n')
    with pytest.raises(C.Error, match='command_failed'):
        C.statics(tmp_path)
    (scripts / names[0]).unlink()
    with pytest.raises(C.Error, match='command_failed'):
        C.statics(tmp_path)


def test_kustomize_only_local_render(tmp_path, monkeypatch):
    with pytest.raises(C.Error, match='overlays_missing'):
        C.kustomize(tmp_path)
    overlay = tmp_path / 'k8s/overlays/test'
    overlay.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(C, 'run', lambda cmd, **kw: calls.append(cmd))
    C.kustomize(tmp_path)
    assert calls == [['kubectl', 'kustomize', overlay]]
    monkeypatch.setattr(C, 'run', lambda *a, **kw: (_ for _ in ()).throw(C.Error('render_failed')))
    with pytest.raises(C.Error, match='render_failed'):
        C.kustomize(tmp_path)


def test_parity_static_pass_reject_and_no_host(tmp_path):
    # Real entry point, no .git, refs, hooks or installed Codex in this fixture.
    (tmp_path / '.cursor/rules').mkdir(parents=True)
    (tmp_path / '.cursor/skills').mkdir()
    (tmp_path / '.claude/skills').mkdir(parents=True)
    (tmp_path / 'bifrost-platform/config').mkdir(parents=True)
    (tmp_path / 'CLAUDE.md').write_text('parity-ids: sample-v1\nBLOCKED\n')
    (tmp_path / 'AGENT_FACTS.md').write_text('facts\n')
    (tmp_path / '.cursor/rules/sample.mdc').write_text('parity-id: sample-v1\n')
    (tmp_path / '.cursor/rules/trade-execution-freeze.mdc').write_text('BLOCKED\n')
    (tmp_path / 'bifrost-platform/config/ops-context.yaml').write_text('- id: D10\n  status: BLOCKED\n')
    script = ROOT / 'agent-config/scripts/check-agent-config-parity.sh'
    cmd = ['bash', str(script), '--static-tree', str(tmp_path)]
    assert subprocess.run(cmd, capture_output=True, check=False).returncode == 0
    (tmp_path / '.cursor/rules/sample.mdc').write_text('parity-id: sample-v2\n')
    assert subprocess.run(cmd, capture_output=True, check=False).returncode == 1
    (tmp_path / 'CLAUDE.md').unlink()
    assert subprocess.run(cmd, capture_output=True, check=False).returncode == 1


def test_no_base_push_explicit_skip(ci_workspace, capsys):
    args, infra, platform = ci_workspace
    args.base_sha, args.purpose = '', 'push'
    C.stage(args, 'doc-policy', infra, platform)
    assert 'skipped(no_base)' in capsys.readouterr().out
    with pytest.raises(C.Error, match='code_health_no_base'):
        C.code_health(args, infra)
    args.purpose = 'landing'
    with pytest.raises(C.Error, match='base_missing'):
        C.check_workspace(args)
