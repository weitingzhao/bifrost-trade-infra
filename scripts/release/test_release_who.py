"""release.sh's default who: the seat this session sits in.

Origin: 2026-11-22 (Crew, via the comm desk). 17 holds of the release window
could not be told apart by seat: every session defaulted to the same
user@host, and only a random suffix followed it. The default is now the seat
id the roster (agent-config/charters/seats.yaml) gives the session, then
user@host when the session is not in it.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

RELEASE = Path(__file__).resolve().parent / "release.sh"

ROSTER = """\
version: 1
seats:
  - {id: company-coordinator, charter: c.md, session: local_a, mailbox: registered}
  - {id: 8-1-duty,        charter: d.md, session: local_a, mailbox: registered}
  - {id: 3-4-verify-release-ci, charter: e.md, session: local_b, also_domain_ids: [delivery]}
  - {id: 6-compute,       charter: f.md, session: null, liaison: local_c}
temporary:
  - {id: t-1, invited_by: 9-crew, session: local_d}
"""


def default_who(session, env_who=None, roster=ROSTER):
    func = re.search(r"^default_who\(\) \{.*?^\}", RELEASE.read_text(), re.S | re.M).group(0)
    with tempfile.TemporaryDirectory() as tmp:
        seats = Path(tmp) / "seats.yaml"
        seats.write_text(roster)
        env = {k: v for k, v in os.environ.items() if k not in ("BIFROST_RELEASE_WHO", "CLAUDE_CODE_HOST_SESSION_ID")}
        env.update(SEATS_FILE=str(seats), USER="someone")
        if session is not None:
            env["CLAUDE_CODE_HOST_SESSION_ID"] = session
        if env_who is not None:
            env["BIFROST_RELEASE_WHO"] = env_who
        out = subprocess.run(["bash", "-c", func + "\ndefault_who"], env=env, capture_output=True, text=True, check=True)
        return out.stdout


class DefaultWho(unittest.TestCase):
    def test_the_session_s_seat(self):
        self.assertEqual(default_who("local_b"), "3-4-verify-release-ci")

    def test_the_first_row_when_one_session_sits_twice(self):
        self.assertEqual(default_who("local_a"), "company-coordinator")

    def test_a_temporary_seat(self):
        self.assertEqual(default_who("local_d"), "t-1")

    def test_a_liaison_is_not_a_session(self):
        self.assertTrue(default_who("local_c").startswith("someone@"))

    def test_a_session_not_on_the_roster_or_none(self):
        self.assertTrue(default_who("local_zz").startswith("someone@"))
        self.assertTrue(default_who(None).startswith("someone@"))

    def test_the_environment_still_wins(self):
        self.assertEqual(default_who("local_b", env_who="x"), "x")

    def test_every_default_goes_through_it(self):
        self.assertNotIn("${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}", RELEASE.read_text())


if __name__ == "__main__":
    unittest.main()
