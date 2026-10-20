"""chief-exam-set.sh against a fake kubectl that keeps one Secret in a directory: the set is
checked before anything is written, the Secret is created or replaced only by the Owner's
kubeconfig, it reads back as the set, and no step prints the set's content.

    python3 -m unittest scripts/agentrt/test_chief_exam_set.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "chief-exam-set.sh"

# The fake keeps $FAKE_K/secret.json (the Secret as created), $FAKE_K/calls (one line a call),
# and reads $FAKE_K/cani ("yes" / "no"), $FAKE_K/forbid (Secrets cannot be read),
# $FAKE_K/drop (a create or replace is taken but not kept), $FAKE_K/echo-fail (a create or replace
# fails quoting what it was sent), $FAKE_K/touch (a file of the set that reading the namespace edits)
# and $FAKE_K/log (platform-api's log).
FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json, os, sys
k = os.environ["FAKE_K"]
a = sys.argv[1:]
def path(n): return os.path.join(k, n)
def has(n): return os.path.exists(path(n))
with open(path("calls"), "a") as f:
    f.write(" ".join(x for x in a if not x.startswith("go-template")) + "\n")
ns = a[a.index("-n") + 1] if "-n" in a else ""
if a[:2] == ["get", "namespace"]:
    if has("touch"):
        with open(open(path("touch")).read().strip(), "ab") as f:
            f.write(b" ")
    print("namespace/" + a[2]); sys.exit(0)
if a[:2] == ["auth", "can-i"]:
    ans = open(path("cani")).read().strip() if has("cani") else "yes"
    print(ans); sys.exit(0 if ans == "yes" else 1)
if "get" in a and "secret" in a:
    if has("forbid"):
        print("Error from server (Forbidden): secrets is forbidden", file=sys.stderr); sys.exit(1)
    s = json.load(open(path("secret.json"))) if has("secret.json") else None
    if s is not None and s["metadata"]["namespace"] != ns:
        s = None
    o = a[a.index("-o") + 1]
    if s is None:
        if "--ignore-not-found" in a: sys.exit(0)
        print("NotFound", file=sys.stderr); sys.exit(1)
    if o == "json": print(json.dumps(s))
    elif o == "name": print("secret/" + s["metadata"]["name"])
    elif o.startswith("jsonpath="): print(s["metadata"].get("annotations", {}).get("bifrost.io/exam-set-sha256", ""), end="")
    elif o.startswith("go-template="): print("".join(x + "\n" for x in sorted(s["data"])), end="")
    sys.exit(0)
if a[:2] in (["create", "-f"], ["replace", "-f"]):
    raw = sys.stdin.read()
    if not raw.strip():
        print("error: no objects passed to " + a[0], file=sys.stderr); sys.exit(1)
    if has("echo-short"):
        print("Error from server: forbidden key point SECRET-KEY-Q1", file=sys.stderr); sys.exit(1)
    if has("echo-fail"):
        print("Error from server (Invalid): admission refused the request " + raw, file=sys.stderr); sys.exit(1)
    s = json.loads(raw)
    if a[0] == "create" and has("secret.json"):
        print("AlreadyExists", file=sys.stderr); sys.exit(1)
    if a[0] == "replace" and not has("secret.json"):
        print("NotFound", file=sys.stderr); sys.exit(1)
    if not has("drop"):
        json.dump(s, open(path("secret.json"), "w"))
    print("secret/%s %s" % (s["metadata"]["name"], "created" if a[0] == "create" else "replaced")); sys.exit(0)
if "logs" in a:
    print(open(path("log")).read() if has("log") else "", end=""); sys.exit(0)
print("fake kubectl: unexpected " + " ".join(a), file=sys.stderr); sys.exit(9)
'''

QUESTIONS = {
    "q1-brief-from-snapshot.json": "Q1",
    "q2-decision-card.json": "Q2",
    "q3-impersonated-approval.json": "Q3",
    "q4-overreach.json": "Q4",
    "q5-handover.json": "Q5",
}


def question(qid: str) -> bytes:
    # A key point no output may carry: it stands for the set's grading keys.
    classes = {"Q1": "exam-brief", "Q2": "exam-card", "Q3": "exam-alert", "Q4": "exam-refuse", "Q5": "exam-handover"}
    return json.dumps({"exam": "chief_of_staff", "question": qid, "class": classes.get(qid, "exam-brief"), "items": [
        {"id": qid + "a", "rules": [{"id": "r", "kind": "require_any", "any_of": ["SECRET-KEY-" + qid]}]}]},
        ensure_ascii=False).encode()


def digest(d: Path) -> str:
    """exam.Load's digest, written out here apart from the script's."""
    h = hashlib.sha256()
    for p in sorted(d.glob("q*.json")):
        raw = p.read_bytes()
        h.update(f"{p.name}\0{len(raw)}\0".encode())
        h.update(raw)
    return h.hexdigest()


class ChiefExamSet(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.k = root / "k"
        self.k.mkdir()
        self.set = root / "set"
        self.set.mkdir()
        for name, qid in QUESTIONS.items():
            (self.set / name).write_bytes(question(qid))
        (self.set / "controls.json").write_text("{}")
        (self.set / "README.md").write_text("not part of the set")
        bindir = root / "bin"
        bindir.mkdir()
        (bindir / "kubectl").write_text(FAKE_KUBECTL)
        (bindir / "kubectl").chmod(0o755)
        self.env = {**os.environ, "FAKE_K": str(self.k), "CHIEF_EXAM_DIR": str(self.set),
                    "CHIEF_EXAM_KUBECONFIG": str(root / "admin.yaml"), "PATH": f"{bindir}:{os.environ['PATH']}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_step(self, *args: str, trace: bool = False) -> subprocess.CompletedProcess:
        r = subprocess.run(["bash", *(["-x"] if trace else []), str(SCRIPT), *args], env=self.env,
                           capture_output=True, text=True, timeout=60)
        out = r.stdout + r.stderr
        for name in QUESTIONS:
            raw = (self.set / name).read_bytes() if (self.set / name).exists() else b""
            self.assertNotIn("SECRET-KEY", out)
            if raw:
                self.assertNotIn(base64.b64encode(raw).decode()[:24], out)
        return r

    def calls(self) -> str:
        p = self.k / "calls"
        return p.read_text() if p.exists() else ""

    def secret(self) -> dict:
        return json.loads((self.k / "secret.json").read_text())

    def test_digest_is_exam_loads(self) -> None:
        r = self.run_step("digest")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sha256 " + digest(self.set), r.stdout)
        self.assertEqual(self.calls(), "")

    def test_put_creates_the_secret_from_the_five_files(self) -> None:
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.secret()
        self.assertEqual(s["metadata"]["namespace"], "bifrost-platform-stg")
        self.assertEqual(s["metadata"]["name"], "bifrost-chief-exam")
        self.assertEqual(sorted(s["data"]), sorted(QUESTIONS))
        for name in QUESTIONS:
            self.assertEqual(base64.b64decode(s["data"][name]), (self.set / name).read_bytes())
        self.assertEqual(s["metadata"]["annotations"]["bifrost.io/exam-set-sha256"], digest(self.set))
        self.assertIn("holds the set: sha256 " + digest(self.set), r.stdout)
        self.assertIn("create -f -", self.calls())

    def test_put_prod_writes_prods_namespace(self) -> None:
        r = self.run_step("put", "prod", digest(self.set))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.secret()["metadata"]["namespace"], "bifrost-platform-prod")

    def test_put_again_changes_nothing(self) -> None:
        self.assertEqual(self.run_step("put", "stg", digest(self.set)).returncode, 0)
        (self.k / "calls").unlink()
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing changed", r.stdout)
        self.assertNotIn("create -f", self.calls())
        self.assertNotIn("replace -f", self.calls())

    def test_put_a_new_set_replaces(self) -> None:
        self.assertEqual(self.run_step("put", "stg", digest(self.set)).returncode, 0)
        (self.set / "q3-impersonated-approval.json").write_bytes(question("Q3") + b" ")
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("replace -f -", self.calls())
        self.assertEqual(self.secret()["metadata"]["annotations"]["bifrost.io/exam-set-sha256"], digest(self.set))

    def test_put_refuses_a_kubeconfig_that_cannot_write_secrets(self) -> None:
        (self.k / "cani").write_text("no")
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 1)
        self.assertIn("the Owner's", r.stderr)
        self.assertFalse((self.k / "secret.json").exists())
        self.assertNotIn("-f -", self.calls())

    def test_put_refuses_a_set_of_the_wrong_shape(self) -> None:
        cases = {
            "four files": lambda: (self.set / "q5-handover.json").unlink(),
            "a sixth": lambda: (self.set / "q6-extra.json").write_bytes(question("Q6")),
            "not JSON": lambda: (self.set / "q2-decision-card.json").write_text('{"exam": "chief_of_staff", SECRET-KEY'),
            "another exam": lambda: (self.set / "q1-brief-from-snapshot.json").write_text('{"exam": "implementer", "items": [1]}'),
            "a link": lambda: ((self.set / "q4-overreach.json").unlink(), (self.set / "q4-overreach.json").symlink_to(self.set / "q3-impersonated-approval.json")),
        }
        for what, spoil in cases.items():
            with self.subTest(what):
                self.tearDown()
                self.setUp()
                spoil()
                r = self.run_step("put", "stg", digest(self.set))
                self.assertEqual(r.returncode, 1, what)
                self.assertIn("chief-exam-set:", r.stderr)
                self.assertEqual(self.calls(), "", what)

    def test_put_says_so_when_the_secret_does_not_read_back(self) -> None:
        (self.k / "drop").write_text("")
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not read back as this set", r.stderr)

    def test_put_takes_only_the_sha256_it_is_given(self) -> None:
        for args in ((), ("1fb1",), ("0" * 64,)):
            with self.subTest(args):
                r = self.run_step("put", "stg", *args)
                self.assertEqual(r.returncode, 1)
                self.assertIn("nothing changed", r.stderr)
                self.assertEqual(self.calls(), "")

    def test_put_refuses_a_set_the_platform_would_not_load(self) -> None:
        # Review 445 A1: each of these loads in no platform (exam.Load, exam.Platform).
        def edit(name, f):
            q = json.loads((self.set / name).read_text())
            f(q)
            (self.set / name).write_text(json.dumps(q))
        cases = {
            "a null item": lambda q: q.update(items=[None]),
            "a null rule": lambda q: q["items"][0].update(rules=[None]),
            "no rule": lambda q: q["items"][0].update(rules=[]),
            "an unknown kind": lambda q: q["items"][0]["rules"][0].update(kind="llm_judge"),
            "a rule without an id": lambda q: q["items"][0]["rules"][0].pop("id"),
            "no question id": lambda q: q.pop("question"),
            "a class not scored": lambda q: q.update({"class": "exam-other"}),
            "an item id twice": lambda q: q.update(items=q["items"] + q["items"]),
        }
        for what, f in cases.items():
            with self.subTest(what):
                self.tearDown()
                self.setUp()
                edit("q3-impersonated-approval.json", f)
                r = self.run_step("put", "stg", digest(self.set))
                self.assertEqual(r.returncode, 1, what)
                self.assertIn("q3-impersonated-approval.json", r.stderr)
                self.assertEqual(self.calls(), "", what)
        self.tearDown()
        self.setUp()
        # The same id in two questions.
        edit("q4-overreach.json", lambda q: q["items"][0].update(id="Q3a"))
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 1)
        self.assertIn("comes twice", r.stderr)

    def test_put_sends_only_the_set_it_checked(self) -> None:
        # Review 445 B1: a file edited after the check is not sent.
        (self.k / "touch").write_text(str(self.set / "q1-brief-from-snapshot.json"))
        want = digest(self.set)
        r = self.run_step("put", "stg", want)
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing was sent", r.stderr)
        self.assertFalse((self.k / "secret.json").exists())

    def test_put_reads_the_data_not_the_annotation(self) -> None:
        # Review 445 C2: data changed by hand under the same annotation is put back.
        self.assertEqual(self.run_step("put", "stg", digest(self.set)).returncode, 0)
        s = self.secret()
        s["data"]["q2-decision-card.json"] = base64.b64encode(b'{"exam": "chief_of_staff"}').decode()
        (self.k / "secret.json").write_text(json.dumps(s))
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("replace -f -", self.calls())
        self.assertEqual(base64.b64decode(self.secret()["data"]["q2-decision-card.json"]),
                         (self.set / "q2-decision-card.json").read_bytes())

    def test_a_refused_write_does_not_quote_the_request(self) -> None:
        # Review 445 C1: kubectl's message is cut to a line, base64 runs masked (run_step checks the output).
        (self.k / "echo-fail").write_text("")
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 1)
        self.assertIn("was not created (kubectl: Invalid)", r.stderr)

    def test_a_refused_write_quotes_nothing_under_xtrace_or_in_plain_text(self) -> None:
        # Review 446 A1: kubectl's answer never reaches a shell variable (bash -x would print it), and a
        # short plain-text quote in it is not shown either (run_step checks both outputs for the set).
        (self.k / "echo-fail").write_text("")
        r = self.run_step("put", "stg", digest(self.set), trace=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("was not created (kubectl: Invalid)", r.stderr)
        (self.k / "echo-fail").unlink()
        (self.k / "echo-short").write_text("")
        r = self.run_step("put", "stg", digest(self.set))
        self.assertEqual(r.returncode, 1)
        self.assertIn("kubectl said something not shown here", r.stderr)
        r = self.run_step("put", "stg", digest(self.set), trace=True)
        self.assertEqual(r.returncode, 1)

    def test_put_refuses_another_environment(self) -> None:
        r = self.run_step("put", "dev")
        self.assertEqual(r.returncode, 1)
        self.assertIn("say stg or prod", r.stderr)
        self.assertEqual(self.calls(), "")

    def test_check_is_ready_when_platform_api_loaded_this_set(self) -> None:
        self.assertEqual(self.run_step("put", "stg", digest(self.set)).returncode, 0)
        (self.k / "log").write_text(
            "2026/10/20 21:08:08 INFO agentrt: exam set loaded dir=/etc/bifrost/chief-exam sha256=%s\n" % digest(self.set))
        (self.k / "calls").unlink()
        r = self.run_step("check", "stg")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ready: platform-api in bifrost-platform-stg", r.stdout)
        self.assertNotIn("-f -", self.calls())

    def test_check_is_not_ready_otherwise(self) -> None:
        cases = {
            "no Secret, not set": (False, "2026/10/20 21:08:08 INFO agentrt: AGENTRT_EXAM_DIR is not set; the exam routes answer 503\n", "not set"),
            "another set loaded": (True, "INFO agentrt: exam set loaded dir=/x sha256=%s\n" % ("0" * 64), "not the set here"),
            "did not load": (True, 'ERROR agentrt: the exam set did not load; the exam routes answer 503 dir=/x where=q3.json\n', "did not load"),
            "no line": (True, "INFO other\n", "no exam line"),
        }
        for what, (put, log, says) in cases.items():
            with self.subTest(what):
                self.tearDown()
                self.setUp()
                if put:
                    self.assertEqual(self.run_step("put", "stg", digest(self.set)).returncode, 0)
                (self.k / "log").write_text(log)
                r = self.run_step("check", "stg")
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertIn(says, r.stdout)
                self.assertIn("not ready", r.stdout)

    def test_check_reads_on_when_the_secret_cannot_be_read(self) -> None:
        (self.k / "forbid").write_text("")
        (self.k / "log").write_text("INFO agentrt: exam set loaded dir=/x sha256=%s\n" % digest(self.set))
        r = self.run_step("check", "stg")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("cannot read it", r.stdout)
        self.assertIn("loaded a set: sha256 " + digest(self.set), r.stdout)


if __name__ == "__main__":
    unittest.main()
