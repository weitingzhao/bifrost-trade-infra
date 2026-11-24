"""pick.py: a seat names a harness, the work goes to an account with quota and a resident on that host.

Origin: Station ledger D13 (2026-11-24): the roster gained an accounts table with fallbacks that day, and
two resident lines on the minis; nothing turned "this seat wants Codex" into "send it to that thread".
"""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('pick', pathlib.Path(__file__).with_name('pick.py'))
pick = importlib.util.module_from_spec(spec); spec.loader.exec_module(pick)

TABLE = {
    'accounts': [
        {'id': 'codex@macpro', 'harness': 'codex', 'host': 'Mac Pro', 'fallback': 'codex@mini-01'},
        {'id': 'codex@mini-01', 'harness': 'codex', 'host': 'mini-01', 'fallback': 'codex@mini-02'},
        {'id': 'codex@mini-02', 'harness': 'codex', 'host': 'mini-02', 'fallback': 'codex@macpro'},
    ],
    'temporary': [
        {'id': 'desk', 'account': 'codex@mini-01', 'ended': None, 'session': 'codex-abc'},
        {'id': 'old', 'account': 'codex@mini-02', 'ended': '2026-11-24', 'session': 'codex-old'},
    ],
}


class PickTest(unittest.TestCase):
    def test_starts_on_a_mini_and_finds_the_resident(self):
        # Agents live on the minis (Owner 2026-11-23): a Mac Pro account must not be the first pick.
        acct, resident = pick.pick(TABLE, 'codex')
        self.assertEqual(acct['id'], 'codex@mini-01')
        self.assertEqual(resident['id'], 'desk')

    def test_skip_follows_fallback_and_ignores_ended_residents(self):
        acct, resident = pick.pick(TABLE, 'codex', {'codex@mini-01'})
        self.assertEqual(acct['id'], 'codex@mini-02')
        self.assertIsNone(resident)

    def test_all_skipped_returns_none(self):
        # Positive control for the two above: when every login is out of quota, say so instead of looping.
        self.assertIsNone(pick.pick(TABLE, 'codex', {'codex@mini-01', 'codex@mini-02', 'codex@macpro'}))

    def test_prefers_the_login_with_a_resident(self):
        # 11-24: the resident Claude sits on mini-02 while mini-01 comes first in the chain.
        t = {'accounts': TABLE['accounts'], 'temporary': [{'id': 'c2', 'account': 'codex@mini-02', 'ended': None, 'session': 'local_x'}]}
        acct, resident = pick.pick(t, 'codex')
        self.assertEqual((acct['id'], resident['id']), ('codex@mini-02', 'c2'))

    def test_real_roster_has_a_codex_resident(self):
        import yaml
        acct, resident = pick.pick(yaml.safe_load(pick.SEATS.read_text()), 'codex')
        self.assertTrue(acct['id'].startswith('codex@mini'))
        self.assertIsNotNone(resident)


if __name__ == '__main__':
    unittest.main()
