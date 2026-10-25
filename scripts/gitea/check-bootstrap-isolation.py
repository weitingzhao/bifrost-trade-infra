#!/usr/bin/env python3
"""Owner read-only S8 preflight: no Secret values are requested.

RBAC has no deny rule: moving the Secret only helps if workload identities have
no additive grants in its new namespace. SAR includes the real SA groups.
"""
import json
import subprocess
import sys

NAMESPACE = 'gitea-admin'
ACCOUNTS = [
    ('bifrost-platform-stg', 'bifrost-platform'),
    ('bifrost-platform-prod', 'bifrost-platform'),
    ('cicd', 'default'), ('cicd', 'tekton-trigger'),
    ('cicd', 'tekton-deliver'), ('cicd', 'bifrost-applier'),
    (NAMESPACE, 'default'),
]
CHECKS = [('get', '', 'secrets', 'gitea-bootstrap'),
          ('list', '', 'secrets', ''), ('watch', '', 'secrets', ''),
          ('list', '', 'secrets', 'gitea-bootstrap'),
          ('watch', '', 'secrets', 'gitea-bootstrap'),
          ('create', '', 'pods', ''), ('create', '', 'serviceaccounts', ''),
          ('create', 'rbac.authorization.k8s.io', 'rolebindings', ''),
          ('patch', '', 'resourcequotas', 'no-workloads'),
          ('update', '', 'resourcequotas', 'no-workloads'),
          ('delete', '', 'resourcequotas', 'no-workloads'),
          ('create', 'tekton.dev', 'taskruns', ''),
          ('create', 'tekton.dev', 'pipelineruns', '')]


def kubectl(*args, data=None):
    result = subprocess.run(['kubectl', *args], input=data, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('kubectl metadata/access check failed: ' + result.stderr[:300])
    return json.loads(result.stdout)


def review(namespace, account, verb, group, resource, name):
    return {'apiVersion': 'authorization.k8s.io/v1', 'kind': 'SubjectAccessReview',
            'spec': {'user': f'system:serviceaccount:{namespace}:{account}',
                     'groups': ['system:serviceaccounts', f'system:serviceaccounts:{namespace}', 'system:authenticated'],
                     'resourceAttributes': {'namespace': NAMESPACE, 'verb': verb,
                                            'group': group, 'resource': resource, 'name': name}}}


def main():
    # Listing SA metadata also covers future CI identities without a code update.
    accounts = set(ACCOUNTS)
    trusted = []
    for ns in ('cicd', 'bifrost-platform-stg', 'bifrost-platform-prod', NAMESPACE):
        for item in kubectl('-n', ns, 'get', 'serviceaccounts', '-o', 'json')['items']:
            name = item['metadata']['name']
            # Argo infrastructure controllers are explicitly trusted, not CI jobs.
            if ns == 'cicd' and name in {'argocd-application-controller', 'argocd-applicationset-controller', 'argocd-server'}:
                trusted.append((ns, name))
            else:
                accounts.add((ns, name))
    failures = []
    for ns, name in sorted(accounts):
        for check in CHECKS:
            status = kubectl('create', '-f', '-', '-o', 'json',
                             data=json.dumps(review(ns, name, *check))).get('status', {})
            if status.get('evaluationError') or status.get('allowed') is not False:
                failures.append(f'{ns}/{name}: {check}')
    resources = 'pods,deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs,taskruns,pipelineruns'
    workloads = kubectl('-n', NAMESPACE, 'get', resources, '-o', 'json')['items']
    if workloads:
        failures.append('workloads exist in gitea-admin')
    quota = kubectl('-n', NAMESPACE, 'get', 'resourcequota', 'no-workloads', '-o', 'json')
    if quota.get('spec', {}).get('hard', {}).get('count/pods') != '0':
        failures.append('count/pods quota is not zero')
    print(f'Checked {len(accounts)} workload identities, {len(CHECKS)} denials each; {len(workloads)} workloads')
    print('Trusted Argo identities (separate infrastructure audit required): ' + ', '.join('/'.join(a) for a in trusted))
    for failure in failures:
        print('FAIL: ' + failure)
    if failures:
        return 1
    print('PASS: workload identities denied; namespace empty; zero Pod quota')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, KeyError, ValueError) as error:
        sys.exit(str(error))
