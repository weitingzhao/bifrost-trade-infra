"""Tests for codex-card.py (Station, 2026-11-21).

Origin: 2026-11-21 entry test of a fresh Codex. It could not tell which seat it sat in or whom to hand back
to, and a dispatched run is only told "Read BRIEF.md"; the Claude side has seat-card.py for the three
moments (start, after compaction, before asking), Codex had nothing.
"""
import importlib.util
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('codex_card', pathlib.Path(__file__).with_name('codex-card.py'))
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

BRIEF = 'invited_by: 11-station\nreply_to: thread:local_abc\n\n# A job\n'


class CodexCard(unittest.TestCase):
    def run_dir(self, brief=BRIEF, agents=None):
        d = pathlib.Path(tempfile.mkdtemp())
        if brief is not None:
            (d / 'BRIEF.md').write_text(brief)
        if agents is not None:
            (d / 'AGENTS.md').write_text(agents)
        return d

    def test_card_names_inviter_and_reply_address(self):
        d = self.run_dir()
        self.assertTrue(cc.write(d))
        text = (d / 'AGENTS.md').read_text()
        self.assertIn('11-station', text)
        self.assertIn('thread:local_abc', text)
        self.assertIn('handover', text)
        # 2026-11-22 entry test: the card sent it to the shared checkout, which lacked howto.py.
        self.assertIn(str(cc.INFRA / 'scripts/station/howto.py'), text)
        self.assertTrue((cc.INFRA / 'scripts/station/howto.py').is_file())

    def test_existing_agents_md_is_kept_and_card_added_once(self):
        d = self.run_dir(agents='# owner notes\nkeep me\n')
        self.assertTrue(cc.write(d))
        self.assertFalse(cc.write(d))
        text = (d / 'AGENTS.md').read_text()
        self.assertEqual(text.count(cc.MARK), 1)
        self.assertTrue(text.startswith(cc.MARK))
        self.assertIn('keep me', text)

    def test_template_placeholder_reply_to_refuses(self):
        d = self.run_dir(brief='invited_by: <seat>\nreply_to: thread:<那个主人的会话号>\n')
        with self.assertRaises(SystemExit):
            cc.write(d)
        self.assertFalse((d / 'AGENTS.md').exists())

    def test_missing_brief_refuses(self):
        with self.assertRaises(SystemExit):
            cc.write(self.run_dir(brief=None))


if __name__ == '__main__':
    unittest.main()
