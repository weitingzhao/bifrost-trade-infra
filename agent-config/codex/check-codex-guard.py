#!/usr/bin/env python3
"""Check that Codex on this machine runs the preflight gate (W-35).

Codex only runs a hook whose trusted hash matches the hook's current config, and an
untrusted hook is skipped without an error. So "hooks.json exists" proves nothing:
this asks Codex itself (app-server hooks/list) whether the gate is enabled and trusted.

    python3 agent-config/codex/check-codex-guard.py            # config only, no model call
    python3 agent-config/codex/check-codex-guard.py --probe    # also a live codex exec probe

Exit 0 = all checks pass, 1 = something is off (printed).
"""
from __future__ import annotations

import json
import os
import pathlib
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

CODEX_HOME = pathlib.Path(os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex"))
ADAPTER = "agent-guard/codex-pretooluse.js"
MARKER = "bifrost-platform/config/ops-context.yaml"


def workspace_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for d in here.parents:
        if (d / MARKER).is_file():
            return d
    env = os.environ.get("BIFROST_WORKSPACE")
    if env and (pathlib.Path(env) / MARKER).is_file():
        return pathlib.Path(env)
    sys.exit(f"✗ workspace root not found (no {MARKER} above {here}; set BIFROST_WORKSPACE)")


def hooks_list(cwds: list[str]) -> dict:
    p = subprocess.Popen(
        ["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )

    def send(msg: dict) -> None:
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()

    def recv(want: int) -> dict:
        end = time.time() + 30
        while time.time() < end:
            ready, _, _ = select.select([p.stdout], [], [], 1)
            if not ready:
                continue
            line = p.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == want:
                return msg
        raise RuntimeError("codex app-server did not answer")

    try:
        send({"method": "initialize", "id": 1, "params": {"clientInfo": {"name": "bifrost-check", "version": "0"}}})
        recv(1)
        send({"method": "initialized"})
        send({"method": "hooks/list", "id": 2, "params": {"cwds": cwds}})
        return recv(2)
    finally:
        p.terminate()


def smoke_hook(command: str) -> list[str]:
    """Run the hook command the way Codex does (through a shell) on two payloads.

    A command whose script path does not resolve is an error hook, and Codex lets the
    tool call through; only a deny for `git add -A` and a clean allow prove the gate runs.
    """
    base = {"session_id": "s", "turn_id": "t", "cwd": "/tmp", "hook_event_name": "PreToolUse", "model": "m"}
    fails: list[str] = []
    for cmd, want in (("git add " + "-A", "deny"), ("git status --short", "allow")):
        payload = json.dumps({**base, "tool_name": "Bash", "tool_input": {"command": cmd}})
        r = subprocess.run(["sh", "-c", command], input=payload, capture_output=True, text=True, timeout=30)
        got = "error" if r.returncode else "allow"
        if not r.returncode and r.stdout.strip():
            decision = json.loads(r.stdout).get("hookSpecificOutput", {}).get("permissionDecision")
            got = "deny" if decision == "deny" else "allow"
        if got != want:
            fails.append(f"hook command on `{cmd}`: want {want}, got {got} ({r.stderr.strip()[:200]})")
    return fails


HEARTBEAT = "thread-heartbeat.js"
HEARTBEAT_EVENTS = ("userPromptSubmit", "preToolUse", "postToolUse", "stop")


def heartbeat_warnings(resp: dict) -> list[str]:
    """Thread heartbeat hooks (W-54). Warnings, not failures: an untrusted one is
    skipped silently, so the thread is invisible on the Console, but tool calls
    are not affected."""
    warns: list[str] = []
    for entry in resp.get("result", {}).get("data", []):
        where = entry["cwd"]
        for ev in HEARTBEAT_EVENTS:
            beats = [h for h in entry["hooks"] if h["eventName"] == ev and HEARTBEAT in h["command"]]
            if not beats:
                warns.append(f"{where}: no {ev} hook runs {HEARTBEAT} (README, hooks.json)")
            for h in beats:
                if not h["enabled"] or h["trustStatus"] != "trusted":
                    warns.append(f"{where}: heartbeat {h['key']} is {h['trustStatus']}"
                                 f"{'' if h['enabled'] else ', disabled'}; re-trust it (README, install step 4)")
    return warns


def probe() -> list[str]:
    fails: list[str] = []
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="codex-guard-probe-"))
    try:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        (tmp / "a.txt").write_text("probe\n")
        out = subprocess.run(
            ["codex", "exec", "-C", str(tmp),
             "Run exactly this one shell command, once, and report its output verbatim "
             "including any hook message: git add -A. Do not retry or work around a block."],
            capture_output=True, text=True, timeout=300,
        ).stdout
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=tmp,
                                capture_output=True, text=True).stdout.strip()
        if "共享工作树" not in out:
            fails.append("probe: `git add -A` was not blocked by the preflight hook")
        if staged:
            fails.append(f"probe: files were staged: {staged}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return fails


def main() -> int:
    root = workspace_root()
    fails: list[str] = []

    if not shutil.which("codex"):
        fails.append("`codex` is not on PATH (see agent-config/codex/README.md, install step 1)")
        print("\n".join("✗ " + f for f in fails))
        return 1

    cfg = tomllib.loads((CODEX_HOME / "config.toml").read_text())
    if cfg.get("sandbox_mode") != "workspace-write":
        fails.append(f"sandbox_mode is {cfg.get('sandbox_mode')!r}, expected 'workspace-write'")
    if cfg.get("approval_policy") != "on-request":
        fails.append(f"approval_policy is {cfg.get('approval_policy')!r}, expected 'on-request'")
    agent_work = str(pathlib.Path.home() / "agent-work")
    for path in (str(root), agent_work):
        if cfg.get("projects", {}).get(path, {}).get("trust_level") != "trusted":
            fails.append(f"project {path} is not trusted in config.toml")

    pointer = CODEX_HOME / "AGENTS.md"
    if not pointer.is_file() or f"{root}/AGENTS.md" not in pointer.read_text():
        fails.append(f"{pointer} does not point to {root}/AGENTS.md")

    resp = hooks_list([str(root), agent_work])
    for entry in resp.get("result", {}).get("data", []):
        gates = [h for h in entry["hooks"] if h["eventName"] == "preToolUse" and ADAPTER in h["command"]]
        where = entry["cwd"]
        if entry.get("errors"):
            fails.append(f"{where}: hook errors {entry['errors']}")
        if not gates:
            fails.append(f"{where}: no PreToolUse hook runs {ADAPTER}")
        for h in gates:
            if not h["enabled"]:
                fails.append(f"{where}: {h['key']} is disabled")
            if h["trustStatus"] != "trusted":
                fails.append(f"{where}: {h['key']} is {h['trustStatus']} (hash {h['currentHash']}); "
                             "re-trust it (README, install step 4)")
            elif h["matcher"] not in (None, "", ".*", "*"):
                fails.append(f"{where}: matcher {h['matcher']!r} does not cover every tool")
            fails += [f"{where}: {f}" for f in smoke_hook(h["command"])]

    warns = heartbeat_warnings(resp)

    if "--probe" in sys.argv[1:]:
        fails += probe()

    if warns:
        print("\n".join("! " + w for w in warns))
    if fails:
        print("\n".join("✗ " + f for f in fails))
        return 1
    print("✓ Codex runs the preflight gate: hook enabled and trusted, config as documented"
          + (", live probe blocked `git add -A`" if "--probe" in sys.argv[1:] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
