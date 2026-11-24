"""The CI line's self-description (admission.yaml) is reconciled with the land script it describes.

Origin: 2026-11-22, law 95 (Owner, via the coordinator): every domain says what it takes to use it, and the
brief requires that a check changing without its description changing is found by a machine (law 93, no
second hand-kept copy). Station's scripts/station/test_requires.py did this outside the CI's test list
(infracheck's quick list runs scripts/landing, not scripts/station); this file is the same reconciliation
where the CI runs it. On 11-21 the land runs the cluster kept had 39 refusals (a reading, not archived).
"""
import pathlib
import re
import unittest

import yaml

LANDING = pathlib.Path(__file__).resolve().parent
INFRA = LANDING.parents[1]
DOC = yaml.safe_load((LANDING / "admission.yaml").read_text())
SCRIPT = (INFRA / DOC["checked_by"]).read_text()


class AdmissionIsTheLandScript(unittest.TestCase):
    def test_every_refusal_the_script_says_has_an_entry(self):
        """Positive control: the script says refusals at all, and each one is described."""
        said = sorted(set(re.findall(r"""['"](refused: [^'"]+)['"]""", SCRIPT)))
        self.assertGreater(len(said), 15)
        matches = [r["match"] for r in DOC["refusals"]]
        self.assertEqual([s for s in said if not any(s.startswith(m) for m in matches)], [])

    def test_every_entry_is_something_the_script_says(self):
        for r in DOC["refusals"]:
            self.assertIn(r["match"], SCRIPT, r["match"])
            self.assertIn(r["kind"], ("you", "system", "wall"), r["match"])

    def test_every_quoted_sentence_of_bring_is_in_its_checking_file(self):
        for b in DOC["bring"]:
            w = b["refused_with"]
            if w.get("file") == "none" or w.get("repo"):
                continue  # another repository's check (platform codeguard): reconciled there, not here
            self.assertIn(w["says"], (INFRA / (w.get("file") or DOC["checked_by"])).read_text(), b["id"])

    def test_it_says_what_it_is(self):
        for key in ("format", "about", "owner", "task", "how", "bring", "refusals", "must_answer"):
            self.assertTrue(DOC.get(key), key)
        self.assertEqual(DOC["format"], "station.requires/v1")


if __name__ == "__main__":
    unittest.main()
