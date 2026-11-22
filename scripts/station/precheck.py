#!/usr/bin/env python3
"""Before pushing to ready/: run the checks bifrost-land runs, and say what it would refuse (Station, 2026-11-22).

Usage: precheck.py <checkout> [<commit>]   (commit defaults to HEAD; compared with that checkout's origin/main,
fetched first). Exits 1 when the landing would refuse, 0 otherwise, and prints the push command to use.

The Change-Id and guard-path checks are not copies: they are the land script's own functions, read out of
k8s/cicd/tekton/pipeline-land.yaml of the infra this file sits in and executed here (the way test_land.py
loads them). The guard paths come from agent-config/release-policy/paths.json, the file the signed policy
is made from. What this cannot run (the commit's CI in the cluster) it says so; see requires/land.yaml.
"""
import json
import pathlib
import re
import subprocess
import sys

import yaml

INFRA = pathlib.Path(__file__).resolve().parents[2]


def land_step():
    spec = yaml.safe_load((INFRA / 'k8s/cicd/tekton/pipeline-land.yaml').read_text())['spec']
    (task,) = [t for t in spec['tasks'] if t['name'] == 'land']
    return task['taskSpec']['steps'][0]


def land_functions():
    scope = {'__name__': 'station_precheck'}
    exec(land_step()['script'], scope)  # noqa: S102 - infra's own pipeline file
    return scope


def landing_repos():
    (value,) = [e['value'] for e in land_step()['env'] if e['name'] == 'LANDING_REPOS']
    return sorted(json.loads(value))


def policy():
    return {'paths': json.loads((INFRA / 'agent-config/release-policy/paths.json').read_text())['paths']}


def git(checkout, *args, check=True):
    r = subprocess.run(['git', '-C', str(checkout), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r


def repo_name(checkout):
    url = git(checkout, 'remote', 'get-url', 'origin').stdout.strip()
    return re.sub(r'\.git$', '', url.rstrip('/').rsplit('/', 1)[-1])


def check(checkout, commit='HEAD', fetch=True):
    """[(level, requirement id, sentence)] for the commits origin/main..commit; level is refuse or warn."""
    fn = land_functions()
    out = []
    if fetch:
        git(checkout, 'fetch', '-q', 'origin', 'main')
    sha = git(checkout, 'rev-parse', commit).stdout.strip()
    repo = repo_name(checkout)
    if repo not in landing_repos():
        out.append(('refuse', 'landing-repo', f'{repo} 不在 LANDING_REPOS（{", ".join(landing_repos())}）：用 scripts/release/push-main.sh'))
    commits = git(checkout, 'rev-list', '--reverse', f'origin/main..{sha}').stdout.split()
    if not commits:
        out.append(('refuse', 'ready-branch', f'{sha[:12]} 相对 origin/main 没有新提交'))
    names = set()
    for c in commits:
        if not fn['change_id'](git(checkout, 'log', '-1', '--format=%B', c).stdout):
            out.append(('refuse', 'trailers', f'提交 {c[:12]} 的最后一段没有 Change-Id 尾注（或尾注段里混了别的行、被空行隔开）'))
        names.update(git(checkout, 'show', '--no-renames', '--name-only', '--format=', c).stdout.split())
    hit = fn['guarded'](policy(), repo, names)
    if hit:
        out.append(('refuse', 'no-d10-paths', f'{hit} 是交易执行守卫路径（no_d10_paths），这条路不收'))
    if commits and git(checkout, 'merge-tree', '--write-tree', 'origin/main', sha, check=False).returncode:
        out.append(('refuse', 'no-overlap', '和最新 origin/main 有冲突，合入时 Gitea rebase 不过去：在最新 main 上重做'))
    if repo == 'bifrost-trade-infra' and any(n.startswith('agent-config/') for n in names):
        out.append(('warn', 'agent-config-auto-mode', 'Agent 推 agent-config/ 会被 auto mode 拦下：治理文件分开提交，交成手续由 Owner 推'))
    return sha, out


def main(argv):
    if not 1 <= len(argv) <= 2:
        raise SystemExit(__doc__)
    checkout = pathlib.Path(argv[0]).resolve()
    sha, found = check(checkout, argv[1] if len(argv) > 1 else 'HEAD')
    for level, rid, text in found:
        print(f'[{"会被拒" if level == "refuse" else "提醒"}] {rid}: {text}')
    print('[没查] ci-green-on-current-main: 集群里的 CI 这里跑不了，推之前本地跑改动目录的测试（howto.py land 的 ci_red）')
    refused = any(level == 'refuse' for level, _, _ in found)
    if not refused:
        print(f'推：git -C {checkout} push origin {sha}:refs/heads/ready/<名字>')
    return 1 if refused else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
