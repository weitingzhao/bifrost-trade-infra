"""Select an original green platform run; API failures deliberately mean fresh CI."""
import json
import os
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path

FIELDS = ('api-scope', 'api-packages', 'api-store-run', 'api-scope-why', 'failed-tests')


def values(rows):
    result = {}
    for row in rows:
        if row['name'] in result or not isinstance(row['value'], str):
            raise ValueError('ambiguous values')
        result[row['name']] = row['value']
    return result


def stamp(run):
    value = datetime.fromisoformat(run['metadata']['creationTimestamp'].replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('missing timezone')
    return value


def claims_reuse(results):
    # TD-533: a run claims a reuse only with a tested-by naming a run; every run
    # writes tested-by, empty when it tested fresh (Tekton needs the result).
    return results.get('tested-by', '').strip() != ''


def same_increment(params, results, base):
    # Owner 2026-11-15: a run with no base whose commit is not on main takes main's head
    # as its base and names it in base-commit (task-ci-platform-test-api.yaml). Its
    # increment is the current run's only when the current run was handed that commit
    # as its base (the push to main after the landing). A run with no base never
    # reuses an increment: it finds its own base, or runs every test.
    return base != '' and (params.get('base', '') or results.get('base-commit', '')) == base


def select(runs, current, identities, repo, base):
    matches = []
    for run in runs:
        try:
            results = values(run.get('status', {}).get('results', []))
            params = values(run['spec'].get('params', []))
            conditions = run.get('status', {}).get('conditions', [])
            if (run['spec'].get('pipelineRef', {}).get('name') != 'bifrost-ci-platform'
                    or [c['status'] for c in conditions if c['type'] == 'Succeeded'] != ['True']
                    or claims_reuse(results) or stamp(run) >= stamp(current)
                    or params.get('repo-url') != repo
                    or any(results.get(k) != v for k, v in identities.items())
                    or results.get('api-scope') not in ('full', 'console', 'incremental')
                    or any(k not in results for k in FIELDS)
                    or (results['api-scope'] == 'incremental' and not same_increment(params, results, base))):
                continue
            matches.append(run)
        except (KeyError, TypeError, ValueError):
            continue
    return max(matches, key=lambda r: (stamp(r), r['metadata']['name'])) if matches else None


def lookup(read, current_name, identities, repo, base):
    try:
        current = read('/' + current_name)
        listing = read('?labelSelector=tekton.dev%2Fpipeline%3Dbifrost-ci-platform')
        if listing.get('metadata', {}).get('continue'):
            return None
        return select(listing['items'], current, identities, repo, base)
    except Exception:
        return None


def main():
    root = Path('/tekton/results')
    token = Path('/var/run/secrets/kubernetes.io/serviceaccount/token')

    def read(suffix):
        url = 'https://kubernetes.default.svc/apis/tekton.dev/v1/namespaces/cicd/pipelineruns' + suffix
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token.read_text().strip()})
        ctx = ssl.create_default_context(cafile='/var/run/secrets/kubernetes.io/serviceaccount/ca.crt')
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return json.load(response)

    hit = lookup(read, os.environ['RUN'], {k: os.environ[v] for k, v in
                 [('platform-tree', 'TREE'), ('ui-commit', 'UI'), ('infra-commit', 'INFRA')]},
                 os.environ['REPO'], os.environ['BASE'])
    (root / 'reuse').write_text('yes' if hit else 'no')
    (root / 'tested-by').write_text(hit['metadata']['name'] if hit else '')
    if hit:
        results = values(hit['status']['results'])
        shared = Path(os.environ['RESULTS_DIR'])
        shared.mkdir(parents=True, exist_ok=True)
        for name in FIELDS:
            (shared / name).write_text(results[name])
        # Not in FIELDS: a run from before 2026-11-15 has none and is still an original.
        (shared / 'base-commit').write_text(results.get('base-commit') or 'none')


if __name__ == '__main__':
    main()
