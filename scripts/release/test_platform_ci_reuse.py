"""Reuse selection fixtures and the deployed producer contract."""
import copy
import runpy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
M = runpy.run_path(str(Path(__file__).with_name('platform_ci_reuse.py')))
IDENTITIES = {'platform-tree': 'tree', 'ui-commit': 'ui', 'infra-commit': 'infra'}
CURRENT = {'metadata': {'creationTimestamp': '2026-11-11T12:00:00Z', 'labels': {'bifrost.io/trigger': 'gitea-webhook'}}}


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
                                 'newer', 'same-time', 'failed', 'repo'])
def test_miss(case):
    run = candidate()
    results = run['status']['results']
    if case in IDENTITIES:
        next(r for r in results if r['name'] == case)['value'] = 'other'
    elif case == 'tested-by':
        results.append({'name': 'tested-by', 'value': 'older'})
    elif case in ('newer', 'same-time'):
        run['metadata']['creationTimestamp'] = '2026-11-11T13:00:00Z' if case == 'newer' else CURRENT['metadata']['creationTimestamp']
    elif case == 'failed':
        run['status']['conditions'][0]['status'] = 'False'
    else:
        run['spec']['params'][0]['value'] = 'other'
    assert choose([run]) is None


def test_empty_tested_by_is_a_fresh_original():
    # TD-533: every run writes tested-by; an empty one tested fresh and may be reused.
    run = candidate()
    run['status']['results'].append({'name': 'tested-by', 'value': ''})
    assert choose([run]) == run


# 2026-11-21, CI line under law 90: the push to main after an incremental landing stands on
# the landing's run (same tree, ui, infra). On 2026-11-20 the 58 full runs of those pushes
# found 0 failures that the landing run had not. Replaces the 2026-11-16 rule that an
# increment is never reused; the full pass PROD needs comes from the daily full CI.
FULL_CURRENT = {'metadata': CURRENT['metadata'], 'spec': {'params': [{'name': 'api-scope-request', 'value': 'full'}]}}


def incremental(base_commit='base'):
    run = candidate()
    run['spec']['params'][1]['value'] = ''
    results = run['status']['results']
    next(r for r in results if r['name'] == 'api-scope')['value'] = 'incremental'
    results.append({'name': 'base-commit', 'value': base_commit})
    return run


def test_the_push_to_main_stands_on_the_landing_runs_increment():
    for base_commit in ('base', 'other', 'none'):
        run = incremental(base_commit)
        assert M['select']([run], CURRENT, IDENTITIES, 'repo', '') == run


def test_the_daily_full_run_never_reuses_an_increment():
    # The daily full CI asks for the whole suite: it is the full pass PROD is released on.
    assert M['select']([incremental()], FULL_CURRENT, IDENTITIES, 'repo', '') is None
    # Positive control: the same full-run request still reuses a whole-suite original.
    whole = candidate()
    assert M['select']([whole], FULL_CURRENT, IDENTITIES, 'repo', '') == whole


def test_a_run_started_by_hand_never_reuses_an_increment():
    # 2026-11-21: a manual run of ac07e84b (bifrost.io/trigger=platform-api) reused the
    # landing's increment in 22 s; started by hand, a run is a request for the full pass.
    by_hand = {'metadata': {'creationTimestamp': CURRENT['metadata']['creationTimestamp'],
                            'labels': {'bifrost.io/trigger': 'platform-api'}}}
    assert M['select']([incremental()], by_hand, IDENTITIES, 'repo', '') is None
    no_label = {'metadata': {'creationTimestamp': CURRENT['metadata']['creationTimestamp']}}
    assert M['select']([incremental()], no_label, IDENTITIES, 'repo', '') is None
    # Positive control: by hand, a whole-suite original is still reused.
    whole = candidate()
    assert M['select']([whole], by_hand, IDENTITIES, 'repo', '') == whole


def test_an_increment_of_another_tree_is_not_reused():
    run = incremental()
    next(r for r in run['status']['results'] if r['name'] == 'platform-tree')['value'] = 'other'
    assert M['select']([run], CURRENT, IDENTITIES, 'repo', '') is None


