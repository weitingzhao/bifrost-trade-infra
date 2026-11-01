"""R5:5.7-1: bifrost-ci-platform tests what a commit changes.

Task changes reads the files a commit changes against main and answers
api-scope: console when each is console/** outside console/src/api or Markdown
outside api/ and config/, full otherwise. test-api in console scope runs only
the Go tests that read files outside api/; it still runs, so no task is
skipped and the run's reason stays Succeeded.

These cases run the pipeline's own scripts: changes with dash and git against
local repositories (Gitea's address is rewritten to them by a git wrapper),
test-api's step with bash and go against a small module, and the Go
self-check test-api runs before it narrows (a reader outside api/ that the
list does not cover turns the run full) against small trees. The run's
api-scope result is what a release gate reads (ci_gate.py --require-full).
One auxiliary case runs the self-check on the platform checkout beside this
one, when there is one; the gate is the self-check in the run itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"
GITEA_URL = "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"
PASSWORD = "reader-password-not-printed"
REAL_GIT = shutil.which("git")
SHELL = shutil.which("dash") or "/bin/sh"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def tasks() -> dict:
    doc = yaml.safe_load(PIPELINE.read_text())
    return {t["name"]: t for t in doc["spec"]["tasks"]}


def changes_script() -> str:
    return tasks()["changes"]["taskSpec"]["steps"][0]["script"]


def api_script() -> str:
    return tasks()["test-api"]["taskSpec"]["steps"][0]["script"]


def scope_packages() -> list[str]:
    """CONSOLE_SCOPE_PACKAGES of test-api's step, as go test takes them."""
    (line,) = [l for l in api_script().splitlines() if l.strip().startswith("CONSOLE_SCOPE_PACKAGES=")]
    return line.split("=", 1)[1].strip().strip('"').split()


def console_scope(path: str) -> bool:
    """The rule task changes applies to one path (its awk), for the checks below."""
    console = path.startswith("console/") and not path.startswith("console/src/api/")
    doc = path.endswith(".md") and not path.startswith(("api/", "config/"))
    return console or doc


def git(cwd: Path, *args: str) -> str:
    return subprocess.run([REAL_GIT, *args], cwd=cwd, env={**os.environ, **GIT_ENV}, check=True,
                          capture_output=True, text=True).stdout.strip()


# --- the pipeline's wiring -------------------------------------------------


def test_no_task_is_skipped_so_the_reason_stays_succeeded():
    doc = yaml.safe_load(PIPELINE.read_text())
    assert "finally" not in doc["spec"]
    for task in doc["spec"]["tasks"]:
        assert "when" not in task, task["name"]


def test_the_run_says_its_scope_in_a_result():
    # A release gate reads it (ci_gate.py --require-full); B5 wants every pipeline result
    # exactly once and non-empty: changes writes full before anything else.
    results = yaml.safe_load(PIPELINE.read_text())["spec"]["results"]
    names = [r["name"] for r in results]
    assert len(names) == len(set(names))
    assert {"name": "api-scope", "value": "$(tasks.changes.results.api-scope)"} in results
    assert [r["name"] for r in tasks()["changes"]["taskSpec"]["results"]][0] == "api-scope"


def test_test_api_takes_its_scope_from_changes():
    t = tasks()
    api = t["test-api"]
    assert api["params"] == [{"name": "scope", "value": "$(tasks.changes.results.api-scope)"}]
    assert api["taskSpec"]["params"] == [{"name": "scope", "type": "string", "default": "full"}]
    env = {e["name"]: e.get("value") for e in api["taskSpec"]["steps"][0]["env"]}
    assert env["API_SCOPE"] == "$(params.scope)"
    # Only the exact word console narrows the run; anything else is every test.
    assert 'if [ "${API_SCOPE:-full}" = "console" ]; then' in api_script()
    changes = t["changes"]
    assert [r["name"] for r in changes["taskSpec"]["results"]] == ["api-scope", "why"]
    assert "workspaces" not in changes and "when" not in changes and "onError" not in changes
    step = changes["taskSpec"]["steps"][0]
    secrets = {e["valueFrom"]["secretKeyRef"]["name"] for e in step["env"] if "valueFrom" in e}
    assert secrets == {"gitea-ci-reader"}
    # Parameters reach the script only through the environment (TD-435).
    script = changes_script()
    assert "$(params." not in script
    lines = [l.strip() for l in script.splitlines()]
    first_git = next(i for i, l in enumerate(lines) if "git_read clone" in l)
    assert lines.index("printf 'full' > \"$scope_file\"") < first_git


# --- task changes, run as written ------------------------------------------


