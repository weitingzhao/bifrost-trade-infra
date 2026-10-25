#!/usr/bin/env python3
"""Owner-only S8 copy/compare/delete. Secret data stays in memory, never logs.

No fallback to the old namespace in consumers. Run one step at a time as the
Owner steps specify. This tool intentionally requires an explicit kubeconfig.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

OLD, NEW, NAME = 'cicd', 'gitea-admin', 'gitea-bootstrap'


def invoke(config, args, data=None):
    result = subprocess.run(['kubectl', '--kubeconfig', config, *args],
                            input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        # Admission errors can echo submitted objects; do not relay either stream.
        raise RuntimeError('kubectl failed; output suppressed to protect Secret data')
    return json.loads(result.stdout) if result.stdout.strip() else None


def read(config, ns):
    return invoke(config, ['-n', ns, 'get', 'secret', NAME, '-o', 'json'])


def same(left, right):
    return left.get('type', 'Opaque') == right.get('type', 'Opaque') and left.get('data') == right.get('data')


def sanitized(source, namespace):
    if not source.get('data', {}).get('gitea_admin_token'):
        raise RuntimeError('source admin token is missing or empty')
    return {'apiVersion': 'v1', 'kind': 'Secret',
            'metadata': {'name': NAME, 'namespace': namespace,
                         'labels': {'bifrost.io/component': 'gitea'}},
            'type': source.get('type', 'Opaque'), 'data': source['data']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kubeconfig', required=True)
    parser.add_argument('step', choices=['dry-run', 'copy', 'verify', 'delete-old', 'rollback-dry-run', 'rollback-copy'])
    args = parser.parse_args()
    reverse = args.step.startswith('rollback-')
    src, dst = (NEW, OLD) if reverse else (OLD, NEW)
    source = read(args.kubeconfig, src)
    if args.step in ('verify', 'delete-old'):
        target = read(args.kubeconfig, dst)
        if not same(source, target):
            raise RuntimeError('source and destination differ; nothing deleted')
        if args.step == 'delete-old':
            # DeleteOptions in a mode-600 file contains only UID/resourceVersion,
            # no Secret values. Preconditions reject a source rotated since read.
            body = {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'preconditions': {
                'uid': source['metadata']['uid'], 'resourceVersion': source['metadata']['resourceVersion']}}
            with tempfile.TemporaryDirectory(prefix='bootstrap-delete-') as directory:
                path = Path(directory) / 'preconditions.json'
                path.write_text(json.dumps(body))
                path.chmod(0o600)
                invoke(args.kubeconfig, ['delete', '--raw', f'/api/v1/namespaces/{OLD}/secrets/{NAME}', '-f', str(path)])
            print('PASS: old copy deleted with UID/resourceVersion preconditions')
        else:
            print('PASS: source and destination data/type match (values suppressed)')
        return
    obj = sanitized(source, dst)
    # create, never apply: no last-applied annotation containing the credential,
    # and an existing target is never silently overwritten.
    command = ['create', '-f', '-', '-o', 'json']
    if args.step.endswith('dry-run'):
        command.append('--dry-run=server')
    invoke(args.kubeconfig, command, obj)
    if not args.step.endswith('dry-run') and not same(source, read(args.kubeconfig, dst)):
        raise RuntimeError('destination readback differs; retain source')
    print('PASS: ' + args.step + ' (Secret values suppressed)')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyError, ValueError) as error:
        sys.exit(str(error))
