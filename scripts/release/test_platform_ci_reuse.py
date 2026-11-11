"""Reuse selection fixtures and the deployed producer contract."""
import copy
import runpy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(Path(__file__).with_name('platform_ci_reuse.py')))
IDENTITIES = {'platform-tree': 'tree', 'ui-commit': 'ui', 'infra-commit': 'infra'}
CURRENT = {'metadata': {'creationTimestamp': '2026-11-11T12:00:00Z'}}


def candidate(name='original', time='2026-11-11T11:00:00Z'):
    return {'metadata': {'name': name, 'creationTimestamp': time},
            'spec': {'pipelineRef': {'name': 'bifrost-ci-platform'}, 'params': [
                {'name': 'repo-url', 'value': 'repo'}, {'name': 'base', 'value': 'base'}]},
            'status': {'conditions': [{'type': 'Succeeded', 'status': 'True'}],
                       'results': [{'name': k, 'value': v} for k, v in
                                   {**IDENTITIES, **dict.fromkeys(M['FIELDS'], ''), 'api-scope': 'full'}.items()]}}


def choose(runs):
    return M['select'](runs, CURRENT, IDENTITIES, 'repo', 'base')


def test_newest_original():
    a, b = candidate(), candidate('newest', '2026-11-11T11:30:00Z')
    assert choose([a, b]) == b


@pytest.mark.parametrize('case', ['platform-tree', 'ui-commit', 'infra-commit', 'tested-by',
                                 'newer', 'same-time', 'failed', 'repo', 'incremental-base'])
def test_miss(case):
    run = candidate()
    results = run['status']['results']
    if case in IDENTITIES:
        next(r for r in results if r['name'] == case)['value'] = 'other'
    elif case == 'tested-by':
        results.append({'name': 'tested-by', 'value': ''})
    elif case in ('newer', 'same-time'):
        run['metadata']['creationTimestamp'] = '2026-11-11T13:00:00Z' if case == 'newer' else CURRENT['metadata']['creationTimestamp']
    elif case == 'failed':
        run['status']['conditions'][0]['status'] = 'False'
    elif case == 'repo':
        run['spec']['params'][0]['value'] = 'other'
    else:
        next(r for r in results if r['name'] == 'api-scope')['value'] = 'incremental'
        run['spec']['params'][1]['value'] = 'other'
    assert choose([run]) is None


def test_incremental_matching_base():
    run = candidate()
    next(r for r in run['status']['results'] if r['name'] == 'api-scope')['value'] = 'incremental'
    assert choose([run]) == run


def test_listing_error_is_miss():
    def read(path):
        if path.startswith('/'):
            return copy.deepcopy(CURRENT)
        raise PermissionError('forbidden')
    assert M['lookup'](read, 'current', IDENTITIES, 'repo', 'base') is None


def test_manifest_contract():
    directory = ROOT / 'k8s/cicd/tekton'
    pipeline = yaml.safe_load((directory / 'pipeline-ci-platform.yaml').read_text())['spec']
    tasks = {t['name']: t for t in pipeline['tasks']}
    for name in ('test-api', 'test-api-store', 'test-console', 'check-spine', 'check-ops-context', 'code-health'):
        assert 'when' not in tasks[name]
        assert {'name': 'reuse', 'value': '$(tasks.reuse.results.reuse)'} in tasks[name]['params']
    results = {r['name']: r['value'] for r in pipeline['results']}
    assert results['tested-by'] == '$(tasks.reuse.results.tested-by)'
    for name in M['FIELDS']:
        assert results[name] == '$(tasks.test-api.results.' + name + ')'
    task = yaml.safe_load((directory / 'task-ci-platform-reuse.yaml').read_text())['spec']
    assert task['steps'][0]['script'] == '#!/usr/bin/env python3\n' + (ROOT / 'scripts/release/platform_ci_reuse.py').read_text()
    docs = list(yaml.safe_load_all((directory / 'trigger-trade-ci.yaml').read_text()))
    template = next(d for d in docs if d and d['metadata']['name'] == 'bifrost-ci-platform-template')
    assert template['spec']['resourcetemplates'][0]['spec']['taskRunSpecs'] == [
        {'pipelineTaskName': 'reuse', 'serviceAccountName': 'tekton-platform-ci-reuse'}]
    rbac = list(yaml.safe_load_all((directory / 'rbac-platform-ci-reuse.yaml').read_text()))
    assert all(d['metadata']['namespace'] == 'cicd' for d in rbac)
    assert rbac[1]['rules'] == [{'apiGroups': ['tekton.dev'], 'resources': ['pipelineruns'], 'verbs': ['get', 'list']}]


