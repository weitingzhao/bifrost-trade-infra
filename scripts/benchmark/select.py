#!/usr/bin/env python3
"""Select a diverse, deterministic question set from verify.py JSONL output."""
import argparse
import collections
import json
from pathlib import Path
import sys

QUOTAS = {'go': 6, 'python': 7, 'ts': 5, 'shell': 2}


def select(candidates, quotas=None):
    quotas = QUOTAS if quotas is None else quotas
    pool = {}
    for candidate in candidates:
        if candidate.get('status') == 'verified' and candidate.get('language') in quotas:
            key = (candidate['repo'], candidate['fix_commit'], candidate['language'])
            pool.setdefault(key, candidate)
    selected, missing = [], {}
    repos, files, commits = collections.Counter(), collections.Counter(), set()
    for language, count in quotas.items():
        for _ in range(count):
            eligible = [c for c in pool.values() if c['language'] == language
                        and (c['repo'], c['fix_commit']) not in commits]
            if not eligible:
                break

            def rank(c):
                touched = c['test_files'] + c['non_test_files']
                return (repos[c['repo']], sum(files[c['repo'], p] for p in touched),
                        c['repo'], c['fix_commit'])

            best = min(eligible, key=rank)
            selected.append(best)
            repos[best['repo']] += 1
            commits.add((best['repo'], best['fix_commit']))
            files.update((best['repo'], p) for p in best['test_files'] + best['non_test_files'])
        deficit = count - sum(c['language'] == language for c in selected)
        if deficit:
            missing[language] = deficit
    questions = []
    for index, candidate in enumerate(selected, 1):
        questions.append({'id': f'Q{index:02d}', 'repo': candidate['repo'],
                          'language': candidate['language'],
                          'base_commit': candidate['parent'],
                          'fix_commit': candidate['fix_commit'],
                          'test_files': candidate['test_files'],
                          'check_command': candidate['tests_to_run'],
                          'fails_by': candidate.get('fails_by', 'assertion'),
                          'task_text': candidate['task_text'] + (
                              '\n\nThe tests below must pass; they call ' +
                              ', '.join(candidate['missing_symbols']) +
                              ', which does not exist yet.'
                              if candidate.get('fails_by') == 'missing_symbol' else '')})
    return questions, missing


def parse_quota(text):
    """go=7,python=4,ts=7,shell=2: every language of QUOTAS, each a count >= 0."""
    out = {}
    for part in text.split(','):
        name, _, count = part.partition('=')
        if name not in QUOTAS or not count.isdigit():
            raise argparse.ArgumentTypeError(f'{part!r} is not language=count of {sorted(QUOTAS)}')
        out[name] = int(count)
    if set(out) != set(QUOTAS):
        raise argparse.ArgumentTypeError(f'name every language: {sorted(QUOTAS)}')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verified', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, default=Path('questions.json'))
    parser.add_argument('--quota', type=parse_quota, default=None,
                        help='per language, e.g. go=7,python=4,ts=7,shell=2 (default: the design\'s 6/7/5/2)')
    args = parser.parse_args()
    try:
        candidates = [json.loads(line) for path in args.verified
                      for line in path.read_text().splitlines() if line.strip()]
        questions, missing = select(candidates, args.quota)
        # Never publish a partial set under the final questions filename.
        if missing:
            print(json.dumps({'status': 'short_pool', 'missing': missing,
                              'selected': len(questions)}, ensure_ascii=False), file=sys.stderr)
            return 1
        args.output.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + '\n')
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'status': 'selected', 'count': len(questions), 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
