"""Manifest/lock contract; --ready additionally rejects the UNBUILT image."""
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / 'k8s/cicd/tekton'
STAGES = ['tools', 'scope', 'consumers', 'doc-policy', 'quick', 'statics', 'kustomize', 'code-health', 'parity-static']


def read_yaml(name):
    return yaml.safe_load((TEKTON / name).read_text())


def validate_images(root=ROOT, ready=False):
    digest = (root / 'docker/ci-infra/IMAGE_DIGEST').read_text().strip()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('invalid_image_digest')
    if ready and digest == 'sha256:' + '0' * 64:
        raise ValueError('UNBUILT: Owner must build, coordinator must pin digest before installation')
    paths = sorted((root / 'k8s/cicd/tekton').glob('task-ci-infra-*.yaml'))
    if len(paths) != 3:
        raise ValueError('missing_ci_infra_task')
    for path in paths:
        doc = yaml.safe_load(path.read_text())
        for step in doc['spec']['steps']:
            if step['image'] != 'registry.cicd.svc.cluster.local:5000/bifrost-ci-infra-tools@' + digest:
                raise ValueError('image_digest_mismatch ' + path.name)


def test_image_pins():
    validate_images()


def test_ready_rejects_unbuilt(tmp_path):
    import shutil
    shutil.copytree(ROOT / 'docker/ci-infra', tmp_path / 'docker/ci-infra')
    target = tmp_path / 'k8s/cicd/tekton'
    target.mkdir(parents=True)
    for p in TEKTON.glob('task-ci-infra-*.yaml'):
        shutil.copy(p, target / p.name)
    # Seed placeholder and every image are a consistent review artifact only.
    old = (tmp_path / 'docker/ci-infra/IMAGE_DIGEST').read_text().strip()
    zero = 'sha256:' + '0' * 64
    (tmp_path / 'docker/ci-infra/IMAGE_DIGEST').write_text(zero + '\n')
    for p in target.glob('*.yaml'):
        p.write_text(p.read_text().replace(old, zero))
    with pytest.raises(ValueError, match='UNBUILT'):
        validate_images(tmp_path, ready=True)
    actual = 'sha256:' + '1' * 64
    (tmp_path / 'docker/ci-infra/IMAGE_DIGEST').write_text(actual + '\n')
    for p in target.glob('*.yaml'):
        p.write_text(p.read_text().replace(zero, actual))
    validate_images(tmp_path, ready=True)
    p = target / 'task-ci-infra-resolve.yaml'
    p.write_text(p.read_text().replace(actual, 'sha256:' + '2' * 64))
    with pytest.raises(ValueError, match='image_digest_mismatch'):
        validate_images(tmp_path)


def test_pipeline_parameters_results_and_dependencies():
    for name in ('pipeline-ci-infra.yaml', 'pipeline-build-ci-infra-tools.yaml'):
        assert read_yaml(name)['metadata']['annotations']['bifrost.io/run-arch'] == 'amd64'
    p = read_yaml('pipeline-ci-infra.yaml')['spec']
    assert {v['name'] for v in p['params']} == {'revision', 'base', 'platformRevision', 'generation', 'purpose'}
    assert {v['name'] for v in p['results']} == {'infra-commit', 'base-commit', 'platform-commit', 'tools-from', 'doc-policy', 'purpose'}
    tasks = {t['name']: t for t in p['tasks']}
    assert tasks['clone']['runAfter'] == ['resolve']
    assert tasks['check']['runAfter'] == ['clone']
    specs = {}
    for n, task in tasks.items():
        doc = read_yaml('task-ci-infra-' + n + '.yaml')['spec']
        specs[n] = doc
        assert {x['name'] for x in task['params']} == {x['name'] for x in doc['params']}
    for value in re.findall(r'\$\(tasks\.([\w-]+)\.results\.([\w-]+)\)', yaml.safe_dump(p)):
        task, result = value
        assert result in {r['name'] for r in specs[task]['results']}
    check = specs['check']
    assert [s['name'] for s in check['steps']] == STAGES
    for step in check['steps']:
        assert '--stage ' + step['name'] in step['script']
        assert 'base/bifrost-trade-infra/scripts/landing/ci-infra.sh' in step['script']
        assert 'secretKeyRef' not in yaml.safe_dump(step)


