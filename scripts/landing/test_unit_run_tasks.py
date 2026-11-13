"""The two generic unit-run Tasks (CI root design, wave 1).

What they must keep: no repository or product name (everything arrives as a
parameter), no CPU limit, the three scheduling labels, and one shared body:
the database variant differs only by its sidecars and their inputs. The two
step scripts are also run here against a local repository.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / 'k8s/cicd/tekton'
PLAIN = TEKTON / 'task-unit-run.yaml'
WITH_DB = TEKTON / 'task-unit-run-db.yaml'
GITEA = 'http://gitea.cicd.svc.cluster.local:3000/'
# Names the templates must never carry: the workspace's repositories and the
# words of the first unit they were measured with.
FORBIDDEN = re.compile(r'bifrost-(?!unit-run|ci\b)[a-z]|agentrt|platform_|golang|go test|console', re.I)
TIERS = {'branch', 'merge', 'build', 'nightly'}


def task(path):
    return yaml.safe_load(path.read_text())


def containers(doc):
    return doc['spec']['steps'] + doc['spec'].get('sidecars', [])


@pytest.mark.parametrize('path', [PLAIN, WITH_DB])
def test_no_repository_or_product_name(path):
    body = '\n'.join(line for line in path.read_text().splitlines() if 'bifrost.io/' not in line)
    assert FORBIDDEN.findall(body) == []


@pytest.mark.parametrize('path', [PLAIN, WITH_DB])
def test_requests_and_memory_limit_but_no_cpu_limit(path):
    for c in containers(task(path)):
        res = c['computeResources']
        assert set(res['requests']) == {'cpu', 'memory'}, c['name']
        assert set(res['limits']) == {'memory'}, c['name']


@pytest.mark.parametrize('path,needs_db', [(PLAIN, 'false'), (WITH_DB, 'true')])
def test_scheduling_labels(path, needs_db):
    labels = task(path)['metadata']['labels']
    assert labels['bifrost.io/workload'] == 'ci'
    assert labels['bifrost.io/ci-tier'] in TIERS
    assert labels['bifrost.io/needs-db'] == needs_db


def test_database_variant_differs_only_by_its_sidecars():
    plain, db = task(PLAIN)['spec'], task(WITH_DB)['spec']
    assert [s['script'] for s in plain['steps']] == [s['script'] for s in db['steps']]
    assert plain['results'] == db['results']
    assert [p for p in db['params'] if p not in plain['params']] == [
        {'name': 'db-roles', 'type': 'string', 'default': '',
         'description': 'Login roles the Postgres sidecar creates before it reports ready, joined by +'}]
    assert 'sidecars' not in plain and [s['name'] for s in db['sidecars']] == ['postgres', 'redis']


def test_credential_reaches_the_fetch_step_only():
    for path in (PLAIN, WITH_DB):
        fetch, run = task(path)['spec']['steps']
        assert 'gitea-ci-reader' in yaml.safe_dump(fetch)
        assert 'gitea-ci-reader' not in yaml.safe_dump(run)


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, text=True, capture_output=True).stdout.strip()


def step_script(name, tmp_path):
    step = next(s for s in task(PLAIN)['spec']['steps'] if s['name'] == name)
    body = step['script'].replace('/unit/', f'{tmp_path}/unit/')
    for result in task(PLAIN)['spec']['results']:
        body = body.replace(f"$(results.{result['name']}.path)", str(tmp_path / 'results' / result['name']))
    (tmp_path / 'results').mkdir(exist_ok=True)
    (tmp_path / 'unit/src').mkdir(parents=True, exist_ok=True)
    path = tmp_path / f'{name}.sh'
    path.write_text(body)
    return path


@pytest.fixture
def gitea(tmp_path):
    """Two repositories of one org served from disk; a git wrapper maps the Gitea URL onto them."""
    commits = {}
    for name in ('first', 'second'):
        bare = tmp_path / 'gitea/org' / f'{name}.git'
        work = tmp_path / 'seed' / name
        work.mkdir(parents=True)
        git(work, 'init', '-q', '-b', 'main')
        (work / 'file').write_text(name)
        git(work, 'add', 'file')
        git(work, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q', '-m', name)
        subprocess.run(['git', 'clone', '-q', '--bare', str(work), str(bare)], check=True)
        git(bare, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
        commits[name] = (git(work, 'rev-parse', 'HEAD'), git(work, 'rev-parse', 'HEAD^{tree}'))
    real = subprocess.run(['sh', '-c', 'command -v git'], check=True, text=True, capture_output=True).stdout.strip()
    shim = tmp_path / 'bin'
    shim.mkdir()
    (shim / 'git').write_text(
        '#!/bin/sh\nfor a in "$@"; do shift; case "$a" in '
        f'{GITEA}*) a="file://{tmp_path}/gitea/${{a#{GITEA}}}" ;; esac; set -- "$@" "$a"; done\n'
        f'exec {real} "$@"\n')
    (shim / 'git').chmod(0o755)
    return commits, {**os.environ, 'PATH': f'{shim}:{os.environ["PATH"]}', 'GIT_USERNAME': 'u', 'GIT_PASSWORD': 'p'}


def fetch(tmp_path, env, revision, extra='', url=GITEA + 'org/first.git'):
    return subprocess.run(['sh', str(step_script('fetch', tmp_path))], text=True, capture_output=True,
                          env={**env, 'REPO_URL': url, 'REVISION': revision, 'EXTRA_CLONES': extra})


def test_fetch_reports_commit_tree_and_every_checkout(tmp_path, gitea):
    commits, env = gitea
    (c1, t1), (c2, t2) = commits['first'], commits['second']
    done = fetch(tmp_path, env, c1, f'second@{c2}')
    assert done.returncode == 0, done.stderr
    assert (tmp_path / 'results/commit').read_text() == c1
    assert (tmp_path / 'results/tree').read_text() == t1
    assert (tmp_path / 'results/clones').read_text() == f'first {c1} {t1}\nsecond {c2} {t2}\n'
    assert (tmp_path / 'unit/src/second/file').read_text() == 'second'
    assert 'extraheader' not in (tmp_path / 'unit/src/first/.git/config').read_text().lower()


def test_fetch_takes_a_branch_for_a_sibling(tmp_path, gitea):
    commits, env = gitea
    done = fetch(tmp_path, env, commits['first'][0], 'second@main')
    assert done.returncode == 0, done.stderr
    assert f"second {commits['second'][0]} {commits['second'][1]}" in (tmp_path / 'results/clones').read_text()


@pytest.mark.parametrize('revision,extra,url', [
    ('main', '', GITEA + 'org/first.git'),                      # the unit itself must be a commit
    ('{c}', 'second', GITEA + 'org/first.git'),                 # no @revision
    ('{c}', '../x@main', GITEA + 'org/first.git'),              # name leaves the org
    ('{c}', 'first@main', GITEA + 'org/first.git'),             # listed twice
    ('{c}', '', 'http://elsewhere.invalid/org/first.git'),      # not the in-cluster Gitea
])
def test_fetch_refuses_bad_input(tmp_path, gitea, revision, extra, url):
    commits, env = gitea
    done = fetch(tmp_path, env, revision.format(c=commits['first'][0]), extra, url)
    assert done.returncode == 2, (done.stdout, done.stderr)


@pytest.mark.parametrize('command,code', [('test "$UNIT_SHARD_INDEX/$UNIT_SHARD_TOTAL" = 2/6 && test -f here', 0), ('exit 7', 7)])
def test_run_reports_the_command_exit_code(tmp_path, command, code):
    (tmp_path / 'unit/src/repo/sub').mkdir(parents=True)
    (tmp_path / 'unit/src/repo/sub/here').write_text('')
    done = subprocess.run(['sh', str(step_script('run', tmp_path))], env={
        **os.environ, 'UNIT_SRC': f'{tmp_path}/unit/src', 'UNIT_WORKDIR': 'repo/sub', 'UNIT_COMMAND': command,
        'UNIT_SHARD_INDEX': '2', 'UNIT_SHARD_TOTAL': '6'})
    assert done.returncode == code
    assert (tmp_path / 'results/exit-code').read_text() == str(code)
    assert (tmp_path / 'results/duration-seconds').read_text().isdigit()


def test_run_passes_the_unit_on_and_reports_what_the_command_wrote(tmp_path):
    """The command writes failed-tests, tests and fail-class under UNIT_RESULT_DIR; the step copies them
    into results, cut to size, when the command fails as well, and leaves a result empty without its file."""
    (tmp_path / 'unit/src/repo').mkdir(parents=True)
    result = tmp_path / 'unit/result'
    result.mkdir()
    command = ('printf "%s %s %s" "$UNIT_NAME" "$UNIT_TASK" "$UNIT_PLAN_ARG" > "$UNIT_RESULT_DIR/tests"; '
               'head -c 4000 /dev/zero | tr "\\0" x > "$UNIT_RESULT_DIR/failed-tests"; exit 5')
    done = subprocess.run(['sh', str(step_script('run', tmp_path))], env={
        **os.environ, 'UNIT_SRC': f'{tmp_path}/unit/src', 'UNIT_WORKDIR': 'repo', 'UNIT_COMMAND': command,
        'UNIT_SHARD_INDEX': '0', 'UNIT_SHARD_TOTAL': '1', 'UNIT_NAME': 'a/b', 'UNIT_TASK': 'test', 'UNIT_PLAN_ARG': 'k',
        'UNIT_RESULT_DIR': str(result)})
    assert done.returncode == 5
    assert (tmp_path / 'results/exit-code').read_text() == '5'
    assert (tmp_path / 'results/tests').read_text() == 'a/b test k'
    assert (tmp_path / 'results/failed-tests').read_text() == 'x' * 1500
    assert (tmp_path / 'results/fail-class').read_text() == ''


@pytest.mark.parametrize('path', [PLAIN, WITH_DB])
def test_the_run_step_gets_the_unit_and_a_result_directory(path):
    spec = task(path)['spec']
    run = next(s for s in spec['steps'] if s['name'] == 'run')
    env = {e['name']: e['value'] for e in run['env']}
    assert (env['UNIT_NAME'], env['UNIT_TASK'], env['UNIT_PLAN_ARG'], env['UNIT_RESULT_DIR']) == (
        '$(params.unit)', '$(params.task)', '$(params.plan-arg)', '/unit/result')
    assert {'name': 'result', 'mountPath': '/unit/result'} in run['volumeMounts']
    assert {'name': 'result', 'emptyDir': {}} in spec['volumes']
    assert {r['name'] for r in spec['results']} >= {'failed-tests', 'tests', 'fail-class'}
    assert all(p.get('default') == '' for p in spec['params'] if p['name'] in ('unit', 'task', 'plan-arg'))


@pytest.mark.parametrize('workdir', ['/etc', '..', 'repo/../..'])
def test_run_refuses_a_workdir_outside_the_checkout(tmp_path, workdir):
    done = subprocess.run(['sh', str(step_script('run', tmp_path))], env={
        **os.environ, 'UNIT_SRC': f'{tmp_path}/unit/src', 'UNIT_WORKDIR': workdir, 'UNIT_COMMAND': 'true',
        'UNIT_SHARD_INDEX': '0', 'UNIT_SHARD_TOTAL': '1'})
    assert done.returncode == 2
