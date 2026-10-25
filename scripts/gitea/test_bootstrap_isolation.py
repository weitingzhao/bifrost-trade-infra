"""S8 source ratchets and positive controls, without cluster or credentials."""
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('secret_grants', ROOT / 'scripts/test_platform_rbac_secrets.py')
rbac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rbac)


def ci_grants(docs):
    # Reuse the existing binding resolver, including User and Group forms.
    old_namespaces, old_match, old_deny = rbac.PLATFORM_NAMESPACES, rbac.platform_namespaces, rbac.DENY
    def subjects(subject, binding_ns):
        kind, name = subject.get('kind'), subject.get('name', '')
        if kind == 'ServiceAccount':
            ns = subject.get('namespace') or binding_ns
        elif kind == 'User' and name.startswith('system:serviceaccount:'):
            ns = name.split(':')[2]
        elif kind == 'Group' and name in ('system:serviceaccounts', 'system:authenticated'):
            return {'cicd'}
        elif kind == 'Group' and name.startswith('system:serviceaccounts:'):
            ns = name.split(':')[2]
        else:
            return set()
        return {ns} if ns == 'cicd' else set()
    try:
        rbac.platform_namespaces = subjects
        rbac.DENY = {('gitea-admin', 'gitea-bootstrap')}
        return rbac.grants(docs)
    finally:
        rbac.PLATFORM_NAMESPACES, rbac.platform_namespaces, rbac.DENY = old_namespaces, old_match, old_deny


def test_no_ci_grants_in_source():
    assert not ci_grants(rbac.load(sorted((ROOT / 'k8s').rglob('*.yaml'))))


def test_ci_grant_detector_positive_controls():
    role = {'kind': 'ClusterRole', 'metadata': {'name': 'bad'},
            'rules': [{'apiGroups': ['*'], 'resources': ['*'], 'verbs': ['*']}]}
    for subject in [
        {'kind': 'ServiceAccount', 'namespace': 'cicd', 'name': 'tekton-trigger'},
        {'kind': 'User', 'name': 'system:serviceaccount:cicd:default'},
        {'kind': 'Group', 'name': 'system:authenticated'},
        {'kind': 'Group', 'name': 'system:serviceaccounts:cicd'},
    ]:
        binding = {'kind': 'ClusterRoleBinding', 'metadata': {'name': 'bad'},
                   'roleRef': {'kind': 'ClusterRole', 'name': 'bad'}, 'subjects': [subject]}
        assert ci_grants([role, binding]) == {('cicd', 'gitea-admin', 'gitea-bootstrap')}


def test_namespace_has_no_workloads_or_grants():
    docs = rbac.load(sorted((ROOT / 'k8s/gitea-admin').glob('*.yaml')))
    assert {d['kind'] for d in docs} == {'Namespace', 'Kustomization', 'ResourceQuota', 'ServiceAccount', 'NetworkPolicy'}
    quota = next(d for d in docs if d['kind'] == 'ResourceQuota')
    assert quota['spec']['hard']['count/pods'] == '0'
    assert all(v == '0' for v in quota['spec']['hard'].values())
    assert next(d for d in docs if d['kind'] == 'ServiceAccount')['automountServiceAccountToken'] is False


def test_no_workload_consumes_admin_secret():
    for path in (ROOT / 'k8s').rglob('*.yaml'):
        assert 'gitea-bootstrap' not in path.read_text(), str(path)


def test_all_owner_consumers_use_new_namespace():
    for name in ('scripts/gitea/lib.sh', 'scripts/gitea/rotate-admin-token.sh', 'scripts/k3s/install-ci-webhooks.sh'):
        text = (ROOT / name).read_text()
        assert 'gitea-admin' in text
        assert 'cicd/gitea-bootstrap' not in text
        assert '-n cicd get secret gitea-bootstrap' not in text
    example = list(yaml.safe_load_all((ROOT / 'k8s/cicd/gitea/secret.yaml.example').read_text()))
    assert {d['metadata']['name']: d['metadata']['namespace'] for d in example} == {
        'gitea-bootstrap': 'gitea-admin', 'gitea-ci-reader': 'cicd'}