def test_a_reused_run_hands_over_the_base_it_named(tmp_path, monkeypatch):
    results = tmp_path / 'results'
    results.mkdir()
    shared = tmp_path / 'shared'
    globals_ = M['main'].__globals__
    real_path = Path
    monkeypatch.setitem(globals_, 'Path', lambda p: results if p == '/tekton/results' else real_path(p))
    monkeypatch.setitem(globals_, 'lookup', lambda *args: incremental('base'))
    for key, value in {'RUN': 'current', 'TREE': 'tree', 'UI': 'ui', 'INFRA': 'infra',
                       'REPO': 'repo', 'BASE': 'base', 'RESULTS_DIR': str(shared)}.items():
        monkeypatch.setenv(key, value)
    M['main']()
    assert (shared / 'base-commit').read_text() == 'base'


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
    # The infra copies of platform config/ are judged in ci-infra only (statics stage).
    assert 'check-ops-context' not in tasks
    for name in ('test-api', 'test-api-store', 'test-console', 'check-spine', 'code-health'):
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


def test_infra_ci_takes_no_allow_list():
    # TD-537: admission refuses a landing allow list on an infra CI run, so the
    # Pipeline and its check Task declare no parameter that would carry one.
    directory = ROOT / 'k8s/cicd/tekton'
    pipeline = yaml.safe_load((directory / 'pipeline-ci-infra.yaml').read_text())['spec']
    task = yaml.safe_load((directory / 'task-ci-infra-check.yaml').read_text())['spec']
    names = [p['name'] for p in pipeline['params']] + [p['name'] for p in task['params']]
    names += [p['name'] for t in pipeline['tasks'] for p in t.get('params', [])]
    names += [e['name'] for s in task['steps'] for e in s.get('env', [])]
    assert 'landing-allow-json' not in names and 'LANDING_ALLOW_JSON' not in names


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
        if task['name'] not in ('test-api', 'test-api-store', 'test-console', 'check-spine', 'code-health'):
            continue
        spec = task.get('taskSpec')
        if spec is None:
            filename = 'task-ci-platform-test-api.yaml' if task['name'].startswith('test-api') else 'task-code-health.yaml'
            spec = yaml.safe_load((directory / filename).read_text())['spec']
        for step in spec['steps']:
            script = step['script'].replace('$(workspaces.source.path)', str(tmp_path)).replace('/tekton/results/', str(results) + '/')
            result = subprocess.run(['bash', '-c', script], cwd=tmp_path,
                                    env={**os.environ, 'REUSE': 'yes', 'BASE_COMMIT_RESULT': str(results / 'base-commit')},
                                    capture_output=True, text=True)
            assert result.returncode == 0, (task['name'], result.stderr)
            assert not result.stdout
    # base-commit: the task writes the word none when the reuse task handed nothing over (one from before 2026-11-15).
    assert {p.name: p.read_text() for p in results.iterdir()} == {**{field: field for field in M['FIELDS']}, 'base-commit': 'none'}


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
    # TD-533: tested-by is always written (the pipeline result needs it), empty on a miss.
    assert (results / 'tested-by').read_text() == ('original' if hit else '')
    if hit:
        expected = M['values'](candidate()['status']['results'])
        assert {p.name: p.read_text() for p in shared.iterdir()} == {**{k: expected[k] for k in M['FIELDS']}, 'base-commit': 'none'}
    else:
        assert not shared.exists()


def test_a_ready_push_never_reuses_an_increment():
    # TD-587, 2026-11-22: ready/releasepolicy-check-judgment pushed three times after main
    # moved; each run reused ci-platform-55fcp's increment, whose base-commit was the old
    # main, and the landing refused it each time (land-fl8dp, land-l2nzp, land-c87zn).
    ready = {'metadata': {'creationTimestamp': CURRENT['metadata']['creationTimestamp'],
                          'labels': {'bifrost.io/trigger': 'gitea-webhook',
                                     'triggers.tekton.dev/trigger': 'platform-ci-ready'}}}
    assert M['select']([incremental()], ready, IDENTITIES, 'repo', '') is None
    # Positive control: a ready push still reuses a whole-suite original, and the push to
    # main (trigger platform-ci) still stands on the increment.
    whole = candidate()
    assert M['select']([whole], ready, IDENTITIES, 'repo', '') == whole
    to_main = copy.deepcopy(ready)
    to_main['metadata']['labels']['triggers.tekton.dev/trigger'] = 'platform-ci'
    assert M['select']([incremental()], to_main, IDENTITIES, 'repo', '') is not None
