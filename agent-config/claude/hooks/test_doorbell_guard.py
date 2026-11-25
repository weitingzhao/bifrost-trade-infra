"""Tests for doorbell-guard.py.

Origin (2026-11-25, ISSUE-2): seats went idle without a doorbell and never heard approval
results already in their mailbox; the Owner had to wake them by hand.
"""
import importlib.util
import pathlib
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location(
    'doorbell_guard', pathlib.Path(__file__).with_name('doorbell-guard.py'))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

# 100 claude -> 200 zsh (hook) -> 300 python (hook itself)
BASE = {
    1: (0, '/sbin/launchd'),
    100: (1, '/Applications/Claude.app/Contents/Resources/claude --resume x'),
    200: (100, '/bin/zsh -c python3 doorbell-guard.py'),
    300: (200, 'python3 doorbell-guard.py'),
}
WITH_BELL = {**BASE, **{
    400: (100, '/bin/zsh -c npx tsx doorbell.ts --minutes 1440'),
    401: (400, 'node tsx bifrost-platform/mcp/platform/src/doorbell.ts --minutes 1440'),
}}
# a doorbell that belongs to another session's claude process
OTHER_BELL = {**BASE, **{
    500: (1, '/x/claude --resume other'),
    501: (500, 'node tsx doorbell.ts'),
}}


class Guard(unittest.TestCase):
    def run_decide(self, table, seat=True, active=False):
        with mock.patch.object(g, 'seat_with_mailbox', return_value=seat):
            return g.decide({'stop_hook_active': active}, 'local_x', table, 300)

    def test_blocks_seat_without_doorbell(self):
        out = self.run_decide(BASE)
        self.assertEqual(out['decision'], 'block')
        self.assertIn('run_in_background', out['reason'])

    def test_lets_go_when_own_doorbell_runs(self):
        self.assertIsNone(self.run_decide(WITH_BELL))

    def test_another_sessions_doorbell_does_not_count(self):
        self.assertEqual(self.run_decide(OTHER_BELL)['decision'], 'block')

    def test_never_blocks_twice(self):  # control for test_blocks_seat_without_doorbell
        self.assertIsNone(self.run_decide(BASE, active=True))

    def test_non_seat_sessions_untouched(self):
        self.assertIsNone(self.run_decide(BASE, seat=False))

    def test_no_claude_ancestor_lets_go(self):
        self.assertIsNone(self.run_decide({300: (1, 'python3 x')}))


if __name__ == '__main__':
    unittest.main()