def test_secret_copy_drops_server_metadata():
    spec = importlib.util.spec_from_file_location('move_bootstrap', ROOT / 'scripts/gitea/move-bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = {'metadata': {'name': 'gitea-bootstrap', 'namespace': 'cicd',
                           'uid': 'old', 'resourceVersion': '7', 'annotations': {'last-applied': 'fixture'}},
              'type': 'Opaque', 'data': {'gitea_admin_token': 'Zml4dHVyZQ=='}}
    copied = module.sanitized(source, 'gitea-admin')
    assert set(copied['metadata']) == {'name', 'namespace', 'labels'}
    assert module.same(source, copied)
    copied['data'] = {'gitea_admin_token': 'b3RoZXI='}
    assert not module.same(source, copied)


def test_secret_errors_never_echo_server_response(monkeypatch, capsys):
    import subprocess
    spec = importlib.util.spec_from_file_location('move_bootstrap', ROOT / 'scripts/gitea/move-bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 1, 'fixture-token', 'fixture-token'))
    import pytest
    with pytest.raises(RuntimeError, match='output suppressed') as error:
        module.invoke('fixture-config', ['create'], {'data': 'fixture-token'})
    assert 'fixture-token' not in str(error.value)
    assert capsys.readouterr().out == ''


def test_delete_checks_equality_and_uid_version(monkeypatch, capsys):
    import json
    import pytest
    spec = importlib.util.spec_from_file_location('move_bootstrap', ROOT / 'scripts/gitea/move-bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = {'metadata': {'uid': 'fixture-uid', 'resourceVersion': '42'},
              'data': {'gitea_admin_token': 'Zml4dHVyZQ=='}}
    target = {'data': {'gitea_admin_token': 'b3RoZXI='}}
    calls = []
    monkeypatch.setattr(module, 'read', lambda config, ns: source if ns == 'cicd' else target)
    def invoke(config, args, data=None):
        calls.append((args, json.loads(Path(args[-1]).read_text())))
        return {}
    monkeypatch.setattr(module, 'invoke', invoke)
    monkeypatch.setattr(module.sys, 'argv', ['move', '--kubeconfig', 'fixture', 'delete-old'])
    with pytest.raises(RuntimeError, match='differ'):
        module.main()
    assert calls == []
    target['data'] = dict(source['data'])
    module.main()
    args, body = calls[0]
    assert args[:3] == ['delete', '--raw', '/api/v1/namespaces/cicd/secrets/gitea-bootstrap']
    assert body['preconditions'] == {'uid': 'fixture-uid', 'resourceVersion': '42'}
    assert 'data' not in body
    assert not Path(args[-1]).exists()
    assert 'Zml4dHVyZQ==' not in capsys.readouterr().out


def test_copy_uses_create_and_dry_run_without_printing(monkeypatch, capsys):
    import pytest
    spec = importlib.util.spec_from_file_location('move_bootstrap', ROOT / 'scripts/gitea/move-bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = {'data': {'gitea_admin_token': 'Zml4dHVyZQ=='}}
    calls = []
    monkeypatch.setattr(module, 'read', lambda *a: source)
    monkeypatch.setattr(module, 'invoke', lambda config, args, data=None: calls.append((args, data)))
    for step, namespace, dry in [('dry-run', 'gitea-admin', True), ('copy', 'gitea-admin', False),
                                 ('rollback-dry-run', 'cicd', True), ('rollback-copy', 'cicd', False)]:
        monkeypatch.setattr(module.sys, 'argv', ['move', '--kubeconfig', 'fixture', step])
        module.main()
        args, obj = calls[-1]
        assert args[0] == 'create'
        assert ('--dry-run=server' in args) == dry
        assert obj['metadata']['namespace'] == namespace
    assert 'Zml4dHVyZQ==' not in capsys.readouterr().out
    def refuse(*a, **k):
        raise RuntimeError('already exists')
    monkeypatch.setattr(module, 'invoke', refuse)
    with pytest.raises(RuntimeError, match='already exists'):
        module.main()
