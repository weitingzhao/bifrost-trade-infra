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
INTENTS = "scripts/agent-host/tests/test_collector_intents.py"
ENV = "scripts/agent-host/tests/test_collector_env.py"
W, L, X = "scripts/agent-host/collector_work.py", "scripts/agent-host/dispatch-claude.py", "scripts/agent-host/dispatch-codex.py"
J, H = "agent-config/scripts/collector-launch.js", "agent-config/scripts/landing/handin-sessions.sh"
A = "agent-config/scripts/collector-audit.js"

# (name, file, from, to, test file, -k expression)
MUTANTS = [
    ("the registration names no identity", W, '        **identity,\n    }\n    if sidebar', '    }\n    if sidebar', LAUNCH, "sessions_backfill"),
    ("no heartbeat is sent", W, 'elif event == "heartbeat" and current["state"] == "Running":', "elif False:", LAUNCH, "sessions_backfill"),
    ("a refusal is not kept", W, 'state["failed"] = {"why": str(exc)[:120], "at": now_text()}', "pass", LAUNCH, "refused_registration"),
    ("the hooks retry a refused registration", W, 'if state.get("failed") and not retry_failed:', "if False:", LAUNCH, "refused_registration"),
    ("bind takes other content", W, 'any(state.get(k) != candidate[k] for k in ("url", "identity", "registration"))', "False", CODEX, "bind_registers_once"),
    ("an end is not kept first (M2)", W, '    if event in ("submit", "cancel"):\n        note_terminal(directory, event)\n', "", INTENTS, "m2_a_submit_whose_read_fails"),
    ("a kept end is not delivered (M2)", W, '            if terminal == "submit":', "            if False:", INTENTS, "m2_a_submit_that_cannot_take_the_lock"),
    ("a late start registers a cancelled epoch (M3)", W, 'if launch_id and read_terminal(directory) != "cancel" else None', "if launch_id else None", INTENTS, "m3_a_cancel_before_the_delayed_start"),
    ("a sent registration is forgotten (M3)", W, '    state["registration_sent"] = True\n', "", INTENTS, "m3_a_registration_whose_reply_was_lost"),
    ("a cancel kept while registering still starts (R2-M2)", W, '        if status == "Registered" and terminal != "cancel":\n', "        if False:\n", INTENTS, "r2m2_a_cancel_kept_while_registering"),
    ("an inherited sidebar is kept", L, "if inherited and not parent and", "if inherited and", LAUNCH, "sidebar_inherited"),
    ("an incomplete description launches", L, "    if missing:\n", "    if False:\n", LAUNCH, "incomplete_description"),
    ("a blank acceptance reference passes (S1)", L, "    if any(not ref.strip() for ref in options.acceptance_ref):", "    if False:", LAUNCH, "incomplete_description"),
    ("claude gets the coordinator's tokens", L, "    child = child_env(env)\n", "    child = dict(env)\n", LAUNCH, "coordinator_credential"),
    ("the record names another pid", L, '"cli_pid": pid,', '"cli_pid": pid + 1,', LAUNCH, "sessions_backfill"),
    ("the wrapper registers no identity", X, "            registration.update(identity)\n", "", CODEX, "registers_with_the_collector_token"),
    ("codex keeps the coordinator's variables (M5)", X, " and not k.startswith(COORDINATOR_PREFIXES)}", "}", CODEX, "no_credential"),
    ("codex loses the heartbeat's address (R2-M1)", X, 'COORDINATOR_PREFIXES = ("AGENTRT_"', 'COORDINATOR_PREFIXES = ("PLATFORM_", "AGENTRT_"', ENV, "heartbeat_still_aims"),
    ("codex keeps the *_KEY credentials (R2-M1)", X, "|(^|_)(API_?)?KEY(_ID)?$", "", ENV, "codex_loses_every_credential"),
    ("codex keeps the *_AUTH credentials (R2-M1)", X, "|(^|_)AUTH($|_)", "", ENV, "codex_loses_every_credential"),
    ("codex keeps the kubeconfig (R2-M1)", X, "|^KUBECONFIG$", "", ENV, "codex_loses_every_credential"),
    ("claude keeps the *_KEY credentials (R2-M1)", L, "|(^|_)(API_?)?KEY(_ID)?$", "", ENV, "claude_loses"),
    ("codex keeps credential variables (M5)", X, "if not SECRET_NAME.search(k) and", "if", CODEX, "no_credential"),
    ("a second reconcile sends again", X, 'if state.get("reconciled") and "pending" not in state:', "if False:", CODEX, "reconcile_ends"),
    ("a live codex without the lock is cancelled (M1)", X, '        return now != started, "Codex is still running"', '        return True, ""', CODEX, "let_go_of_the_child_lock"),
    ("an older run is taken as gone (M1)", X, '    if json.loads((directory / "child.json").read_text()).get("v") != 2:', "    if False:", CODEX, "cannot_be_told"),
    ("collector runs keyed by --session (M4)", X, "    if identity:\n        u = ", "    if False:\n        u = ", CODEX, "two_callers"),
    ("two platforms share a run (R2-M3)", X, ' + scope + "\\0"', "", CODEX, "two_platforms"),
    ("a nested session counts as the launch", J, "return Boolean(found) && pid > 0 && found.launch.cli_pid === pid", "return Boolean(found)", LAUNCH, "nested_in_the_launch"),
    ("waiting for registration says no_context", J, "  if (whole && owned && linkedLaunch) return undefined\n", "", LAUNCH, "sessions_backfill"),
    ("the hook keeps no submit (M2)", J, "    if (event === 'submit') noteTerminal(dir, event)\n", "", INTENTS, "hooks_keep_the_end_themselves"),
    ("the hook keeps no cancel (M3)", J, "      noteTerminal(dir, 'cancel')\n", "", INTENTS, "r2m2_a_resume_between"),
    ("a cancel waits for the work directory (R2-M2)", J, "      noteTerminal(dir, 'cancel')\n      if (!workState(vendor, session, epoch)) continue\n",
     "      if (!workState(vendor, session, epoch)) continue\n      noteTerminal(dir, 'cancel')\n", INTENTS, "r2m2_a_resume_between"),
    ("a superseded work is not cancelled", J, "      if (!workState(vendor, session, epoch)) continue\n", "      if (!workState(vendor, session, epoch) || !writes) continue\n", LAUNCH, "resume_cancels"),
    ("the audit calls a lost registration never sent (R2-S1)", A, "  if (state && state.registration_sent) return 'unconfirmed'\n", "", INTENTS, "r2s1"),
    ("the audit owes no end to a lost registration (R2-S1)", A, "Boolean(state && (state.id || state.registration_sent))", "Boolean(state && state.id)", INTENTS, "r2s1"),
    ("the audit misses an undelivered end (M2)", A, "    if (works.some(w => w.end_not_delivered)) gaps.push('work_end_not_delivered')\n", "", INTENTS, "audit_reports_an_end"),
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
