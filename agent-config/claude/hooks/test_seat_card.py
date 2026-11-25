"""seat-card.py (Station, Owner LAW-5, 2026-11-21): the card reaches the agent at session start and
before it asks a person; a session outside the seats table gets the way in; nothing ever breaks a session.
Origin: 2026-11-21 entry test, a fresh Claude found the rules but no seat and no way to claim or hand in work.

    python3 -m unittest agent-config/claude/hooks/test_seat_card.py
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SID = 'local_test-seat'


class SeatCard(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        ac = self.tmp / 'agent-config'
        (ac / 'claude/hooks').mkdir(parents=True)
        (ac / 'charters/cards').mkdir(parents=True)
        (ac / 'scripts').mkdir()
        shutil.copy(HERE / 'seat-card.py', ac / 'claude/hooks/seat-card.py')
        shutil.copy(HERE.parents[1] / 'scripts/render-card.py', ac / 'scripts/render-card.py')
        (ac / 'charters/seats.yaml').write_text(textwrap.dedent(f'''\
            seats:
              - {{id: t1, name: test, charter: t1.md, domain: "99", kind: owner, harness: claude, session: {SID}}}
            '''))
        (ac / 'charters/cards/t1.yaml').write_text(textwrap.dedent('''\
            as_of: 2026-11-21
            laws: [67]
            owns: [the test bench]
            promises: [answer tests]
            decide_alone: [how the bench is built]
            must_answer: [is the bench up]
            not_mine: [{what: verdicts, to: audit}]
            walls: [no trading]
            '''))
        self.hook = ac / 'claude/hooks/seat-card.py'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_hook(self, payload, sid=SID):
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_CODE_HOST_SESSION_ID'}
        if sid is not None:
            env['CLAUDE_CODE_HOST_SESSION_ID'] = sid
        r = subprocess.run([sys.executable, str(self.hook)], input=payload, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        return json.loads(r.stdout)['hookSpecificOutput']['additionalContext'] if r.stdout.strip() else None

    def test_session_start_and_compact_get_the_whole_card(self):
        for source in ('startup', 'compact'):
            out = self.run_hook(json.dumps({'hook_event_name': 'SessionStart', 'source': source}))
            self.assertIn('【t1】', out)
            self.assertIn('no trading', out)

    def test_before_asking_a_person_gets_decide_alone_and_walls(self):
        out = self.run_hook(json.dumps({'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion'}))
        self.assertIn('how the bench is built', out)
        self.assertIn('no trading', out)

    def test_unknown_session_gets_the_way_in(self):
        out = self.run_hook(json.dumps({'hook_event_name': 'SessionStart'}), sid=None)
        self.assertIn('AGENTS.md', out)

    def test_unknown_session_asking_gets_nothing(self):
        self.assertIsNone(self.run_hook(json.dumps({'hook_event_name': 'PreToolUse'}), sid='local_other'))

    def test_garbage_input_never_breaks_the_session(self):
        # Positive control for the fail-soft path: same hook, unparseable stdin.
        self.assertIsNone(self.run_hook('not json'))


if __name__ == '__main__':
    unittest.main()