def test_infra_allow_transport():
    directory = ROOT / 'k8s/cicd/tekton'
    pipeline = yaml.safe_load((directory / 'pipeline-ci-infra.yaml').read_text())['spec']
    param = next(p for p in pipeline['params'] if p['name'] == 'landing-allow-json')
    assert param == {'name': 'landing-allow-json', 'type': 'string', 'default': ''}
    check = next(t for t in pipeline['tasks'] if t['name'] == 'check')
    assert {'name': 'landing-allow-json', 'value': '$(params.landing-allow-json)'} in check['params']
    task = yaml.safe_load((directory / 'task-ci-infra-check.yaml').read_text())['spec']
    assert param in task['params']
    step = next(s for s in task['steps'] if s['name'] == 'doc-policy')
    assert {'name': 'LANDING_ALLOW_JSON', 'value': '$(params.landing-allow-json)'} in step['env']


def test_window_has_one_decision():
    task = yaml.safe_load((ROOT / 'k8s/cicd/tekton/task-release-window.yaml').read_text())
    assert [s['name'] for s in task['spec']['steps']] == ['check']


def test_reused_steps_return_before_work(tmp_path):
    import os
    import subprocess
    directory = ROOT / 'k8s/cicd/tekton'
    shared, results = tmp_path / 'ci-api-results', tmp_path / 'results'
    shared.mkdir()
    results.mkdir()
    for field in M['FIELDS']:
        (shared / field).write_text(field)
    pipeline = yaml.safe_load((directory / 'pipeline-ci-platform.yaml').read_text())['spec']
    for task in pipeline['tasks']:
        if task['name'] not in ('test-api', 'test-api-store', 'test-console', 'check-spine', 'check-ops-context', 'code-health'):
            continue
        spec = task.get('taskSpec')
        if spec is None:
            filename = 'task-ci-platform-test-api.yaml' if task['name'].startswith('test-api') else 'task-code-health.yaml'
            spec = yaml.safe_load((directory / filename).read_text())['spec']
        for step in spec['steps']:
            script = step['script'].replace('$(workspaces.source.path)', str(tmp_path)).replace('/tekton/results/', str(results) + '/')
            result = subprocess.run(['bash', '-c', script], cwd=tmp_path,
                                    env={**os.environ, 'REUSE': 'yes'}, capture_output=True, text=True)
            assert result.returncode == 0, (task['name'], result.stderr)
            assert not result.stdout
    assert {p.name: p.read_text() for p in results.iterdir()} == {field: field for field in M['FIELDS']}


def test_admission_scopes_reader_to_reuse_task():
    docs = list(yaml.safe_load_all((ROOT / 'k8s/platform-rbac/40-admission.yaml').read_text()))
    policy = next(d for d in docs if d and d['metadata']['name'] == 'bifrost-platform-pipelinerun')
    rules = [' '.join(v['expression'].split()) for v in policy['spec']['validations']]
    assert any("s.serviceAccountName == 'tekton-platform-ci-reuse' && has(s.pipelineTaskName) && object.spec.pipelineRef.name == 'bifrost-ci-platform' && s.pipelineTaskName == 'reuse'" in r for r in rules)
    assert not any("object.spec.taskRunTemplate.serviceAccountName in ['default', 'tekton-deliver', 'bifrost-applier', 'tekton-platform-ci-reuse']" in r for r in rules)


@pytest.mark.parametrize('hit', [False, True])
def test_result_emission(tmp_path, monkeypatch, hit):
    results = tmp_path / 'results'
    results.mkdir()
    shared = tmp_path / 'shared'
    globals_ = M['main'].__globals__
    real_path = Path
    monkeypatch.setitem(globals_, 'Path', lambda p: results if p == '/tekton/results' else real_path(p))
    monkeypatch.setitem(globals_, 'lookup', lambda *args: candidate() if hit else None)
    for key, value in {'RUN': 'current', 'TREE': 'tree', 'UI': 'ui', 'INFRA': 'infra',
                       'REPO': 'repo', 'BASE': 'base', 'RESULTS_DIR': str(shared)}.items():
        monkeypatch.setenv(key, value)
    M['main']()
    assert (results / 'reuse').read_text() == ('yes' if hit else 'no')
    assert (results / 'tested-by').exists() == hit
    if hit:
        assert (results / 'tested-by').read_text() == 'original'
        expected = M['values'](candidate()['status']['results'])
        assert {p.name: p.read_text() for p in shared.iterdir()} == {k: expected[k] for k in M['FIELDS']}
    else:
        assert not shared.exists()
