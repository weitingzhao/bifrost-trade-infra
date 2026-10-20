"""TD-379: on the agent host, no directory the agent user can write comes before the system's
toolchain on PATH. The agent units and the scripts that run an executor as the agent user set
PATH; ~/.local/bin (where claude and cursor-agent are installed) goes last, so a program an
executor drops there as `node` or `go` is never run in place of the real one.

    python3 -m unittest scripts/agent-host/test_agent_path.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Every file that sets PATH for the agent user, and how many PATH values each sets.
FILES = {
    "bifrost-agentd.service": 1,
    "bifrost-agentd-stg.service": 1,
    "bifrost-agentd-bench@.service": 1,
    "bifrost-agentd-exam@.service": 1,
    "confine-probe.sh": 1,
    "codex-sandbox-probe.sh": 1,
    "check-agent-06.sh": 1,
    "prepare-agent-06.sh": 1,
    "agent-06-owner.sh": 1,
}

SYSTEM = ("/usr/local/lib/nodejs/current/bin", "/usr/local/go/bin", "/usr/local/bin", "/usr/bin", "/bin")

# A PATH value that names the agent user's home: Environment=PATH=…, PATH="…", PATH=… in a command.
VALUE = re.compile(r'PATH="?([^"\s]*\.local/bin[^"\s]*)')


def agent_writable(entry: str) -> bool:
    return entry.startswith("/home/") or "$u/" in entry or ".local" in entry or "$HOME" in entry


def values(text: str) -> list[str]:
    return VALUE.findall(text)


def misplaced(value: str) -> list[str]:
    """The agent-writable entries that come before a system directory."""
    entries = value.split(":")
    last_system = max((i for i, e in enumerate(entries) if e in SYSTEM), default=-1)
    return [e for e in entries[:last_system] if agent_writable(e)]


class AgentPath(unittest.TestCase):
    def test_every_file_puts_the_agent_home_last(self) -> None:
        for name, want in FILES.items():
            with self.subTest(file=name):
                found = values((HERE / name).read_text())
                self.assertEqual(len(found), want, f"{name}: PATH values {found}")
                for v in found:
                    self.assertEqual(misplaced(v), [], f"{name}: {v}")

    def test_no_other_file_sets_the_agent_path(self) -> None:
        for path in sorted(HERE.iterdir()):
            if path.name in FILES or path.name.startswith("test") or not path.is_file():
                continue
            with self.subTest(file=path.name):
                self.assertEqual(values(path.read_text(errors="replace")), [],
                                 f"{path.name} sets the agent user's PATH; add it to FILES")

    def test_the_check_finds_a_misplaced_home(self) -> None:
        # Positive control: the order before TD-379.
        old = "/opt/bifrost/codex/bin:/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/bin:/bin"
        self.assertEqual(misplaced(old), ["/home/$u/.local/bin"])
        self.assertEqual(values(f'Environment=PATH={old}\n'), [old])
        self.assertEqual(misplaced("/usr/bin:/bin:/home/x/.local/bin"), [])


if __name__ == "__main__":
    unittest.main()
