"""put-reader-token.sh (TD-432) against a fake Gitea and a fake kubectl, on a pty.

    python3 -m unittest scripts/gitea/test_put_reader_token.py
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

try:
    from .file_http_fixture import ThreadingHTTPServer
except ImportError:
    from file_http_fixture import ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_gitea_scripts import GITEA_TOKEN_FIXTURE, run_on_pty  # noqa: E402

MODES = {
    "stg": ("bifrost-platform-reader-stg", "bifrost-platform-stg", "bifrost-gitea-reader"),
    "prod": ("bifrost-platform-reader-prod", "bifrost-platform-prod", "bifrost-gitea-reader"),
    "ci": ("bifrost-ci-reader", "cicd", "gitea-ci-reader"),
}

FAKE_KUBECTL = r"""#!/usr/bin/env bash
# fake kubectl for put-reader-token tests
state="$FAKE_STATE"; echo "$*" >> "$state/calls"; args=" $* "
case "$args" in
  *" --dry-run=server -f - "*) cat >/dev/null; echo 'server dry run' ;;
  *" get secret $FAKE_NAME -o name "*) [[ -f "$state/secret.yaml" ]] && echo secret/x && exit 0; exit 1 ;;
  *" -n $FAKE_NS get serviceaccount default "*) echo serviceaccount/default ;;
  *" create -f - "*) cat > "$state/secret.yaml"; echo created ;;
  *" replace -f - "*) [[ -f "$state/secret.yaml" ]] || exit 1; cat > "$state/secret.yaml"; echo replaced ;;
  *" get secret $FAKE_NAME -o json "*) python3 -c 'import json,sys,yaml,base64
d = yaml.safe_load(open(sys.argv[1]))
print(json.dumps({"metadata": d["metadata"], "type": d["type"], "data": {k: base64.b64encode(str(v).encode()).decode() for k, v in d["stringData"].items()}}))' "$state/secret.yaml" ;;
  *) echo "unexpected kubectl $*" >&2; exit 9 ;;
