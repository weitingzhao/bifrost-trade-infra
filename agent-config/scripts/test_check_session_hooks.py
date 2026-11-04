"""python3 -m unittest discover -s agent-config/scripts -p test_check_session_hooks.py"""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_session_hooks", HERE / "check_session_hooks.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
CLAUDE = json.loads((HERE.parent / "claude" / "settings.json").read_text())
CURSOR = json.loads((HERE.parent / "cursor" / "hooks.json").read_text())


def with_timeout(value):
    settings = copy.deepcopy(CLAUDE)
    hook = settings["hooks"]["SessionEnd"][0]["hooks"][0]
    if value is None:
        hook.pop("timeout", None)
    else:
        hook["timeout"] = value
    return settings


class SessionHooks(unittest.TestCase):
    def test_the_repository_wiring_passes(self):
        self.assertEqual(m.problems(CLAUDE, CURSOR), [])

    def test_a_session_end_timeout_is_a_whole_number_of_seconds_at_least_the_floor(self):
        # Review round 1 S2: True, 0, -1 and 1 all passed the first check.
        for bad in (None, True, False, 0, -1, 1, 5, 9, 10.0, 10.5, "10", [10]):
            with self.subTest(timeout=bad):
                self.assertEqual(len(m.problems(with_timeout(bad), CURSOR)), 1)
        for good in (10, 30):
            with self.subTest(timeout=good):
                self.assertEqual(m.problems(with_timeout(good), CURSOR), [])

    def test_every_session_event_must_run_the_heartbeat(self):
        for event in m.CLAUDE_EVENTS:
            settings = copy.deepcopy(CLAUDE)
            del settings["hooks"][event]
            with self.subTest(event=event):
                self.assertTrue(any(event in p for p in m.problems(settings, CURSOR)))
        for event in m.CURSOR_EVENTS:
            hooks = copy.deepcopy(CURSOR)
            hooks["hooks"][event] = [{"command": "node ./scripts/other.js"}]
            with self.subTest(event=event):
                self.assertTrue(any(event in p for p in m.problems(CLAUDE, hooks)))

    def test_malformed_entries_are_not_wiring(self):
        settings = copy.deepcopy(CLAUDE)
        settings["hooks"]["PreCompact"] = ["not an entry", {"hooks": "nope"}]
        self.assertEqual(m.problems(settings, CURSOR), [".claude/settings.json 未接线 thread-heartbeat.js 到 PreCompact"])


if __name__ == "__main__":
    unittest.main()
