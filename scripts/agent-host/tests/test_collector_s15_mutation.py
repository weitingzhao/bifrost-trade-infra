"""S1-5 mutation check: each mutant is one plausible mistake in the S1-5 code, and the one
test named for it must then fail; an unmutated copy passes every named test first.

python3 -m pytest -q scripts/agent-host/tests/test_collector_s15_mutation.py
"""

import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from collector_fakes import INFRA

LAUNCH = "scripts/agent-host/tests/test_collector_launch.py"
CODEX = "scripts/agent-host/tests/test_collector_codex.py"
HANDIN = "agent-config/scripts/landing/test_handin_sessions.py"
W, L, X = "scripts/agent-host/collector_work.py", "scripts/agent-host/dispatch-claude.py", "scripts/agent-host/dispatch-codex.py"
J, H = "agent-config/scripts/collector-launch.js", "agent-config/scripts/landing/handin-sessions.sh"

# (name, file, from, to, test file, -k expression)
MUTANTS = [
    ("the registration names no identity", W, '        **identity,\n    }\n    if sidebar', '    }\n    if sidebar', LAUNCH, "sessions_backfill"),
    ("no heartbeat is sent", W, 'if event == "heartbeat" and status == "Running":', "if False:", LAUNCH, "sessions_backfill"),
    ("a refusal is not kept", W, 'state["failed"] = {"why": str(exc)[:120], "at": now_text()}', "pass", LAUNCH, "refused_registration"),
    ("the hooks retry a refused registration", W, '(state.get("failed") and not retry_failed)', "False", LAUNCH, "refused_registration"),
    ("bind takes other content", W, 'any(state.get(k) != candidate[k] for k in ("url", "identity", "registration"))', "False", CODEX, "bind_registers_once"),
    ("an inherited sidebar is kept", L, "if inherited and not parent and", "if inherited and", LAUNCH, "sidebar_inherited"),
    ("an incomplete description launches", L, "    if missing:\n", "    if False:\n", LAUNCH, "incomplete_description"),
    ("the record names another pid", L, '"cli_pid": pid,', '"cli_pid": pid + 1,', LAUNCH, "sessions_backfill"),
    ("the wrapper registers no identity", X, "            registration.update(identity)\n", "", CODEX, "registers_with_the_collector_token"),
    ("the child gets the collector token", X, 'child = launch(run_dir, args, repo, ("PLATFORM_COLLECTOR_TOKEN",))', "child = launch(run_dir, args, repo)", CODEX, "registers_with_the_collector_token"),
    ("a second reconcile sends again", X, 'if state.get("reconciled") and "pending" not in state:', "if False:", CODEX, "reconcile_ends"),
    ("reconcile ignores a live child", X, "        if child_active(run_dir):\n", "        if False:\n", CODEX, "reconcile_refuses"),
    ("a nested session counts as the launch", J, "return Boolean(found) && pid > 0 && found.launch.cli_pid === pid", "return Boolean(found)", LAUNCH, "nested_in_the_launch"),
    ("waiting for registration says no_context", J, "  if (whole && owned && linkedLaunch) return undefined\n", "", LAUNCH, "sessions_backfill"),
    ("a superseded work is not cancelled", J, "if (event === 'cancel' ? !workState(vendor, session, epoch) : !writes) continue", "if (event === 'cancel' || !writes) continue", LAUNCH, "resume_cancels"),
    ("no fallback to the session id", H, '  if [ -z "$states" ]; then\n    states=$(sessions_get session "$value") || { echo unknown; return; }\n  fi\n', "", HANDIN, "registered_unregistered"),
    ("linked does not win", H, "elif grep -qx linked <<<\"$states\"; then echo registered", "elif false; then echo registered", HANDIN, "registered_unregistered"),
    ("a retried squash asks again", H, '  if [ -f "$dir/sessions.json" ] && [ "$(jq', '  if false && [ -f "$dir/sessions.json" ] && [ "$(jq', HANDIN, "registered_unregistered"),
    ("no token still asks", H, 'sessions_check() {\n  [ -n "$(sessions_token)" ] || return 0\n', "sessions_check() {\n", HANDIN, "without_a_collector_token"),
]
COPY = ["scripts/agent-host", "agent-config/scripts/thread-heartbeat.js", "agent-config/scripts/collector-session.js", "agent-config/scripts/collector-epochs.js",
        J, "agent-config/scripts/collector-audit.js", "agent-config/scripts/landing/handin.sh", H, HANDIN]


def copy_tree(root: Path) -> Path:
    for rel in COPY:
        src, dst = INFRA / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(src, dst)
    return root


def run(root: Path, test: str, expr: str):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(root / test), "-k", expr],
                          cwd=root, capture_output=True, text=True, timeout=300)


def test_every_s15_mutant_is_killed_by_its_named_test(tmp_path):
    clean = copy_tree(tmp_path / "clean")
    for test in {m[4] for m in MUTANTS}:
        expr = " or ".join(sorted({m[5] for m in MUTANTS if m[4] == test}))
        r = run(clean, test, expr)
        assert r.returncode == 0, f"the unmutated copy fails {test}:\n{r.stdout[-3000:]}"

    def one(i):
        name, rel, old, new, test, expr = MUTANTS[i]
        root = copy_tree(tmp_path / f"m{i}")
        target = root / rel
        text = target.read_text()
        assert text.count(old) == 1, f'mutant "{name}": its anchor must occur once in {rel}'
        target.write_text(text.replace(old, new))
        r = run(root, test, expr)
        # pytest: 1 = a test failed (killed); 5 = nothing collected (the name matched no test).
        return name, r.returncode == 1, r.returncode != 5

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, range(len(MUTANTS))))
    assert [name for name, killed, _ in results if not killed] == [], "surviving mutants"
    assert all(ran for _, _, ran in results)
