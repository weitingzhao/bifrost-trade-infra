"""Tests for owner-words-hint.py.

Origin (2026-11-25, LAW-1 four): code kept citing the Owner by date and quote; the rule in
CLAUDE.md alone left 1,430 such lines on main.
"""
import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    'owner_words_hint', pathlib.Path(__file__).with_name('owner-words-hint.py'))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

REPO = '/Users/x/Desktop/stocks/bifrost-trade-infra/agent-config/x.md'
DATED = 'rule (Owner ' + '2026-11-25): ids only'
QUOTED = 'the Owner said: ' + '「批」'


class Hint(unittest.TestCase):
    def test_write_with_owner_date_hints(self):
        out = h.hint({'tool_name': 'Write', 'tool_input': {'file_path': REPO, 'content': 'a\n' + DATED}})
        self.assertIn('get_laws', out)
        self.assertIn(DATED, out)

    def test_edit_with_quote_hints(self):
        out = h.hint({'tool_name': 'Edit', 'tool_input': {'file_path': REPO, 'new_string': QUOTED}})
        self.assertIsNotNone(out)

    def test_multiedit_checks_every_edit(self):
        edits = [{'new_string': 'fine'}, {'new_string': DATED}]
        self.assertIsNotNone(h.hint({'tool_name': 'MultiEdit', 'tool_input': {'file_path': REPO, 'edits': edits}}))

    def test_ids_only_is_quiet(self):  # control for test_write_with_owner_date_hints
        self.assertIsNone(h.hint({'tool_name': 'Write', 'tool_input': {'file_path': REPO, 'content': 'rule (LAW-1 four)'}}))

    def test_notes_and_memory_are_not_checked(self):
        for p in ('/Users/x/.claude/projects/m/memory/a.md', '/Users/x/Library/side-session-notes/n.md'):
            self.assertIsNone(h.hint({'tool_name': 'Write', 'tool_input': {'file_path': p, 'content': DATED}}))


if __name__ == '__main__':
    unittest.main()