@pytest.fixture
def platform(tmp_path):
    """A bare origin whose main has the platform's shape, and a clone to commit on."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(origin))
    git(origin, "config", "uploadpack.allowFilter", "true")
    git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-q", "-b", "main")
    for rel, text in {
        "api/go.mod": "module x\n",
        "api/internal/x/x.go": "package x\n",
        "api/cmd/probe/CANARY.md": "canary\n",
        "console/src/pages/A.tsx": "export const A = 1\n",
        "console/src/api/__fixtures__/f.json": "{}\n",
        "config/sessions-catalog.yaml": "a: 1\n",
        "mcp/x.ts": "export {}\n",
        "README.md": "readme\n",
    }.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    git(work, "push", "-q", "origin", "main")
    return origin, work


def branch(work: Path, name: str, change) -> str:
    git(work, "checkout", "-q", "-b", name, "main")
    change(work)
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", name)
    git(work, "push", "-q", "origin", name)
    sha = git(work, "rev-parse", "HEAD")
    git(work, "checkout", "-q", "main")
    return sha


def run_changes(tmp_path: Path, origin: Path, revision: str, url: str = GITEA_URL, credential: bool = True):
    results = tmp_path / "results"
    results.mkdir(exist_ok=True)
    for name in ("api-scope", "why"):
        (results / name).unlink(missing_ok=True)
    script = (changes_script().replace("$(results.api-scope.path)", str(results / "api-scope"))
              .replace("$(results.why.path)", str(results / "why")))
    path = tmp_path / "changes.sh"
    path.write_text(script)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    # Gitea's address goes to the local origin; everything else is git's own.
    (bin_dir / "git").write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do [ "$a" = "{GITEA_URL}" ] && a="file://{origin}"; set -- "$@" "$a"; shift; done\n'
        f'exec "{REAL_GIT}" "$@"\n')
    # busybox's timeout, as the task's image has it: SECS PROG ARGS.
    (bin_dir / "timeout").write_text(f'#!/bin/sh\necho "$1" >> "{tmp_path}/timeout-calls"\nshift\nexec "$@"\n')
    for f in ("git", "timeout"):
        (bin_dir / f).chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "TMPDIR": str(tmp_path),
           "REPO_URL": url, "REVISION": revision}
    if credential:
        env.update(GIT_USERNAME="reader", GIT_PASSWORD=PASSWORD)
    r = subprocess.run([SHELL, str(path)], env=env, capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert PASSWORD not in out
    scope, why = (results / "api-scope").read_text(), (results / "why").read_text()
    # One line: busybox's cut ends what it prints with a newline, macOS's does not always.
    assert "\n" not in why and 0 < len(why) <= 300, repr(why)
    return scope, why, out


def write(rel: str, text: str = "changed\n"):
    def change(work: Path) -> None:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    return change


def remove(rel: str):
    return lambda work: (work / rel).unlink()


def both(*changes):
    def change(work: Path) -> None:
        for c in changes:
            c(work)
    return change


def symlink(rel: str, target: str):
    def change(work: Path) -> None:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, work / rel)
    return change


def executable(rel: str):
    return lambda work: (work / rel).chmod(0o755)


CASES = [
    # (name, change, paths it touches, scope)
    ("console page", write("console/src/pages/A.tsx"), ["console/src/pages/A.tsx"], "console"),
    ("console add and delete", both(write("console/src/pages/B.tsx"), remove("console/src/pages/A.tsx")),
     ["console/src/pages/B.tsx", "console/src/pages/A.tsx"], "console"),
    ("console test and css", both(write("console/src/pages/__tests__/A.test.tsx"), write("console/src/x.css")),
     ["console/src/pages/__tests__/A.test.tsx", "console/src/x.css"], "console"),
    ("markdown outside api and config", both(write("README.md"), write("docs/plan.md")), ["README.md", "docs/plan.md"],
     "console"),
    ("console file made executable", executable("console/src/pages/A.tsx"), ["console/src/pages/A.tsx"], "console"),
    ("a fixture Go tests read", write("console/src/api/__fixtures__/f.json"), ["console/src/api/__fixtures__/f.json"],
     "full"),
    ("console/src/api source", write("console/src/api/agentRuntime.ts"), ["console/src/api/agentRuntime.ts"], "full"),
    ("go", write("api/internal/x/x.go", "package x\n// c\n"), ["api/internal/x/x.go"], "full"),
    ("markdown a Go test reads", write("api/cmd/probe/CANARY.md"), ["api/cmd/probe/CANARY.md"], "full"),
    ("markdown under config", write("config/patrol-skills/README.md"), ["config/patrol-skills/README.md"], "full"),
    ("console beside go", both(write("console/src/pages/A.tsx"), write("api/internal/x/x.go", "package x\n// d\n")),
     ["console/src/pages/A.tsx", "api/internal/x/x.go"], "full"),
    ("mcp", write("mcp/x.ts"), ["mcp/x.ts"], "full"),
    ("a symlink under console", symlink("console/src/link.ts", "../../api/go.mod"), ["console/src/link.ts"], "full"),
    ("a path with a space", write("console/src/a b.tsx"), ["console/src/a b.tsx"], "full"),
    ("a file named console", write("console.md.txt"), ["console.md.txt"], "full"),
]


@pytest.mark.parametrize("name, change, paths, scope", CASES, ids=[c[0] for c in CASES])
def test_changes_decides_from_the_paths(tmp_path, platform, name, change, paths, scope):
    origin, work = platform
    sha = branch(work, "lane", change)
    got, why, out = run_changes(tmp_path, origin, sha)
    assert got == scope, out
    # The Python mirror of the rule agrees, for the ratchet below to use.
    assert all(console_scope(p) for p in paths) == (scope == "console") or name in (
        "a symlink under console", "a path with a space", "console file made executable")
    if scope == "console":
        assert why.startswith(f"{len(paths)} file(s), each console/**"), why
    # busybox's timeout bounds each Gitea read.
    assert set((tmp_path / "timeout-calls").read_text().split()) == {"120"}


def test_a_change_beside_main_moving_on_is_judged_from_the_merge_base(tmp_path, platform):
    origin, work = platform
    sha = branch(work, "lane", write("console/src/pages/A.tsx"))
    # main moves on with Go after the lane forked: the lane's own change is console only.
    (work / "api/internal/x/x.go").write_text("package x\n// later\n")
    git(work, "commit", "-q", "-am", "go on main")
    git(work, "push", "-q", "origin", "main")
    got, why, out = run_changes(tmp_path, origin, sha)
    assert (got, why.split(",")[0]) == ("console", "1 file(s)"), out


def test_more_than_two_thousand_files_run_everything(tmp_path, platform):
    origin, work = platform

    def many(w: Path) -> None:
        d = w / "console/src/gen"
        d.mkdir(parents=True)
        for i in range(2001):
            (d / f"f{i}.ts").write_text(f"export const f{i} = {i}\n")
    sha = branch(work, "lane", many)
    got, why, out = run_changes(tmp_path, origin, sha)
    assert (got, why) == ("full", "more than 2000 files changed"), out


@pytest.mark.parametrize("how, says", [
    ("main itself", "the commit is on main: nothing to compare it with"),
    ("an older main commit", "the commit is on main: nothing to compare it with"),
    ("not a sha", "revision is not a commit SHA"),
    ("short sha", "revision is not a commit SHA"),
    ("unknown sha", "is not in Gitea"),
    ("not gitea", "the repository is not in the in-cluster Gitea"),
    ("no credential", "no Gitea reader credential"),
    ("unreachable", "cannot clone the repository from Gitea"),
])
def test_what_it_cannot_tell_runs_everything(tmp_path, platform, how, says):
    origin, work = platform
    old = git(work, "rev-parse", "main")
    (work / "console/src/pages/A.tsx").write_text("export const A = 2\n")
    git(work, "commit", "-q", "-am", "console on main")
    git(work, "push", "-q", "origin", "main")
    rev, url, credential, where = git(work, "rev-parse", "main"), GITEA_URL, True, origin
    if how == "an older main commit":
        rev = old
    elif how == "not a sha":
        rev = "main"
    elif how == "short sha":
        rev = rev[:12]
    elif how == "unknown sha":
        rev = "0123456789abcdef0123456789abcdef01234567"
    elif how == "not gitea":
        url = "http://gitea.example.invalid/bifrost/bifrost-platform.git"
    elif how == "no credential":
        credential = False
    elif how == "unreachable":
        where = tmp_path / "missing.git"
    got, why, out = run_changes(tmp_path, where, rev, url=url, credential=credential)
    assert got == "full", out
    assert says in why, why


# --- test-api in console scope ----------------------------------------------


def scope_check_source() -> str:
    """The Go self-check test-api runs before it narrows (between <<'GO' and GO)."""
    script = api_script()
    return script[script.index("<<'GO'\n") + len("<<'GO'\n"):script.index("\nGO\n")]


def known_reads() -> list[str]:
    """CONSOLE_SCOPE_KNOWN: file=target, each a read outside api/ that is allowed."""
    (line,) = [l for l in api_script().splitlines() if l.strip().startswith("CONSOLE_SCOPE_KNOWN=")]
    return line.split("=", 1)[1].strip().strip('"').split()


GO_ENV = {"GOPROXY": "off", "GOSUMDB": "off", "GOTOOLCHAIN": "local", "GOFLAGS": ""}


def go_env(tmp_path: Path) -> dict:
    return {**os.environ, **GO_ENV, "GOCACHE": str(tmp_path / "gocache"), "GOMODCACHE": str(tmp_path / "gomod")}


def module(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    """A small platform: rules, rules/s5check and cluster pass and mark that they ran; any
    other package fails, so a run that reaches it is red."""
    api = tmp_path / "bifrost-platform/api"
    api.mkdir(parents=True)
    (api / "go.mod").write_text("module example.invalid/scope\n\ngo 1.21\n")
    listed = {"internal/agentrt/rules": "rules", "internal/agentrt/rules/s5check": "s5check", "internal/cluster": "cluster"}
    for rel, pkg in listed.items():
        (api / rel).mkdir(parents=True)
        (api / rel / "a_test.go").write_text(
            f'package {pkg}\nimport ("os"; "testing")\n'
            f'func TestRan(t *testing.T) {{ os.WriteFile(os.Getenv("RAN_DIR")+"/{pkg}", nil, 0o600) }}\n')
    (api / "internal/other").mkdir(parents=True)
    (api / "internal/other/a_test.go").write_text('package other\nimport "testing"\nfunc TestRed(t *testing.T) { t.Fatal("red") }\n')
    for rel, text in (extra or {}).items():
        (tmp_path / "bifrost-platform" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "bifrost-platform" / rel).write_text(text)
    return api


def run_api(tmp_path: Path, api: Path, scope: str):
    ran = tmp_path / "ran"
    ran.mkdir(exist_ok=True)
    script = api_script().replace("$(workspaces.source.path)", str(tmp_path))
    return subprocess.run(["bash"], input=script, cwd=api, env={**go_env(tmp_path), "RAN_DIR": str(ran), "API_SCOPE": scope},
                          capture_output=True, text=True, timeout=300), ran


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_console_scope_runs_only_the_listed_packages(tmp_path):
    api = module(tmp_path)
    r, ran = run_api(tmp_path, api, "console")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "==> console scope: go test ./internal/agentrt/rules/... ./internal/cluster" in r.stdout
    assert "==> go vet" not in r.stdout
    assert sorted(p.name for p in ran.iterdir()) == ["cluster", "rules", "s5check"]
    # Positive control: every other scope runs every package, and the red one stops it.
    for scope in ("full", "", "Console", "console "):
        r, _ = run_api(tmp_path, api, scope)
        assert r.returncode != 0, scope
        assert "==> go vet ./..." in r.stdout and "console scope" not in r.stdout, scope


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_a_go_test_reading_console_outside_the_list_turns_the_run_full(tmp_path):
    # The platform adds a test that reads console/src/lib: a console change can now break
    # it, and its package is not in the list. The run checks before it narrows: full.
    api = module(tmp_path, {
        "api/internal/web/web_test.go": 'package web\nimport ("os"; "testing")\n'
                                        'func TestReads(t *testing.T) { os.ReadFile("../../../console/src/lib/x.json") }\n'})
    r, ran = run_api(tmp_path, api, "console")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "==> console scope refused, every Go test runs" in r.stdout, r.stdout
    assert "api/internal/web/web_test.go reads console/src/lib/x.json outside api/" in r.stdout
    assert "==> go vet ./..." in r.stdout and "==> console scope: go test" not in r.stdout
    assert "red" in r.stdout


def scope_check(tmp_path: Path, files: dict[str, str], packages: list[str], known: list[str]):
    root = tmp_path / "platform"
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    check = tmp_path / "scope-check"
    check.mkdir(exist_ok=True)
    (check / "main.go").write_text(scope_check_source())
    (check / "go.mod").write_text("module scopecheck\n\ngo 1.21\n")
    return subprocess.run(["go", "run", ".", str(root), *packages, "--", *known], cwd=check, env=go_env(tmp_path),
                          capture_output=True, text=True, timeout=300)


# A tree with the platform's readers outside api/ (3e7b8e48), one line each.
BASE_TREE = {
    "api/internal/agentrt/rules/a_test.go": 'root := filepath.Join(filepath.Dir(file), "../../../..")\n',
    "api/internal/cluster/a_test.go": 'root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../.."))\n',
    "api/internal/devsession/catalog_repo_test.go": 'root := filepath.Clean(filepath.Join("..", "..", ".."))\n',
    "api/internal/codehealth/scanner.go": 'filepath.Join(wd, "../../..")\n',
    "api/internal/store/f_test.go": 'const f = "../../../console/src/api/__fixtures__/x.json"\n',
    "api/internal/delivery/c_test.go": 'dir := "../../../../bifrost-trade-infra/k8s/cicd/tekton"\n',
    "api/cmd/agentd/install_test.go": 'filepath.Abs("../../../agent/deploy/install-agentd.sh")\n',
    "api/internal/patrol/s_test.go": 'dir := filepath.Join("..", "..", "..", "config", "patrol-skills")\n',
    "api/internal/agentd/p_test.go": 'bad := "../elsewhere.py"\n',
    "agent/deploy/install-agentd.sh": "",
    "console/src/pages/A.tsx": "",
}


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_the_self_check_reads_a_tree_like_the_platforms(tmp_path):
    packages, known = scope_packages(), known_reads()
    r = scope_check(tmp_path, BASE_TREE, packages, known)
    assert r.returncode == 0, r.stdout + r.stderr
    # Each known read is still there, exactly as registered, and nothing else is named.
    r = scope_check(tmp_path, BASE_TREE, packages, [])
    assert r.returncode == 1
    assert sorted(r.stdout.splitlines()) == sorted(
        f"{k.rsplit('=', 1)[0]} reads {k.rsplit('=', 1)[1]} outside api/" for k in known)
    r = scope_check(tmp_path, BASE_TREE, packages + ["./internal/gone"], known)
    assert r.returncode == 1 and "allowed package ./internal/gone has no Go file" in r.stdout


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
@pytest.mark.parametrize("rel, line, target", [
    ("api/internal/web/a_test.go", 'os.ReadFile("../../../console/src/lib/x.json")', "console/src/lib/x.json"),
    ("api/internal/web/a_test.go", 'root := filepath.Join("..", "..", "..", "console")', "console"),
    ("api/internal/web/a_test.go", 'filepath.WalkDir("../../..", f)', "."),
    ("api/internal/web/a_test.go", 'os.ReadFile("../../../docs/notes.md")', "docs/notes.md"),
    ("api/internal/agentrt/other/a_test.go", 'root := "../../../.."', "."),
])
def test_a_new_reader_outside_the_list_is_named(tmp_path, rel, line, target):
    r = scope_check(tmp_path, {**BASE_TREE, rel: line + "\n"}, scope_packages(), known_reads())
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.splitlines() == [f"{rel} reads {target} outside api/"], r.stdout


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_a_known_file_is_excused_for_its_one_target_only(tmp_path):
    # Review: CONSOLE_SCOPE_KNOWN once excused a whole file. A new read in a known file
    # (here devsession's catalog test reading console/src/lib) is named like any other.
    rel = "api/internal/devsession/catalog_repo_test.go"
    files = {**BASE_TREE, rel: BASE_TREE[rel] + 'src := "../../../console/src/lib/x.ts"\n'}
    r = scope_check(tmp_path, files, scope_packages(), known_reads())
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stdout.splitlines() == [f"{rel} reads console/src/lib/x.ts outside api/"], r.stdout
    # A pair without a target is refused outright (the run goes full).
    r = scope_check(tmp_path, BASE_TREE, scope_packages(), [rel])
    assert r.returncode != 0 and "a known read is file=target" in r.stdout


def platform_checkout() -> Path | None:
    """The platform checkout beside this infra one (push-main.sh links it there), or
    BIFROST_PLATFORM_ROOT."""
    for candidate in (os.environ.get("BIFROST_PLATFORM_ROOT"), ROOT.parent / "bifrost-platform"):
        if candidate and (Path(candidate) / "api/go.mod").is_file():
            return Path(candidate)
    return None


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_auxiliary_the_self_check_passes_on_the_platform_checkout(tmp_path):
    """Auxiliary, not the gate: test-api runs the self-check on the commit it tests. This
    only warns early, on whatever checkout is beside this one (it may be behind main)."""
    root = platform_checkout()
    if root is None:
        pytest.skip("no bifrost-platform checkout beside this one; set BIFROST_PLATFORM_ROOT")
    check = tmp_path / "scope-check"
    check.mkdir()
    (check / "main.go").write_text(scope_check_source())
    (check / "go.mod").write_text("module scopecheck\n\ngo 1.21\n")
    r = subprocess.run(["go", "run", ".", str(root), *scope_packages(), "--", *known_reads()], cwd=check,
                       env=go_env(tmp_path), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
