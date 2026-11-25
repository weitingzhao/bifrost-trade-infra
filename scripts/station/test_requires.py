"""Self-descriptions keep the station.requires/v1 format, and the precheck refuses what land refuses.

Origin: 2026-11-21, Owner (via the coordinator, LAW-10/77): agents meet the process one refusal at a time; 11-21
saw 39 landing refusals, 8 for a missing Change-Id and 10 for a rebase conflict (CI line's count, a reading of
the land runs the cluster kept). Reconciling the guide with the land script is the CI line's own test, run
in CI: scripts/landing/test_admission.py (11-22); this file keeps only the format and the precheck.
"""
import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
INFRA = HERE.parents[1]
SELF = sorted(INFRA.glob('scripts/**/admission.yaml'))
DOCS = {yaml.safe_load(p.read_text())['tool']: yaml.safe_load(p.read_text()) for p in SELF}

spec = importlib.util.spec_from_file_location('precheck', HERE / 'precheck.py')
precheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(precheck)



class Format(unittest.TestCase):
    def test_every_self_description_is_v1(self):
        self.assertTrue(DOCS)
        for name, d in DOCS.items():
            self.assertEqual(d['format'], 'station.requires/v1', name)
            for key in ('about', 'owner', 'task', 'how', 'bring'):
                self.assertTrue(d.get(key), (name, key))
            for b in d['bring']:
                self.assertIn(b.get('precheck', 'not-covered'), ('checked', 'printed', 'warned', 'not-covered'), (name, b['id']))
                self.assertTrue(b.get('what') and b.get('refused_with'), (name, b['id']))
            for r in d.get('refusals', []):
                self.assertIn(r['kind'], ('you', 'system', 'wall'), r['match'])


class Precheck(unittest.TestCase):
    """A throwaway repo whose origin is named like infra, so the land script's own checks run on it."""

    def repo(self):
        root = pathlib.Path(tempfile.mkdtemp())
        origin, work = root / 'bifrost-trade-infra.git', root / 'work'
        run = lambda *a, cwd=work: subprocess.run(['git', *a], cwd=cwd, check=True, capture_output=True)
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(origin)], check=True)
        subprocess.run(['git', 'clone', '-q', str(origin), str(work)], check=True, capture_output=True)
        run('config', 'user.email', 't@example.invalid'); run('config', 'user.name', 't')
        (work / 'a.txt').write_text('one\n'); run('add', 'a.txt'); run('commit', '-q', '-m', 'base\n\nChange-Id: I0')
        run('push', '-q', 'origin', 'HEAD:main')
        return work, run

    def test_missing_change_id_refused(self):
        work, run = self.repo()
        (work / 'b.txt').write_text('x\n'); run('add', 'b.txt'); run('commit', '-q', '-m', 'no trailer')
        _, found = precheck.check(work)
        self.assertIn('trailers', [rid for level, rid, _ in found if level == 'refuse'])

    def test_change_id_that_is_not_one_word_refused(self):
        work, run = self.repo()
        (work / 'b.txt').write_text('x\n'); run('add', 'b.txt')
        run('commit', '-q', '-m', 'title\n\nWork: unassigned\n\nChange-Id: I1 extra words')
        _, found = precheck.check(work)
        self.assertIn('trailers', [rid for _, rid, _ in found])

    def test_good_commit_passes_and_conflict_is_refused(self):
        work, run = self.repo()
        (work / 'a.txt').write_text('mine\n'); run('commit', '-qam', 'mine\n\nWork: unassigned\nChange-Id: I2')
        self.assertEqual(precheck.check(work)[1], [])
        other = work.parent / 'other'
        subprocess.run(['git', 'clone', '-q', str(work.parent / 'bifrost-trade-infra.git'), str(other)], check=True, capture_output=True)
        run('config', 'user.email', 't@example.invalid', cwd=other); run('config', 'user.name', 't', cwd=other)
        (other / 'a.txt').write_text('theirs\n'); run('commit', '-qam', 'theirs\n\nChange-Id: I3', cwd=other)
        run('push', '-q', 'origin', 'HEAD:main', cwd=other)
        self.assertIn('no-overlap', [rid for _, rid, _ in precheck.check(work)[1]])

    def test_guard_path_refused(self):
        work, run = self.repo()
        globs = [p for g in precheck.policy()['paths']['no_d10_paths'] if g['repo'] in ('bifrost-trade-infra', '*') for p in g['paths']]
        self.assertTrue(globs)
        path = work / globs[0].replace('**', 'x').replace('*', 'x')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('x\n')
        run('add', '-f', str(path)); run('commit', '-q', '-m', 'guard\n\nChange-Id: I4')
        self.assertIn('no-d10-paths', [rid for _, rid, _ in precheck.check(work)[1]])


if __name__ == '__main__':
    unittest.main()