def test_trigger_contract_and_no_rbac_expansion():
    docs = list(yaml.safe_load_all((TEKTON / 'trigger-trade-ci.yaml').read_text()))
    byname = {d['metadata']['name']: d for d in docs}
    binding = byname['bifrost-gitea-push-infra']['spec']['params']
    assert {p['name']: p['value'] for p in binding} == {'revision': '$(body.after)', 'base': '$(body.before)', 'purpose': 'push'}
    el = byname['bifrost-ci']['spec']
    infra = next(x for x in el['triggers'] if x['name'] == 'infra-ci')
    f = infra['interceptors'][0]['params'][0]['value']
    for term in ("body.repository.full_name == 'bifrost/bifrost-trade-infra'", "!body.ref.startsWith('refs/heads/land/')",
                 "!body.ref.startsWith('refs/heads/agent/')", "body.after.matches('^[0-9a-f]{40}$')", "body.after != '" + '0'*40):
        assert term in f
    run = byname['bifrost-ci-infra-template']['spec']['resourcetemplates'][0]
    assert run['spec']['pipelineRef']['name'] == 'bifrost-ci-infra'
    assert run['metadata']['labels']['bifrost.io/purpose'] == 'push'
    assert run['metadata']['labels']['bifrost.io/revision'] == '$(tt.params.revision)'
    assert run['spec']['taskRunTemplate']['podTemplate']['nodeSelector']['kubernetes.io/arch'] == 'amd64'
    roles = list(yaml.safe_load_all((TEKTON / 'rbac-trigger.yaml').read_text()))
    role = next(r for r in roles if r['kind'] == 'Role')
    assert role['rules'][0] == {'apiGroups': ['tekton.dev'], 'resources': ['pipelineruns', 'taskruns'], 'verbs': ['create', 'get', 'list']}
    assert len(role['rules']) == 4


def test_locks_and_build_source():
    lock = (ROOT / 'docker/ci-infra/requirements.lock').read_text()
    found = re.findall(r'^(\w+)==([\d.]+) --hash=sha256:([0-9a-f]{64})$', lock, re.MULTILINE)
    assert {n: v for n,v,h in found} == {'pytest': '9.0.2', 'pluggy': '1.6.0', 'iniconfig': '2.1.0',
                                       'packaging': '25.0', 'pygments': '2.19.2', 'pyyaml': '6.0.3'}
    docker = (ROOT / 'docker/ci-infra/Dockerfile').read_text()
    assert re.search(r'^FROM python:3.12-slim-bookworm@sha256:[0-9a-f]{64}$', docker, re.MULTILINE)
    assert '--require-hashes --only-binary=:all:' in docker
    for name in ('git', 'bash', 'ca-certificates'):
        assert re.search(r'\b' + name + r'=[\w.:+~-]+', docker)
    build = read_yaml('pipeline-build-ci-infra-tools.yaml')['spec']
    assert build['results'][0]['value'] == '$(tasks.build.results.digest)'
    args = build['tasks'][1]['taskSpec']['steps'][0]['args']
    assert '--digest-file=$(results.digest.path)' in args
    assert '--custom-platform=linux/amd64' in args


def test_manifest_shell_syntax_and_credential_transport(tmp_path):
    for name in ('resolve', 'clone', 'check'):
        for step in read_yaml('task-ci-infra-' + name + '.yaml')['spec']['steps']:
            script = step['script']
            subprocess.run(['bash', '-n'], input=script, text=True, check=True)
            assert 'set -x' not in script and 'http://$' not in script
            assert '$(params.' not in script  # all untrusted params enter via env
            if name != 'check':
                assert 'GIT_CONFIG_VALUE_0="Authorization: Basic $auth"' in script
                assert 'git -c' not in script
                assert 'unset GIT_USERNAME GIT_PASSWORD' in script
    subprocess.run(['bash', '-n', str(ROOT / 'scripts/landing/ci-infra.sh')], check=True)


if __name__ == '__main__':
    validate_images(ready='--ready' in sys.argv)