esac
"""


class PutReaderToken(unittest.TestCase):
    def setUp(self, mode: str = "stg") -> None:
        self.mode = mode
        self.login, self.ns, self.name = MODES[mode]
        self.tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self.tmp.name)
        self.state = root / "state"
        self.state.mkdir()
        bindir = root / "bin"
        bindir.mkdir()
        (bindir / "kubectl").write_text(FAKE_KUBECTL)
        (bindir / "kubectl").chmod(0o755)
        self.kubeconfig = root / "admin.yaml"
        self.kubeconfig.write_text("fixture\n")
        self.primaries = root / "gitea-primary.txt"
        self.primaries.write_text("# comment\nbifrost-platform\n\nbifrost-ui  # trailing\n")
        self.path = f"{bindir}:{os.environ['PATH']}"
        # repo -> (admin, push, pull) as the token's user sees it
        self.perms = {"bifrost-trade-infra": (False, False, True), "bifrost-platform": (False, False, True), "bifrost-ui": (False, False, True),
                      "repo-template": (False, False, True)}
        self.push_code = 403
        self.user_scope = True
        self.org_scope = True
        self.is_admin = False
        self.who = self.login
        self.hidden: set[str] = set()
        # extra search pages after the first, each a list of (full_name, admin, push)
        self.more_pages: list[list[tuple[str, bool, bool]]] = []
        self.pages_asked: list[int] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                auth = self.headers.get("Authorization", "")
                ok = auth == "token " + GITEA_TOKEN_FIXTURE
                basic = auth == "Basic " + base64.b64encode(f"{outer.login}:{GITEA_TOKEN_FIXTURE}".encode()).decode()
                path = urllib.parse.urlsplit(self.path).path
                code, body = 404, {}
                if path == "/api/v1/user":
                    if not ok:
                        code = 401
                    elif outer.user_scope:
                        code, body = 200, {"login": outer.who, "is_admin": outer.is_admin}
                    else:
                        code, body = 403, {"message": "token does not have at least one of required scope(s): [read:user]"}
                elif path == "/api/v1/orgs/bifrost/repos":
                    if not ok:
                        code = 401
                    elif outer.org_scope:
                        code, body = 200, []
                    else:
                        code, body = 403, {"message": "token does not have at least one of required scope(s): [read:organization]"}
                elif path == "/api/v1/repos/search":
                    page = int(urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)["page"][0])
                    outer.pages_asked.append(page)
                    if page == 1:
                        rows = [{"full_name": "bifrost/" + r, "permissions": {"admin": a, "push": p, "pull": q}}
                                for r, (a, p, q) in sorted(outer.perms.items()) if r not in outer.hidden]
                    elif page - 2 < len(outer.more_pages):
                        rows = [{"full_name": n, "permissions": {"admin": a, "push": p, "pull": True}}
                                for n, a, p in outer.more_pages[page - 2]]
                    else:
                        rows = []
                    code, body = (200, {"ok": True, "data": rows}) if ok else (401, {})
                elif path.startswith("/api/v1/repos/bifrost/"):
                    repo = path.rsplit("/", 1)[1]
                    if not ok:
                        code = 401
                    elif repo in outer.perms:
                        admin, push, pull = outer.perms[repo]
                        code, body = 200, {"permissions": {"admin": admin, "push": push, "pull": pull}}
                elif path.endswith("/info/refs") and "service=git-upload-pack" in self.path:
                    code = 200 if basic else 401
                elif path.endswith("/info/refs") and "service=git-receive-pack" in self.path:
                    code = outer.push_code if basic else 401
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_it(self, typed: str | None = GITEA_TOKEN_FIXTURE, tty: bool = True, mode: str | None = None,
               extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": self.path, "FAKE_STATE": str(self.state), "FAKE_NS": self.ns, "FAKE_NAME": self.name,
               "PUT_TOKEN_KUBECONFIG": str(self.kubeconfig), "GITEA_PRIMARIES_FILE": str(self.primaries),
               "GITEA_PUBLIC_BASE": f"http://127.0.0.1:{self.server.server_address[1]}/bifrost", "NO_PROXY": "*", "no_proxy": "*"}
        self.assertEqual(shutil.which("kubectl", path=env["PATH"]), str(self.root / "bin" / "kubectl"))
        cmd = ["bash", str(HERE / "put-reader-token.sh"), self.mode if mode is None else mode, *extra]
        if not tty:
            return subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        r, self.echoed = run_on_pty(cmd, env, typed)
        return r

    def test_creates_a_basic_auth_secret_for_each_account(self) -> None:
        import yaml
        for mode in MODES:
            with self.subTest(mode):
                self.tearDown()
                self.setUp(mode)
                r = self.run_it()
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                doc = yaml.safe_load((self.state / "secret.yaml").read_text())
                self.assertEqual(doc["type"], "kubernetes.io/basic-auth")
                self.assertEqual((doc["metadata"]["name"], doc["metadata"]["namespace"]), (self.name, self.ns))
                self.assertEqual(doc["stringData"], {"username": self.login, "password": GITEA_TOKEN_FIXTURE})
                self.assertIn(f"ok    token of {self.login}, not an administrator", r.stdout)
                self.assertIn("ok    3 primaries: read only (fetch 200, push refused)", r.stdout)
                self.assertIn("ok    it sees 4 repositories and can write none", r.stdout)
                self.assertIn(f"==> Secret {self.ns}/{self.name} created", r.stdout)
                self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr + self.echoed + (self.state / "calls").read_text())

    def test_nothing_written_when_anything_is_wrong(self) -> None:
        cases = (
            ("secret already there", lambda: (self.state / "secret.yaml").write_text("old"), None, "already exists"),
            ("not a Gitea token", lambda: None, "github_pat_x", "40 hex characters"),
            ("token Gitea refuses", lambda: None, "e" * 40, "GET /api/v1/user → HTTP 401"),
            ("a token without user scope", lambda: setattr(self, "user_scope", False), None, "the token has no user scope"),
            ("another account's token", lambda: setattr(self, "who", "bifrost-mbp"), None, "does not belong to bifrost-platform-reader-stg"),
            ("a site administrator", lambda: setattr(self, "is_admin", True), None, "is a site administrator"),
            ("a token without organization scope", lambda: setattr(self, "org_scope", False), None, "no organization scope"),
            ("a primary it cannot read", lambda: self.perms.pop("bifrost-ui"), None, "GET /api/v1/repos/bifrost/bifrost-ui → HTTP 404"),
            ("a writer of a primary", lambda: self.perms.update({"bifrost-ui": (False, True, True)}), None, "a reader must only read"),
            ("a token that can push", lambda: setattr(self, "push_code", 200), None, "push handshake on bifrost-platform → 200"),
            ("a push handshake that errs", lambda: setattr(self, "push_code", 500), None, "HTTP 500: neither a verified refusal nor a yes"),
            ("administrator of another repository", lambda: self.perms.update({"repo-template": (True, True, True)}), None,
             "is administrator or writer of an unexpected repository"),
            ("a primary the search does not show", lambda: self.hidden.add("bifrost-ui"), None, "the search does not show: bifrost/bifrost-ui"),
            # review 542 A6: page 21 used to be past the last page read, and the run passed
            ("a writable repository on page 21",
             lambda: self.more_pages.extend([[(f"bifrost/r{p}-{i}", False, False) for i in range(50)] for p in range(2, 21)]
                                            + [[("bifrost/late", False, True)]]), None, "is administrator or writer of an unexpected repository"),
            ("a search that never ends",
             lambda: self.more_pages.extend([[(f"bifrost/r{p}", False, False)] for p in range(2, 60)]), None,
             "still returned repositories at page 40; the check is not finished"),
        )
        for name, change, typed, words in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                change()
                before = (self.state / "secret.yaml").read_text() if (self.state / "secret.yaml").exists() else None
                r = self.run_it(typed=GITEA_TOKEN_FIXTURE if typed is None else typed)
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)
                self.assertIn(words, r.stderr, name)
                self.assertIn("Nothing was written.", r.stderr, name)
                after = (self.state / "secret.yaml").read_text() if (self.state / "secret.yaml").exists() else None
                self.assertEqual(before, after, name)
                self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr, name)

    def test_replace_rotates_an_existing_secret_only(self) -> None:
        import yaml
        (self.state / "secret.yaml").write_text(yaml.safe_dump({
            "metadata": {"name": self.name, "namespace": self.ns}, "type": "kubernetes.io/basic-auth",
            "stringData": {"username": self.login, "password": "f" * 40}}))
        r = self.run_it()
        self.assertEqual(r.returncode, 1)
        self.assertIn("to rotate its token run: put-reader-token.sh stg replace", r.stderr)
        r = self.run_it(extra=("replace",))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = yaml.safe_load((self.state / "secret.yaml").read_text())
        self.assertEqual(doc["stringData"], {"username": self.login, "password": GITEA_TOKEN_FIXTURE})
        self.assertIn(f"==> Secret {self.ns}/{self.name} replaced", r.stdout)
        self.assertNotIn(GITEA_TOKEN_FIXTURE, r.stdout + r.stderr + self.echoed + (self.state / "calls").read_text())
        (self.state / "secret.yaml").unlink()
        r = self.run_it(extra=("replace",))
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not exist; replace only rotates an existing one", r.stderr)

    def test_replace_writes_nothing_when_the_new_token_fails(self) -> None:
        (self.state / "secret.yaml").write_text("old")
        self.push_code = 200
        r = self.run_it(extra=("replace",))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Nothing was written.", r.stderr)
        self.assertEqual((self.state / "secret.yaml").read_text(), "old")

    def test_reads_every_page_to_the_end(self) -> None:
        self.more_pages = [[(f"bifrost/r{p}-{i}", False, False) for i in range(50)] for p in range(2, 23)]
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pages_asked[-1], 23)
        self.assertIn(f"ok    it sees {4 + 21 * 50} repositories and can write none", r.stdout)

    def test_refuses_without_a_terminal(self) -> None:
        r = self.run_it(tty=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a terminal", r.stderr)
        self.assertFalse((self.state / "secret.yaml").exists())

    def test_refuses_an_unknown_account_or_mode(self) -> None:
        for mode, extra in (("admin", ()), ("stg", ("overwrite",))):
            r = self.run_it(tty=False, mode=mode, extra=extra)
            self.assertEqual(r.returncode, 2, mode)
            self.assertIn("usage:", r.stderr)


if __name__ == "__main__":
    unittest.main()
