"""howto.py find: the ten things agents ask most must each be found in the capability directory.

Origin: 2026-11-23 night, 06's rejoin stalled because nobody knew the compute line could open a host-tier
node card; the directory was in shared notes the minis could not read (Station ledger B5, 2026-11-24).
"""
import pathlib
import subprocess
import sys
import unittest

HOWTO = pathlib.Path(__file__).with_name('howto.py')
COMMON = ['加一台节点', '叫醒 4090', '关 4090', 'owner_run_command', '发信', '应用一份清单',
          '重启 Deployment', '临时探针', '进名册', '找 Owner']


def run(*args):
    return subprocess.run([sys.executable, str(HOWTO), *args], capture_output=True, text=True)


class FindTest(unittest.TestCase):
    def test_common_tasks_are_found(self):
        for word in COMMON:
            with self.subTest(word=word):
                r = run('find', word)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(word.lower(), r.stdout.lower())  # in the row or its [section]

    def test_unknown_word_says_where_to_go(self):
        # Positive control for test_common_tasks_are_found: a word that is nowhere must fail, not pass silently.
        r = run('find', 'zz-no-such-task-zz')
        self.assertEqual(r.returncode, 1)
        self.assertIn('11-station', r.stdout)


if __name__ == '__main__':
    unittest.main()
